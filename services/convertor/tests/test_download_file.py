"""
The file the Download button hands over.

It could not hand over a playable file by any route. Asked for a
resolution the backend returned the .m3u8 playlist with a .mp4 name --
a few hundred bytes of text saved as a video. Asked for the original it
looked for a key the converter deletes as soon as the encode succeeds.
Both ends were broken, so nobody noticed either.

The fix is a remux: the segments are already H.264 and AAC, so they are
copied into an MP4 container rather than encoded again.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.exceptions import FFmpegExecutionError
from src.services import DOWNLOAD_NAME, _download_source, build_download_file


def _rendition(base: Path, name: str) -> Path:
    playlist = base / f"stream_{name}" / "playlist.m3u8"
    playlist.parent.mkdir(parents=True, exist_ok=True)
    playlist.write_text("#EXTM3U\n")
    return playlist


def _process(returncode: int = 0, stderr: bytes = b""):
    process = MagicMock()
    process.stderr = MagicMock()
    process.stderr.read = AsyncMock(return_value=stderr)
    process.wait = AsyncMock(return_value=returncode)
    return process


def _ffmpeg_that_writes(base: Path, returncode: int = 0):
    """Stand in for ffmpeg, including the file it leaves behind.

    Without the file the caller is right to refuse: ffmpeg exits 0 having
    written nothing often enough that success has to mean a file exists.
    """

    def run(*cmd, **kwargs):
        if returncode == 0:
            (base / DOWNLOAD_NAME).write_bytes(b"not really an mp4")
        return _process(returncode)

    return run


class TestWhichRenditionIsUsed:
    def test_720p_when_it_exists(self, tmp_path: Path):
        _rendition(tmp_path, "360p")
        _rendition(tmp_path, "720p")
        _rendition(tmp_path, "1080p")

        assert _download_source(tmp_path).parent.name == "stream_720p"

    def test_the_highest_available_when_the_source_was_smaller(self, tmp_path: Path):
        """A 480-line source never produces a 720p rendition -- upscaling
        would be inventing detail -- and the button still has to work."""
        _rendition(tmp_path, "360p")

        assert _download_source(tmp_path).parent.name == "stream_360p"

    def test_nothing_when_the_encode_produced_nothing(self, tmp_path: Path):
        assert _download_source(tmp_path) is None


class TestBuildingTheFile:
    @pytest.mark.asyncio
    async def test_it_copies_rather_than_re_encodes(self, tmp_path: Path):
        """A re-encode would cost minutes of CPU per video and lose
        quality for a file that is already in the right codecs."""
        _rendition(tmp_path, "720p")

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_ffmpeg_that_writes(tmp_path),
        ) as spawned:
            await build_download_file(tmp_path, has_audio=True)

        cmd = spawned.call_args.args
        assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"
        assert "+faststart" in cmd, "the index must be at the front to play while loading"
        assert cmd[-1].endswith(DOWNLOAD_NAME)

    @pytest.mark.asyncio
    async def test_the_audio_headers_are_converted(self, tmp_path: Path):
        """MPEG-TS carries ADTS headers that MP4 does not understand; the
        file plays silently without this."""
        _rendition(tmp_path, "720p")

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_ffmpeg_that_writes(tmp_path),
        ) as spawned:
            await build_download_file(tmp_path, has_audio=True)

        assert "aac_adtstoasc" in spawned.call_args.args

    @pytest.mark.asyncio
    async def test_a_silent_video_does_not_ask_for_an_audio_filter(
        self, tmp_path: Path
    ):
        _rendition(tmp_path, "720p")

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_ffmpeg_that_writes(tmp_path),
        ) as spawned:
            await build_download_file(tmp_path, has_audio=False)

        assert "aac_adtstoasc" not in spawned.call_args.args

    @pytest.mark.asyncio
    async def test_nothing_to_build_from_is_not_an_error(self, tmp_path: Path):
        """The encode failing is the encode's business to report."""
        with patch("asyncio.create_subprocess_exec") as spawned:
            assert await build_download_file(tmp_path) is None

        spawned.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_failed_remux_is_raised_not_swallowed(self, tmp_path: Path):
        """Returning quietly here would publish a video whose Download
        button leads to a key that does not exist."""
        _rendition(tmp_path, "720p")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=_process(returncode=1, stderr=b"Invalid data found"),
        ):
            with pytest.raises(FFmpegExecutionError) as failure:
                await build_download_file(tmp_path)

        assert "Invalid data found" in str(failure.value)
