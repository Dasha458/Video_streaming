"""
End-to-end tests: the running stack, through the gateway, nothing mocked.

Everything else in this suite stops at a boundary. The unit tests mock
the session and the storage client; even the integration tests, which
use a real Postgres, mock S3 and the broker. So the one path the product
exists for -- somebody uploads a video and somebody else watches it --
was covered by nothing, end to end, and the pieces were only ever
checked against each other's descriptions.

These talk to http://localhost: nginx, the backend, Postgres, MinIO,
RabbitMQ and the converter, as deployed. They are skipped when that is
not answering, so `pytest` on a laptop with nothing running is quiet.

    docker compose up -d
    pytest tests/e2e -m e2e
"""

import os
import secrets
import time
from pathlib import Path
from typing import Iterator

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost")
FIXTURE = Path(__file__).parent / "fixtures" / "sample.mp4"

#: Enough to need more than one part, so the resumable path is exercised
#: rather than described. The server's part size is 10 MiB.
PADDING_BYTES = 1_200_000 + 10 * 1024 * 1024

#: The window the gateway and the application count upload starts in.
RATE_LIMIT_WINDOW = 60

#: Encoding a three-second clip takes seconds; this is slack for a cold
#: converter, not an expectation.
ENCODE_TIMEOUT = 240
POLL_SECONDS = 2


def _stack_is_up() -> bool:
    try:
        response = httpx.get(f"{BASE_URL}/api/health/ready", timeout=5)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def pytest_collection_modifyitems(config, items):
    if _stack_is_up():
        return
    skip = pytest.mark.skip(
        reason=f"no stack answering at {BASE_URL} -- run docker compose up -d"
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture
def unique_video(tmp_path: Path) -> Path:
    """A playable video no one has uploaded before.

    The platform stores a given file once -- that is the rule -- so a
    test that uploaded a fixed file would pass once and then be refused
    as a duplicate for ever. Random padding after the last MP4 box
    changes the hash and leaves the file decodable; it also pushes it
    past the part size, so the upload really is sent in parts.
    """
    target = tmp_path / "unique.mp4"
    target.write_bytes(FIXTURE.read_bytes() + secrets.token_bytes(PADDING_BYTES))
    return target


class Account:
    """A signed-in client, the details it was created with, and what it
    has uploaded so far.

    The list of uploads lives here rather than in a module-level
    registry: pytest may load this conftest under a different module
    name than the one a test imports the helper from, in which case
    module state is two lists and the cleanup empties the wrong one.
    An attribute on the object the fixture itself yields cannot drift
    like that.
    """

    def __init__(self, client: httpx.Client, email: str, username: str):
        self.client = client
        self.email = email
        self.username = username
        self.created: list[str] = []


def _register_and_sign_in(base: str) -> Account:
    suffix = secrets.token_hex(6)
    email = f"e2e-{suffix}@example.com"
    username = f"e2e{suffix}"
    password = "A-str0ng-e2e-passw0rd"

    client = httpx.Client(base_url=base, timeout=60, follow_redirects=False)

    created = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "username": username},
    )
    assert created.status_code == 201, created.text

    signed_in = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert signed_in.status_code == 204, signed_in.text

    return Account(client, email, username)


# Session-scoped on purpose. The gateway rate-limits /api/auth/* to five
# requests a minute, which is correct and which a fixture registering an
# account per test walks straight into: twelve tests is twenty-four auth
# requests. Two accounts are enough -- an owner and somebody else -- and
# each test still gets a file nobody has uploaded before.
@pytest.fixture(scope="session")
def uploader(base_url: str) -> Iterator[Account]:
    account = _register_and_sign_in(base_url)
    yield account

    # A run that leaves half a dozen encoded videos behind fills the
    # bucket and the listing pages of whatever machine it was pointed at.
    for video_id in account.created:
        # A video still being encoded cannot be deleted -- the converter
        # is writing into that prefix -- and several tests finish without
        # waiting for it, so the cleanup would silently skip exactly
        # those. Quietly, and stopping the moment it is gone: one test
        # deletes its video on purpose, and waiting 240s for that one to
        # become playable is four minutes spent on nothing.
        _settle(account.client, video_id)
        try:
            account.client.delete(f"/api/files/videos/{video_id}")
        except httpx.HTTPError:
            pass
    account.created.clear()
    account.client.close()


