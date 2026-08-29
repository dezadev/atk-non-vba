"""Shared immutable data models for the application."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaInfo:
    duration: float | None


@dataclass(frozen=True)
class DownloadItem:
    title: str
    url: str


@dataclass(frozen=True)
class MediaPair:
    """One independently rendered video and its optional replacement audio."""

    video: Path
    audio: Path | None = None


@dataclass(frozen=True)
class PairMergeJob:
    """A prepared FFmpeg job for the per-file merge mode."""

    video: Path
    audio: Path
    output: Path
    command: list[str]
    expected_duration: float | None
