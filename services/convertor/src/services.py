import asyncio
import json
import logging
import math
import shutil
import subprocess
from pathlib import Path

from .exceptions import (
    DirectoryPrepareError,
    FFmpegExecutionError,
    FFmpegStartError,
    FFProbeError,
    InvalidMediaError,
)
from .renditions import LADDER, Rendition
from .schemas import VideoProperties

LOCAL_BASE = Path("/tmp/processing")


# ---------- Utility: safe mkdir / cleanup ----------
async def prepare_dirs(video_id: str) -> Path:
    base = LOCAL_BASE / video_id
    try:
        base.mkdir(parents=True, exist_ok=True)
        logging.debug(f"Created local dirs for {video_id}")
        return base
    except Exception as e:
        raise DirectoryPrepareError(video_id) from e


def cleanup_dirs(video_id: str) -> None:
    base = LOCAL_BASE / video_id
    if not base.exists():
        logging.warning(f"Cleanup skipped — {base} does not exist")
        return
    try:
        shutil.rmtree(base)
        logging.debug(f"Removed local dirs for {video_id}")
    except Exception as e:
        logging.error(f"Failed to cleanup local dirs for {video_id}, Error: {e}")
        raise DirectoryPrepareError(video_id) from e


def has_gpu() -> bool:
    try:
        subprocess.run(
            ["nvidia-smi"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        test_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=64x64:d=1",
            "-c:v",
            "h264_nvenc",
            "-f",
            "null",
            "-",
        ]
        subprocess.run(
            test_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except Exception:
        logging.warning(
            "NVENC initialization failed or GPU missing. Falling back to CPU encoding."
        )
        return False


def _filter_complex(ladder: tuple[Rendition, ...], use_gpu: bool) -> str:
    """One split into N branches, each scaled to a rendition. The CPU path
    pads to even dimensions because libx264 rejects odd sizes; scale_npp
    on the GPU path handles that itself."""
    n = len(ladder)
    branches = "".join(f"[v{i + 1}]" for i in range(n))
    parts = [f"[0:v]split={n}{branches}"]
    for i, r in enumerate(ladder):
        scale = "scale_npp" if use_gpu else "scale"
        chain = (
            f"[v{i + 1}]{scale}=w={r.width}:h={r.height}"
            ":force_original_aspect_ratio=decrease"
        )
        if not use_gpu:
            chain += ",pad=ceil(iw/2)*2:ceil(ih/2)*2"
        parts.append(f"{chain}[{r.label}]")
    return ";".join(parts)


def _codec_args(index: int, r: Rendition, vcodec: str) -> list[str]:
    i = str(index)
    return [
        "-map",
        f"[{r.label}]",
        "-map",
        "a:0?",
        f"-c:v:{i}",
        vcodec,
        f"-b:v:{i}",
        f"{r.video_kbps}k",
        f"-maxrate:v:{i}",
        f"{r.video_kbps}k",
        f"-bufsize:v:{i}",
        f"{r.bufsize_kbps}k",
        f"-c:a:{i}",
        "aac",
        f"-b:a:{i}",
        f"{r.audio_kbps}k",
    ]


def _var_stream_map(ladder: tuple[Rendition, ...], has_audio: bool) -> str:
    return " ".join(
        f"v:{i},a:{i},name:{r.name}" if has_audio else f"v:{i},name:{r.name}"
        for i, r in enumerate(ladder)
    )


async def stream_ffmpeg(
    url: str,
    output_dir: Path,
    fps: int,
    segment_duration: int = 3,
    has_audio: bool = True,
    force_cpu: bool = False,
) -> int:
    out_template = str(output_dir / "stream_%v" / "seg_%03d.ts")
    out_playlist = str(output_dir / "stream_%v" / "playlist.m3u8")

    gop_size = math.ceil(fps * segment_duration)
    logging.info(f"Calculated GOP size for -g parameter: {gop_size}")
    use_gpu = has_gpu() and not force_cpu

    # ---------- Common base command ----------
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-analyzeduration",
        "100M",
        "-probesize",
        "100M",
        "-y",
    ]

    # ---------- Input & hardware acceleration ----------
    if use_gpu:
        cmd += [
            "-hwaccel",
            "cuda",
            "-hwaccel_output_format",
            "cuda",
        ]
    cmd += ["-i", url]

    # ---------- Filter & scaling ----------
    cmd += ["-filter_complex", _filter_complex(LADDER, use_gpu)]

    # ---------- Codec setup ----------
    vcodec = "h264_nvenc" if use_gpu else "libx264"
    for index, rendition in enumerate(LADDER):
        cmd += _codec_args(index, rendition, vcodec)

    # ---------- Preset / Rate control ----------
    if use_gpu:
        for i in range(len(LADDER)):
            cmd += [f"-rc:v:{i}", "vbr", f"-preset:v:{i}", "p4"]
    else:
        cmd += ["-preset", "veryfast", "-tune", "zerolatency"]

    # ---------- Output ----------
    cmd += [
        "-f",
        "hls",
        "-g",
        str(gop_size),
        "-keyint_min",
        str(gop_size),
        "-sc_threshold",
        "0",
        "-hls_time",
        str(segment_duration),
        "-hls_playlist_type",
        "vod",
        "-hls_segment_filename",
        out_template,
        "-hls_flags",
        "independent_segments+split_by_time",
        "-master_pl_name",
        "master.m3u8",
        "-var_stream_map",
        _var_stream_map(LADDER, has_audio),
        out_playlist,
    ]
    try:
        process = await asyncio.create_subprocess_exec(*cmd, stderr=subprocess.PIPE)
    except Exception as e:
        raise FFmpegStartError() from e

    stderr_output = []

    async def log_stderr() -> None:
        if process.stderr is None:
            return
        while True:
            chunk = await process.stderr.read(1024)
            if not chunk:
                break
            decoded = chunk.decode(errors="ignore").strip()
            stderr_output.append(decoded)
            logging.debug("[ffmpeg stderr] %s", decoded)

    await log_stderr()
    rc = await process.wait()
    if rc != 0:
        tail = "\n".join(stderr_output[-5:]) if stderr_output else "No stderr output"
        raise FFmpegExecutionError(return_code=rc, stderr=tail)
    return rc


async def get_video_properties(url: str) -> VideoProperties:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-of",
        "json",
        url,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except Exception as e:
        raise FFProbeError(details="Failed to start ffprobe process") from e

    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        logging.error(f"ffprobe stderr: {stderr.decode(errors='ignore')}")
        raise FFProbeError(details=stderr.decode(errors="ignore"))

    try:
        info = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise FFProbeError(details="Failed to parse ffprobe JSON output") from e

    streams = info.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    if not video_stream:
        raise InvalidMediaError("No video stream found in the file")

    fps_fraction = video_stream.get("r_frame_rate", "0/1")
    num, den = map(int, fps_fraction.split("/"))
    fps = num / den if den else 0

    # Cast bit_rate safely
    bit_rate = video_stream.get("bit_rate", 0)
    try:
        bit_rate = int(bit_rate)
    except (ValueError, TypeError):
        bit_rate = 0

    return VideoProperties(
        fps=fps,
        width=video_stream.get("width", 0),
        height=video_stream.get("height", 0),
        bitrate=bit_rate // 1000 if bit_rate else 0,
        has_audio=has_audio,
    )


async def check_liveness(scope, receive, send):
    if scope["type"] == "http":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps({"status": "ok"}).encode("utf-8"),
            }
        )
