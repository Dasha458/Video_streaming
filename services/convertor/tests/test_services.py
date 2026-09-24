"""
Comprehensive tests for convertor service functions.
Tests: prepare_dirs, cleanup_dirs, has_gpu, get_video_properties, stream_ffmpeg.
"""

import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.exceptions import (
    FFmpegExecutionError,
    FFmpegStartError,
    FFProbeError,
    InvalidMediaError,
)
from src.schemas import VideoProperties
from src.services import (
    cleanup_dirs,
    get_video_properties,
    has_gpu,
    prepare_dirs,
    stream_ffmpeg,
)

# ─────────────────────────────────────────────────────────────────────────────
# prepare_dirs / cleanup_dirs (filesystem — no mocks needed)
# ─────────────────────────────────────────────────────────────────────────────


async def test_prepare_dirs_creates_directory():
    vid = "test_prep_001"
    path = await prepare_dirs(vid)
    try:
        assert path.exists()
        assert path.is_dir()
    finally:
        cleanup_dirs(vid)


async def test_cleanup_dirs_removes_directory():
    vid = "test_cleanup_001"
    path = await prepare_dirs(vid)
    assert path.exists()
    cleanup_dirs(vid)
    assert not path.exists()


async def test_prepare_dirs_idempotent():
    """Calling prepare_dirs twice for the same ID must not raise."""
    vid = "test_idempotent_001"
    try:
        path1 = await prepare_dirs(vid)
        path2 = await prepare_dirs(vid)
        assert path1 == path2
        assert path1.exists()
    finally:
        cleanup_dirs(vid)


def test_cleanup_dirs_nonexistent_does_not_raise():
    """cleanup_dirs on a non-existent path must not raise."""
    cleanup_dirs("video_that_was_never_created_xyz")


async def test_prepare_and_cleanup_dirs():
    """Original test — kept for backwards compatibility."""
    vid = "testvid"
    path = await prepare_dirs(vid)
    assert path.exists()
    cleanup_dirs(vid)
    assert not path.exists()


# ─────────────────────────────────────────────────────────────────────────────
# has_gpu — mocks subprocess.run
# ─────────────────────────────────────────────────────────────────────────────


