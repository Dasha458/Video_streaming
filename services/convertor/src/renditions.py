"""
The HLS rendition ladder -- the single place that says what this service
encodes. ffmpeg's filter graph, its per-stream codec flags, the
var_stream_map and the metadata published back to the backend are all
derived from LADDER, so they cannot disagree with each other.
"""

from dataclasses import dataclass

from .messages import ResolutionMeta


@dataclass(frozen=True)
class Rendition:
    height: int
    width: int
    video_kbps: int
    audio_kbps: int

    @property
    def name(self) -> str:
        """Stream name used by var_stream_map and the stream_<name>/ directory."""
        return f"{self.height}p"

    @property
    def label(self) -> str:
        """ffmpeg filter pad label, e.g. [v720]."""
        return f"v{self.height}"

    @property
    def bufsize_kbps(self) -> int:
        # 1.5x the target bitrate is the usual VBV buffer for CBR-ish HLS.
        return int(self.video_kbps * 1.5)

    def playlist_path(self, video_id: str) -> str:
        return f"{video_id}/stream_{self.name}/playlist.m3u8"

    def as_message(self, video_id: str) -> ResolutionMeta:
        return ResolutionMeta(
            height=self.height,
            width=self.width,
            bitrate=self.video_kbps,
            playlist_path=self.playlist_path(video_id),
        )


LADDER: tuple[Rendition, ...] = (
    Rendition(height=360, width=640, video_kbps=800, audio_kbps=96),
    Rendition(height=720, width=1280, video_kbps=2000, audio_kbps=128),
    Rendition(height=1080, width=1920, video_kbps=5000, audio_kbps=192),
)
