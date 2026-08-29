"""FFmpeg command construction and media metadata helpers."""
from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path

from atk.models import MediaInfo
from atk.tools import find_tool, run_command


def probe_duration(path: Path) -> MediaInfo:
    """Read media duration using ffprobe when available."""
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return MediaInfo(duration=None)
    result = run_command([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    if result.returncode != 0:
        return MediaInfo(duration=None)
    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return MediaInfo(duration=None)
    return MediaInfo(duration=duration)


def write_concat_list(paths: Sequence[Path]) -> Path:
    """Create a temporary FFmpeg concat-demuxer list for many media files."""
    fd, name = tempfile.mkstemp(prefix="ffmpeg_concat_", suffix=".txt", text=True)
    with open(fd, "w", encoding="utf-8") as file:
        for path in paths:
            safe_path = str(path.resolve()).replace("'", "'\\''")
            file.write(f"file '{safe_path}'\n")
    return Path(name)


def media_input_args(path: Path, is_concat_list: bool) -> list[str]:
    return ["-i", str(path)] if not is_concat_list else ["-f", "concat", "-safe", "0", "-i", str(path)]


def build_looped_input_args(video_input: Path, audio_input: Path, duration_mode: str, *, video_is_concat_list: bool = False, audio_is_concat_list: bool = False) -> list[str]:
    """Build FFmpeg input arguments with fast packet-level looping."""
    args: list[str] = []
    if duration_mode == "audio":
        args.extend(["-stream_loop", "-1"])
    args.extend(media_input_args(video_input, video_is_concat_list))
    if duration_mode == "video":
        args.extend(["-stream_loop", "-1"])
    args.extend(media_input_args(audio_input, audio_is_concat_list))
    return args


def total_duration(paths: Sequence[Path]) -> float | None:
    total = 0.0
    for path in paths:
        duration = probe_duration(path).duration
        if duration is None:
            return None
        total += duration
    return total


def display_media_name(path: str | Path) -> str:
    return re.split(r"[/\\\\]+", str(path))[-1]


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "durasi tidak terbaca"
    rounded = int(round(seconds))
    hours, remainder = divmod(rounded, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