def test_has_gpu_returns_true_when_nvenc_available():
    """Both nvidia-smi and ffmpeg h264_nvenc succeed → True."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = has_gpu()
    assert result is True


def test_has_gpu_returns_false_when_nvidia_smi_fails():
    """nvidia-smi raises CalledProcessError → False."""
    with patch(
        "subprocess.run", side_effect=subprocess.CalledProcessError(1, "nvidia-smi")
    ):
        result = has_gpu()
    assert result is False


def test_has_gpu_returns_false_when_ffmpeg_nvenc_fails():
    """nvidia-smi passes but ffmpeg h264_nvenc fails → False."""
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(returncode=0)  # nvidia-smi OK
        raise subprocess.CalledProcessError(1, "ffmpeg")  # nvenc test fails

    with patch("subprocess.run", side_effect=side_effect):
        result = has_gpu()
    assert result is False


def test_has_gpu_returns_false_on_any_exception():
    """Any unexpected exception → False (safe fallback)."""
    with patch("subprocess.run", side_effect=OSError("ffmpeg not found")):
        result = has_gpu()
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# get_video_properties — mocks asyncio.create_subprocess_exec
# ─────────────────────────────────────────────────────────────────────────────


def _make_ffprobe_output(
    width=1280, height=720, fps="30/1", bitrate="2000000", has_audio=True
):
    streams = [
        {
            "codec_type": "video",
            "width": width,
            "height": height,
            "r_frame_rate": fps,
            "bit_rate": str(bitrate),
        }
    ]
    if has_audio:
        streams.append({"codec_type": "audio"})
    return json.dumps({"streams": streams}).encode()


def _mock_process(stdout: bytes, returncode: int = 0):
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    return proc


async def test_get_video_properties_basic():
    """Returns correct VideoProperties for a standard 720p video."""
    output = _make_ffprobe_output(width=1280, height=720, fps="30/1", bitrate="2000000")
    with patch("asyncio.create_subprocess_exec", return_value=_mock_process(output)):
        props = await get_video_properties("http://example.com/video.mp4")

    assert isinstance(props, VideoProperties)
    assert props.width == 1280
    assert props.height == 720
    assert props.fps == pytest.approx(30.0)
    assert props.has_audio is True
    assert props.bitrate == 2000  # 2000000 // 1000


async def test_get_video_properties_no_audio():
    """has_audio is False when no audio stream is present."""
    output = _make_ffprobe_output(has_audio=False)
    with patch("asyncio.create_subprocess_exec", return_value=_mock_process(output)):
        props = await get_video_properties("http://example.com/video.mp4")

    assert props.has_audio is False


async def test_get_video_properties_fractional_fps():
    """fps=25/1 → 25.0; fps=30000/1001 → ~29.97."""
    output = _make_ffprobe_output(fps="30000/1001")
    with patch("asyncio.create_subprocess_exec", return_value=_mock_process(output)):
        props = await get_video_properties("http://example.com/video.mp4")

    assert props.fps == pytest.approx(29.97, abs=0.01)


async def test_get_video_properties_raises_ffprobe_error_on_failure():
    """Non-zero returncode raises FFProbeError."""
    proc = AsyncMock()
    proc.returncode = 1
    proc.communicate = AsyncMock(return_value=(b"", b"Input/output error"))
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(FFProbeError):
            await get_video_properties("http://example.com/bad.mp4")


async def test_get_video_properties_raises_invalid_media_when_no_video_stream():
    """JSON with no video streams raises InvalidMediaError."""
    output = json.dumps({"streams": [{"codec_type": "audio"}]}).encode()
    with patch("asyncio.create_subprocess_exec", return_value=_mock_process(output)):
        with pytest.raises(InvalidMediaError):
            await get_video_properties("http://example.com/audio_only.mp3")


async def test_get_video_properties_raises_ffprobe_error_on_invalid_json():
    """Malformed ffprobe JSON output raises FFProbeError."""
    with patch(
        "asyncio.create_subprocess_exec", return_value=_mock_process(b"not-json")
    ):
        with pytest.raises(FFProbeError):
            await get_video_properties("http://example.com/video.mp4")


async def test_get_video_properties_handles_missing_bitrate():
    """Missing bit_rate key in stream → bitrate defaults to 0."""
    streams = [
        {"codec_type": "video", "width": 640, "height": 480, "r_frame_rate": "24/1"}
    ]
    output = json.dumps({"streams": streams}).encode()
    with patch("asyncio.create_subprocess_exec", return_value=_mock_process(output)):
        props = await get_video_properties("http://example.com/video.mp4")

    assert props.bitrate == 0


# ─────────────────────────────────────────────────────────────────────────────
# stream_ffmpeg — mocks subprocess + asyncio subprocess
# ─────────────────────────────────────────────────────────────────────────────


def _mock_ffmpeg_process(returncode: int = 0, stderr_chunks: list = None):
    """Returns an AsyncMock mimicking asyncio.subprocess.Process for ffmpeg."""
    proc = AsyncMock()
    proc.returncode = returncode

    chunks = list(stderr_chunks or [])
    chunks.append(b"")  # EOF sentinel

    async def read(n):
        return chunks.pop(0) if chunks else b""

    proc.stderr = AsyncMock()
    proc.stderr.read = read
    proc.wait = AsyncMock(return_value=returncode)
    return proc


async def test_stream_ffmpeg_cpu_success(tmp_path):
    """stream_ffmpeg completes with CPU codec (force_cpu=True, returncode=0)."""
    proc = _mock_ffmpeg_process(returncode=0)
    with (
        patch("asyncio.create_subprocess_exec", return_value=proc),
        patch("src.services.has_gpu", return_value=False),
    ):
        rc = await stream_ffmpeg(
            url="http://example.com/input.mp4",
            output_dir=tmp_path,
            fps=30,
            force_cpu=True,
        )
    assert rc == 0


async def test_stream_ffmpeg_raises_ffmpeg_execution_error_on_nonzero_rc(tmp_path):
    """Non-zero ffmpeg returncode raises FFmpegExecutionError."""
    proc = _mock_ffmpeg_process(returncode=1, stderr_chunks=[b"error: bad codec"])
    with (
        patch("asyncio.create_subprocess_exec", return_value=proc),
        patch("src.services.has_gpu", return_value=False),
    ):
        with pytest.raises(FFmpegExecutionError) as exc_info:
            await stream_ffmpeg(
                url="http://example.com/input.mp4",
                output_dir=tmp_path,
                fps=25,
                force_cpu=True,
            )
    assert exc_info.value.return_code == 1


async def test_stream_ffmpeg_raises_ffmpeg_start_error_when_exec_fails(tmp_path):
    """OSError when starting ffmpeg raises FFmpegStartError."""
    with (
        patch(
            "asyncio.create_subprocess_exec", side_effect=OSError("ffmpeg not found")
        ),
        patch("src.services.has_gpu", return_value=False),
    ):
        with pytest.raises(FFmpegStartError):
            await stream_ffmpeg(
                url="http://example.com/input.mp4",
                output_dir=tmp_path,
                fps=30,
                force_cpu=True,
            )


async def test_stream_ffmpeg_no_audio_flag(tmp_path):
    """stream_ffmpeg with has_audio=False still completes successfully."""
    proc = _mock_ffmpeg_process(returncode=0)
    with (
        patch("asyncio.create_subprocess_exec", return_value=proc),
        patch("src.services.has_gpu", return_value=False),
    ):
        rc = await stream_ffmpeg(
            url="http://example.com/input.mp4",
            output_dir=tmp_path,
            fps=24,
            has_audio=False,
            force_cpu=True,
        )
    assert rc == 0
