"""
Pins what this service publishes to contracts/video-encode-status.schema.json
(repository root). If the model or the ladder drifts from the contract, this
fails here; the backend has the mirror test against the same file.
"""

import json
from pathlib import Path

import jsonschema
import pytest

from src.messages import EncodeStatusMessage
from src.renditions import LADDER

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
SCHEMA = json.loads((CONTRACTS / "video-encode-status.schema.json").read_text())
VIDEO_ID = "1b4e28ba-2fa1-11d2-883f-0016d3cca427"


def _validate(payload: dict) -> None:
    jsonschema.Draft202012Validator(SCHEMA).validate(payload)


def test_processing_message_matches_contract():
    _validate(EncodeStatusMessage(video_id=VIDEO_ID, status="processing").payload())


def test_failed_message_matches_contract():
    _validate(EncodeStatusMessage(video_id=VIDEO_ID, status="failed").payload())


def test_ready_message_with_full_ladder_matches_contract():
    msg = EncodeStatusMessage(
        video_id=VIDEO_ID,
        status="ready",
        resolutions=[r.as_message(VIDEO_ID) for r in LADDER],
        video_path=f"minio/videos/{VIDEO_ID}/master.m3u8",
    )
    _validate(msg.payload())


def test_optional_fields_are_omitted_not_null():
    """The schema forbids null; a bare status message must not carry
    resolutions/video_path keys at all."""
    assert EncodeStatusMessage(video_id=VIDEO_ID, status="failed").payload() == {
        "video_id": VIDEO_ID,
        "status": "failed",
    }


def test_shared_examples_are_what_this_service_would_send():
    examples = json.loads((CONTRACTS / "video-encode-status.examples.json").read_text())
    for example in examples:
        _validate(example)
        # Round-trip through our model must reproduce the example exactly.
        assert EncodeStatusMessage.model_validate(example).payload() == example


def test_unknown_status_is_rejected_by_the_model():
    with pytest.raises(Exception):
        EncodeStatusMessage(video_id=VIDEO_ID, status="done")  # type: ignore[arg-type]
