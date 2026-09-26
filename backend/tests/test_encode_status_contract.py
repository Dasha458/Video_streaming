"""
Mirror of services/convertor/tests/test_contract.py: the backend's
StatusMessage must accept exactly what the convertor promises to send,
as pinned in contracts/video-encode-status.schema.json.
"""

import json
from pathlib import Path

import pytest

from src.events.endpoint import StatusMessage

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SCHEMA = json.loads((CONTRACTS / "video-encode-status.schema.json").read_text())
EXAMPLES = json.loads((CONTRACTS / "video-encode-status.examples.json").read_text())


@pytest.mark.parametrize("example", EXAMPLES, ids=[e["status"] for e in EXAMPLES])
def test_every_contract_example_parses(example: dict) -> None:
    msg = StatusMessage.model_validate(example)
    assert str(msg.video_id) == example["video_id"]
    assert msg.status == example["status"]
    if "resolutions" in example:
        assert msg.resolutions is not None
        assert [r.model_dump() for r in msg.resolutions] == example["resolutions"]
        assert msg.video_path == example["video_path"]


def test_backend_requires_nothing_the_contract_does_not_promise() -> None:
    """Every field StatusMessage insists on must be `required` in the schema;
    otherwise a valid convertor message could be rejected here."""
    required_here = {
        name for name, f in StatusMessage.model_fields.items() if f.is_required()
    }
    assert required_here <= set(SCHEMA["required"])


def test_backend_knows_every_contract_field() -> None:
    """A field the convertor may send but the backend doesn't model would be
    silently dropped -- surface that as a failing test instead."""
    assert set(SCHEMA["properties"]) <= set(StatusMessage.model_fields)


def test_every_contract_status_maps_to_a_db_status() -> None:
    from src.core.status_ids import status_id_for

    for status in SCHEMA["properties"]["status"]["enum"]:
        assert status_id_for(status) is not None, status
