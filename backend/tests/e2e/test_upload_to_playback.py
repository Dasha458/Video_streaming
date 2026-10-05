"""
The one path the product exists for: somebody uploads a video, and
somebody else watches it.

Nothing covered this end to end. The unit tests mock the session and the
storage client; the integration tests use a real Postgres but still mock
S3 and the broker. So every piece was checked against the others'
descriptions, and the places where a description was wrong -- a download
that returned a playlist named .mp4, a readiness check reading an
attribute that does not exist -- survived for months.

These go through the gateway and wait for the converter, so a failure
here means a user-visible failure.
"""

import pytest

from tests.e2e.conftest import start_upload, upload_in_parts, wait_until_ready

pytestmark = pytest.mark.e2e

MP4_MAGIC = b"ftyp"


class TestUploadingAndWatching:
    def test_a_video_goes_from_upload_to_playable(self, published_video):
        """Upload, encode, and a playlist the player can actually load."""
        video = published_video

        assert video["name"] == "E2E published video"
        assert video["master_hls_url"], "no playlist to play"
        # The ladder the converter is configured with.
        assert sorted(video["resolutions"]) == ["1080p", "360p", "720p"]

    def test_the_playlist_is_served_by_the_gateway(self, anonymous, published_video):
        """The player fetches this URL directly from storage through
        nginx, never through the backend -- so a backend that believes
        the video is ready proves nothing on its own."""
        video = published_video

        playlist = anonymous.get("/" + video["master_hls_url"].lstrip("/"))

        assert playlist.status_code == 200, playlist.text[:200]
        assert playlist.text.startswith("#EXTM3U")
        # A master playlist names the renditions rather than segments.
        assert "stream_720p/playlist.m3u8" in playlist.text

    def test_a_rendition_and_its_segments_are_reachable(
        self, anonymous, published_video
    ):
        """One level further down: the playlist is useless if the
        segments it names cannot be fetched."""
        video = published_video
        base = "/" + video["master_hls_url"].rsplit("/", 1)[0].lstrip("/")

        rendition = anonymous.get(f"{base}/stream_720p/playlist.m3u8")
        assert rendition.status_code == 200
        assert rendition.text.startswith("#EXTM3U")

        first_segment = next(
            line for line in rendition.text.splitlines() if line.endswith(".ts")
        )
        segment = anonymous.get(f"{base}/stream_720p/{first_segment}")

        assert segment.status_code == 200
        assert len(segment.content) > 1000

    def test_somebody_else_can_find_and_watch_it(self, viewer, published_video):
        seen = viewer.client.get(f"/api/videos/{published_video['id']}")

        assert seen.status_code == 200
        body = seen.json()
        assert body["master_hls_url"]
        assert body["is_owner"] is False

    def test_a_private_video_is_not_visible_to_anyone_else(
        self, uploader, viewer, anonymous, unique_video
    ):
        video_id = upload_in_parts(
            uploader, unique_video, name="E2E private", privacy="private"
        )
        wait_until_ready(uploader.client, video_id)

        # Not "forbidden": that would confirm the id exists.
        assert viewer.client.get(f"/api/videos/{video_id}").status_code == 404
        assert anonymous.get(f"/api/videos/{video_id}").status_code == 404


class TestDownloading:
    def test_the_owner_gets_a_real_mp4(self, uploader, published_video):
        """It used to hand over the .m3u8 playlist with a .mp4 name: a
        few hundred bytes of text saved as a video."""
        downloaded = uploader.client.get(
            f"/api/files/videos/{published_video['id']}/download"
        )

        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith("video/mp4")
        assert 'filename="E2E published video.mp4"' in (
            downloaded.headers.get("content-disposition", "")
        )
        # The bytes, not the promise: an MP4 names its brand at offset 4.
        assert downloaded.content[4:8] == MP4_MAGIC
        assert len(downloaded.content) > 100_000, "this is the size of a playlist"

    def test_nobody_else_may_download_it(self, viewer, published_video):
        refused = viewer.client.get(
            f"/api/files/videos/{published_video['id']}/download"
        )

        assert refused.status_code == 404


