"""
The ffmpeg argument builders are derived from src/renditions.LADDER. These
pin them to the exact strings the service produced before the ladder was
centralised, so the refactor is provably byte-for-byte neutral for ffmpeg,
and pin the published metadata to what ffmpeg actually encodes.
"""

from src.renditions import LADDER
from src.services import _codec_args, _filter_complex, _var_stream_map


def test_gpu_filter_graph_is_unchanged():
    assert _filter_complex(LADDER, use_gpu=True) == (
        "[0:v]split=3[v1][v2][v3];"
        "[v1]scale_npp=w=640:h=360:force_original_aspect_ratio=decrease[v360];"
        "[v2]scale_npp=w=1280:h=720:force_original_aspect_ratio=decrease[v720];"
        "[v3]scale_npp=w=1920:h=1080:force_original_aspect_ratio=decrease[v1080]"
    )


def test_cpu_filter_graph_is_unchanged():
    assert _filter_complex(LADDER, use_gpu=False) == (
        "[0:v]split=3[v1][v2][v3];"
        "[v1]scale=w=640:h=360:force_original_aspect_ratio=decrease,"
        "pad=ceil(iw/2)*2:ceil(ih/2)*2[v360];"
        "[v2]scale=w=1280:h=720:force_original_aspect_ratio=decrease,"
        "pad=ceil(iw/2)*2:ceil(ih/2)*2[v720];"
        "[v3]scale=w=1920:h=1080:force_original_aspect_ratio=decrease,"
        "pad=ceil(iw/2)*2:ceil(ih/2)*2[v1080]"
    )


def test_var_stream_map_with_and_without_audio():
    assert (
        _var_stream_map(LADDER, has_audio=True)
        == "v:0,a:0,name:360p v:1,a:1,name:720p v:2,a:2,name:1080p"
    )
    assert (
        _var_stream_map(LADDER, has_audio=False)
        == "v:0,name:360p v:1,name:720p v:2,name:1080p"
    )


def test_codec_args_are_unchanged():
    args = [a for i, r in enumerate(LADDER) for a in _codec_args(i, r, "libx264")]
    # fmt: off
    assert args == [
        "-map", "[v360]", "-map", "a:0?", "-c:v:0", "libx264",
        "-b:v:0", "800k", "-maxrate:v:0", "800k", "-bufsize:v:0", "1200k",
        "-c:a:0", "aac", "-b:a:0", "96k",
        "-map", "[v720]", "-map", "a:0?", "-c:v:1", "libx264",
        "-b:v:1", "2000k", "-maxrate:v:1", "2000k", "-bufsize:v:1", "3000k",
        "-c:a:1", "aac", "-b:a:1", "128k",
        "-map", "[v1080]", "-map", "a:0?", "-c:v:2", "libx264",
        "-b:v:2", "5000k", "-maxrate:v:2", "5000k", "-bufsize:v:2", "7500k",
        "-c:a:2", "aac", "-b:a:2", "192k",
    ]
    # fmt: on


def test_published_metadata_matches_what_ffmpeg_encodes():
    """Before the ladder existed, main.py published 854x360 @ 1200k,
    1280x720 @ 2500k and 1920x1080 @ 4500k while ffmpeg encoded 640x360 @
    800k, 1280x720 @ 2000k and 1920x1080 @ 5000k. Now there is one source."""
    msgs = [r.as_message("vid") for r in LADDER]
    assert msgs == [
        {
            "height": 360,
            "width": 640,
            "bitrate": 800,
            "playlist_path": "vid/stream_360p/playlist.m3u8",
        },
        {
            "height": 720,
            "width": 1280,
            "bitrate": 2000,
            "playlist_path": "vid/stream_720p/playlist.m3u8",
        },
        {
            "height": 1080,
            "width": 1920,
            "bitrate": 5000,
            "playlist_path": "vid/stream_1080p/playlist.m3u8",
        },
    ]