@pytest.fixture(scope="session")
def viewer(base_url: str) -> Iterator[Account]:
    """Somebody else: signed in, and not the owner of anything."""
    account = _register_and_sign_in(base_url)
    yield account
    account.client.close()


@pytest.fixture(scope="session")
def anonymous(base_url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=base_url, timeout=60) as client:
        yield client


@pytest.fixture(scope="session")
def published_video(uploader, tmp_path_factory) -> dict:
    """One public, encoded video, shared by the tests that only read it.

    Encoding is the slow part of this suite, so uploading a fresh video
    for every assertion about an existing one would cost minutes to
    prove nothing extra. Tests that change state still upload their own.
    """
    target = tmp_path_factory.mktemp("published") / "published.mp4"
    target.write_bytes(FIXTURE.read_bytes() + secrets.token_bytes(PADDING_BYTES))

    video_id = upload_in_parts(uploader, target, name="E2E published video")
    video = wait_until_ready(uploader.client, video_id)
    video["id"] = video_id
    return video


def start_upload(client: httpx.Client, path: Path) -> dict:
    """Open an upload, waiting out the rate limit if it is in the way.

    Starting an upload is limited to ten a minute per address, which is
    generous for a person and tight for a suite that uploads eight
    videos and may be run twice in a row. Waiting is honest -- the limit
    is doing its job -- and far better than loosening a real control to
    suit the tests.
    """
    payload = {
        "filename": path.name,
        "content_type": "video/mp4",
        "size": path.stat().st_size,
    }
    started = client.post("/api/files/uploads", json=payload)
    if started.status_code == 429:
        time.sleep(RATE_LIMIT_WINDOW + 2)
        started = client.post("/api/files/uploads", json=payload)
    assert started.status_code == 200, started.text
    return started.json()


def upload_in_parts(account: "Account", path: Path, **metadata) -> str:
    """Do what the browser does, and return the new video's id."""
    client = account.client
    upload = start_upload(client, path)

    data = path.read_bytes()
    part_size = upload["part_size"]
    for number in range(1, upload["total_parts"] + 1):
        chunk = data[(number - 1) * part_size : number * part_size]
        sent = client.put(
            f"/api/files/uploads/{upload['upload_id']}/parts/{number}",
            content=chunk,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert sent.status_code == 200, sent.text

    finished = client.post(
        f"/api/files/uploads/{upload['upload_id']}/complete",
        data={
            "name": metadata.get("name", "e2e video"),
            "description": metadata.get("description", ""),
            "privacy": metadata.get("privacy", "public"),
            "category": metadata.get("category", "education"),
        },
    )
    assert finished.status_code == 200, finished.text
    video_id = finished.json()["files"][0]["file_id"]
    account.created.append(video_id)
    return video_id


def _settle(client: httpx.Client, video_id: str, timeout: int = ENCODE_TIMEOUT) -> None:
    """Wait until a video is deletable, and never raise.

    Deletable means encoded, or already gone. This is cleanup: a failure
    here should not turn a passing run into an error.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = client.get(f"/api/videos/{video_id}")
        except httpx.HTTPError:
            return
        if response.status_code == 404:
            return
        if response.status_code == 200 and response.json().get("master_hls_url"):
            return
        time.sleep(POLL_SECONDS)


def wait_until_ready(
    client: httpx.Client, video_id: str, timeout: int = ENCODE_TIMEOUT
) -> dict:
    """Block until the converter has finished with it, or say why not."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/videos/{video_id}")
        if response.status_code == 200:
            last = response.json()
            if last.get("master_hls_url"):
                return last
        time.sleep(POLL_SECONDS)

    pytest.fail(
        f"video {video_id} was not playable within {timeout}s; "
        f"last response: {last}"
    )
