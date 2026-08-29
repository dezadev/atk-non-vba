"""Rules and FFmpeg preparation for independent video/audio pairs."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from atk.media.ffmpeg import build_looped_input_args, display_media_name, probe_duration
from atk.models import MediaPair


def expected_pair_duration(video: Path, audio: Path, duration_mode: str) -> float | None:
    """Return the expected duration for one pair, probing each input once."""
    video_duration = probe_duration(video).duration
    audio_duration = probe_duration(audio).duration
    if duration_mode == "video":
        return video_duration
    if duration_mode == "audio":
        return audio_duration
    return min(video_duration, audio_duration) if video_duration is not None and audio_duration is not None else None


def pair_output_paths(pairs: Sequence[MediaPair], output_dir: Path) -> list[Path]:
    """Create deterministic, non-colliding output names based on each video."""
    used_names: set[str] = set()
    outputs: list[Path] = []
    for pair in pairs:
        base_name = f"{pair.video.stem}_gabung_audio"
        candidate = f"{base_name}.mp4"
        number = 2
        while candidate.casefold() in used_names:
            candidate = f"{base_name}_{number}.mp4"
            number += 1
        used_names.add(candidate.casefold())
        outputs.append(output_dir / candidate)
    return outputs


def build_pair_ffmpeg_command(ffmpeg: str, pair: MediaPair, output: Path, duration_mode: str, video_volume: int, audio_volume: int, overwrite: bool) -> tuple[list[str], float | None]:
    """Build the fast stream-copy FFmpeg command for a single media pair."""
    if pair.audio is None:
        raise ValueError(f"Audio untuk {display_media_name(pair.video)} belum dipilih.")
    command = [ffmpeg, "-y" if overwrite else "-n"]
    command.extend(build_looped_input_args(pair.video, pair.audio, duration_mode))
    video_gain = video_volume / 100
    audio_gain = audio_volume / 100
    filters: list[str] = []
    audio_inputs: list[str] = []
    if video_gain > 0:
        filters.append(f"[0:a]volume={video_gain:.2f}[vold]")
        audio_inputs.append("[vold]")
    filters.append(f"[1:a]volume={audio_gain:.2f}[anew]")
    audio_inputs.append("[anew]")
    filters.append(f"{''.join(audio_inputs)}amix=inputs={len(audio_inputs)}:duration=longest:dropout_transition=0[aout]")
    command.extend(["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[aout]", "-progress", "pipe:1", "-nostats", "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)])
    return command, expected_pair_duration(pair.video, pair.audio, duration_mode)