class TestTheUploadItself:
    def test_an_interrupted_upload_carries_on(self, uploader, unique_video):
        """The reason for all of this: the parts already sent are not
        sent again.

        It also pins the shape of the upload. If this ever became one
        request again the gateway would refuse it outright --
        client_max_body_size is 12m.
        """
        data = unique_video.read_bytes()
        started = start_upload(uploader.client, unique_video)
        assert started["total_parts"] >= 2, "the fixture no longer exceeds one part"
        assert started["part_size"] <= 12 * 1024 * 1024

        part_size = started["part_size"]
        upload_id = started["upload_id"]

        uploader.client.put(
            f"/api/files/uploads/{upload_id}/parts/1",
            content=data[:part_size],
            headers={"Content-Type": "application/octet-stream"},
        )

        # What a browser asks after being closed and reopened.
        resumed = uploader.client.get(f"/api/files/uploads/{upload_id}")

        assert resumed.status_code == 200
        assert resumed.json()["received_parts"] == [1]
        assert resumed.json()["received_bytes"] == part_size

        for number in range(2, started["total_parts"] + 1):
            uploader.client.put(
                f"/api/files/uploads/{upload_id}/parts/{number}",
                content=data[(number - 1) * part_size : number * part_size],
                headers={"Content-Type": "application/octet-stream"},
            )

        finished = uploader.client.post(
            f"/api/files/uploads/{upload_id}/complete",
            data={
                "name": "E2E resumed",
                "description": "",
                "privacy": "public",
                "category": "education",
            },
        )

        assert finished.status_code == 200
        # Registered by hand: this test drives the upload directly rather
        # than through the helper, so nothing else knows the video exists
        # and the cleanup would leave it behind on every run.
        uploader.created.append(finished.json()["files"][0]["file_id"])

    def test_the_same_file_cannot_be_uploaded_twice(self, uploader, unique_video):
        """The platform's rule, through the whole stack: the hash is
        computed by the server from what was actually stored."""
        upload_in_parts(uploader, unique_video, name="E2E original")

        with pytest.raises(AssertionError):
            upload_in_parts(uploader, unique_video, name="E2E copy")

    def test_a_lie_about_the_size_is_caught(self, uploader, unique_video):
        """The declared size decides whether an upload may start, so it
        is checked again against what arrived."""
        data = unique_video.read_bytes()
        started = uploader.client.post(
            "/api/files/uploads",
            json={
                "filename": "unique.mp4",
                "content_type": "video/mp4",
                # Deliberately not the real size: this is the lie.
                "size": len(data) + 5_000_000,
            },
        ).json()

        part_size = started["part_size"]
        for number in range(1, (len(data) + part_size - 1) // part_size + 1):
            uploader.client.put(
                f"/api/files/uploads/{started['upload_id']}/parts/{number}",
                content=data[(number - 1) * part_size : number * part_size],
                headers={"Content-Type": "application/octet-stream"},
            )

        refused = uploader.client.post(
            f"/api/files/uploads/{started['upload_id']}/complete",
            data={
                "name": "E2E wrong size",
                "description": "",
                "privacy": "public",
                "category": "education",
            },
        )

        assert refused.status_code == 400
        assert refused.json()["code"] == "UPLOAD_SIZE_MISMATCH"


class TestRemovingIt:
    def test_deleting_takes_the_media_with_it(self, uploader, anonymous, unique_video):
        """Deleting used to leave every byte in storage."""
        video_id = upload_in_parts(uploader, unique_video)
        video = wait_until_ready(uploader.client, video_id)
        playlist_url = "/" + video["master_hls_url"].lstrip("/")

        assert anonymous.get(playlist_url).status_code == 200

        removed = uploader.client.delete(f"/api/files/videos/{video_id}")
        assert removed.status_code == 200

        assert uploader.client.get(f"/api/videos/{video_id}").status_code == 404
        assert anonymous.get(playlist_url).status_code in (403, 404)
