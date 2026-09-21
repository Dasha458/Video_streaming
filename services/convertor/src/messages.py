"""
Messages this service publishes. The shape is fixed by
contracts/video-encode-status.schema.json at the repository root; the test
in tests/test_contract.py fails if this model drifts from it.
"""

from typing import Literal

from pydantic import BaseModel


class ResolutionMeta(BaseModel):
    height: int
    width: int
    bitrate: int  # kbps
    playlist_path: str


class EncodeStatusMessage(BaseModel):
    video_id: str
    status: Literal["processing", "ready", "failed"]
    resolutions: list[ResolutionMeta] | None = None
    video_path: str | None = None

    def payload(self) -> dict:
        """Wire form: optional fields are omitted, not sent as null."""
        return self.model_dump(exclude_none=True)
