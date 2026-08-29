"""yt-dlp command construction and playlist parsing."""
from __future__ import annotations

import json
from pathlib import Path

from atk.models import DownloadItem


def build_youtube_playlist_command(yt_dlp: str, url: str, output_dir: Path, media_format: str) -> list[str]:
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("URL playlist YouTube belum diisi.")
    download_dir = output_dir.expanduser().resolve()
    if not download_dir.is_dir():
        raise ValueError(f"Folder download tidak ditemukan: {download_dir}")
    command = [yt_dlp, "--yes-playlist", "--ignore-errors", "--newline", "--progress-template", "download:%(progress._percent_str)s", "-P", str(download_dir), "-o", "%(playlist_index|)s-%(title).200B.%(ext)s"]
    if media_format == "audio":
        command.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
    elif media_format == "video":
        command.extend(["--merge-output-format", "mp4", "-f", "bv*+ba/b"])
    else:
        raise ValueError("Format download harus 'video' atau 'audio'.")
    return [*command, clean_url]


def build_youtube_item_command(yt_dlp: str, url: str, output_dir: Path, media_format: str) -> list[str]:
    command = build_youtube_playlist_command(yt_dlp, url, output_dir, media_format)
    command[1] = "--no-playlist"
    return command


def build_youtube_playlist_probe_command(yt_dlp: str, url: str) -> list[str]:
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("URL playlist YouTube belum diisi.")
    return [yt_dlp, "--flat-playlist", "--dump-single-json", clean_url]


def parse_youtube_playlist_items(metadata_json: str) -> list[DownloadItem]:
    data = json.loads(metadata_json)
    items: list[DownloadItem] = []
    for index, entry in enumerate(data.get("entries") or [], start=1):
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or f"Item {index}")
        url = entry.get("webpage_url") or entry.get("url")
        if not url and entry.get("id"):
            url = f"https://www.youtube.com/watch?v={entry['id']}"
        if url:
            items.append(DownloadItem(title=title, url=str(url)))
    return items
