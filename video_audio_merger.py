#!/usr/bin/env python3
"""A desktop app to merge media with FFmpeg and download YouTube playlists.

Targeted for Python 3.14+ and uses only the standard library plus installed
``ffmpeg`` and optional ``yt-dlp`` executables. The UI is intentionally compact
and Indonesian-language for easy local use.
"""
from __future__ import annotations

import json
import queue
import random
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from tkinter import END, EXTENDED, BooleanVar, DoubleVar, IntVar, Listbox, StringVar, Tk, filedialog, messagebox, ttk
from typing import Iterable, Sequence

APP_TITLE = "Toolkit Video & Audio (FFmpeg + yt-dlp)"
VIDEO_EXTENSIONS = (("Video", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"), ("Semua file", "*.*"))
AUDIO_EXTENSIONS = (("Audio", "*.mp3 *.wav *.aac *.m4a *.ogg *.flac"), ("Semua file", "*.*"))
OUTPUT_EXTENSIONS = (("MP4", "*.mp4"), ("MKV", "*.mkv"), ("Semua file", "*.*"))


@dataclass(frozen=True)
class MediaInfo:
    duration: float | None


@dataclass(frozen=True)
class DownloadItem:
    title: str
    url: str


def find_tool(name: str) -> str | None:
    """Return the executable path when a command exists in PATH."""
    return shutil.which(name)


def run_command(command: Iterable[str]) -> subprocess.CompletedProcess[str]:
    """Run a command without opening a console window on Windows."""
    startupinfo = None
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
        startupinfo=startupinfo,
    )


def probe_duration(path: Path) -> MediaInfo:
    """Read media duration using ffprobe when available."""
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return MediaInfo(duration=None)

    result = run_command([
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ])
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
    if not is_concat_list:
        return ["-i", str(path)]
    return ["-f", "concat", "-safe", "0", "-i", str(path)]


def build_looped_input_args(
    video_input: Path,
    audio_input: Path,
    duration_mode: str,
    *,
    video_is_concat_list: bool = False,
    audio_is_concat_list: bool = False,
) -> list[str]:
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


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "durasi tidak terbaca"
    rounded = int(round(seconds))
    hours, remainder = divmod(rounded, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def build_youtube_playlist_command(yt_dlp: str, url: str, output_dir: Path, media_format: str) -> list[str]:
    """Build a yt-dlp command for downloading a YouTube playlist."""
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("URL playlist YouTube belum diisi.")
    download_dir = output_dir.expanduser().resolve()
    if not download_dir.is_dir():
        raise ValueError(f"Folder download tidak ditemukan: {download_dir}")

    output_template = "%(playlist_index|)s-%(title).200B.%(ext)s"
    command = [
        yt_dlp,
        "--yes-playlist",
        "--ignore-errors",
        "--newline",
        "--progress-template",
        "download:%(progress._percent_str)s",
        "-P",
        str(download_dir),
        "-o",
        output_template,
    ]
    if media_format == "audio":
        command.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
    elif media_format == "video":
        command.extend(["--merge-output-format", "mp4", "-f", "bv*+ba/b"])
    else:
        raise ValueError("Format download harus 'video' atau 'audio'.")
    command.append(clean_url)
    return command


def build_youtube_item_command(yt_dlp: str, url: str, output_dir: Path, media_format: str) -> list[str]:
    """Build a yt-dlp command for downloading one queued media item."""
    command = build_youtube_playlist_command(yt_dlp, url, output_dir, media_format)
    command[1] = "--no-playlist"
    return command


def build_youtube_playlist_probe_command(yt_dlp: str, url: str) -> list[str]:
    """Build a yt-dlp command that lists playlist entries without downloading media."""
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("URL playlist YouTube belum diisi.")
    return [yt_dlp, "--flat-playlist", "--dump-single-json", clean_url]


def parse_youtube_playlist_items(metadata_json: str) -> list[DownloadItem]:
    """Parse yt-dlp flat playlist JSON into per-video queue items."""
    data = json.loads(metadata_json)
    entries = data.get("entries") or []
    items: list[DownloadItem] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or f"Item {index}")
        url = entry.get("webpage_url") or entry.get("url")
        if not url and entry.get("id"):
            url = f"https://www.youtube.com/watch?v={entry['id']}"
        if url:
            items.append(DownloadItem(title=title, url=str(url)))
    return items


class MergerApp:
    """Tkinter UI for merging media and downloading YouTube playlists."""

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x680")
        self.root.minsize(640, 460)

        self.video_files: list[Path] = []
        self.audio_files: list[Path] = []
        self.video_path = StringVar()
        self.audio_path = StringVar()
        self.output_path = StringVar()
        self.video_list: Listbox | None = None
        self.audio_list: Listbox | None = None
        self.download_queue_list: Listbox | None = None
        self.downloaded_list: Listbox | None = None
        self.download_queue_items: list[DownloadItem] = []
        self.downloaded_items: list[DownloadItem] = []
        self.playlist_url = StringVar()
        self.download_dir = StringVar(value=str(Path.home() / "Downloads"))
        self.download_format = StringVar(value="video")
        self.duration_mode = StringVar(value="shortest")
        self.video_volume = IntVar(value=0)
        self.audio_volume = IntVar(value=100)
        self.overwrite = BooleanVar(value=True)
        self.status = StringVar(value="Pilih file video dan audio untuk mulai.")
        self.progress = DoubleVar(value=0)
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self._poll_log_queue()
        self._check_tools()

    def _build_ui(self) -> None:
        self.root.rowconfigure(0, weight=3)
        self.root.rowconfigure(1, weight=2)
        self.root.columnconfigure(0, weight=1)

        main_pane = ttk.PanedWindow(self.root, orient="vertical")
        main_pane.grid(row=0, column=0, rowspan=2, sticky="nsew")

        notebook = ttk.Notebook(main_pane)
        status_frame = ttk.Frame(main_pane, padding=(12, 8, 12, 12))
        main_pane.add(notebook, weight=4)
        main_pane.add(status_frame, weight=1)

        merge_tab = ttk.Frame(notebook, padding=12)
        download_tab = ttk.Frame(notebook, padding=12)
        notebook.add(merge_tab, text="Gabung Media")
        notebook.add(download_tab, text="Download YouTube")

        self._build_merge_tab(merge_tab)
        self._build_download_tab(download_tab)
        self._build_progress_and_log(status_frame, start_row=0)

    def _build_merge_tab(self, main: ttk.Frame) -> None:
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        title = ttk.Label(main, text="Penggabung Video & Audio", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        subtitle = ttk.Label(main, text="Kelola daftar video/audio, acak urutan bila perlu, lalu gabungkan.")
        subtitle.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self.video_list = self._media_list_panel(
            main, 2, 0, "Daftar Video", self._add_video_files, self._remove_selected_videos, self._shuffle_videos
        )
        self.audio_list = self._media_list_panel(
            main, 2, 1, "Daftar Audio", self._add_audio_files, self._remove_selected_audios, self._shuffle_audios
        )

        output_row = ttk.Frame(main)
        output_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        output_row.columnconfigure(1, weight=1)
        self._file_row(output_row, 0, "Output", self.output_path, self._choose_output)

        options = ttk.LabelFrame(main, text="Penyesuaian durasi", padding=10)
        options.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 6))
        for value, text in (
            ("shortest", "Selesai di durasi terpendek (audio/video dipotong otomatis)"),
            ("video", "Ikuti durasi video (audio dipotong atau diulang sampai cukup)"),
            ("audio", "Ikuti durasi audio (video di-loop bila audio lebih panjang)"),
        ):
            ttk.Radiobutton(options, text=text, variable=self.duration_mode, value=value).pack(anchor="w", pady=2)

        mix = ttk.LabelFrame(main, text="Volume", padding=10)
        mix.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 8))
        mix.columnconfigure(1, weight=1)
        ttk.Label(mix, text="Audio asli video").grid(row=0, column=0, sticky="w")
        ttk.Scale(mix, from_=0, to=100, variable=self.video_volume).grid(row=0, column=1, sticky="ew", padx=10)
        ttk.Label(mix, textvariable=self.video_volume).grid(row=0, column=2)
        ttk.Label(mix, text="Audio baru").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Scale(mix, from_=0, to=150, variable=self.audio_volume).grid(row=1, column=1, sticky="ew", padx=10, pady=(8, 0))
        ttk.Label(mix, textvariable=self.audio_volume).grid(row=1, column=2, pady=(8, 0))
        ttk.Checkbutton(mix, text="Timpa file output jika sudah ada", variable=self.overwrite).grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        buttons = ttk.Frame(main)
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(buttons, text="Gabungkan Sekarang", command=self._start_merge).pack(side="left")
        ttk.Button(buttons, text="Acak Semua", command=self._shuffle_all_media).pack(side="left", padx=8)
        ttk.Button(buttons, text="Keluar", command=self.root.destroy).pack(side="right")

    def _build_download_tab(self, main: ttk.Frame) -> None:
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(5, weight=1)

        title = ttk.Label(main, text="YouTube Playlist Downloader", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        subtitle = ttk.Label(main, text="Tambahkan URL ke antrian, lalu download sebagai video MP4 atau audio MP3.")
        subtitle.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        url_row = ttk.Frame(main)
        url_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        url_row.columnconfigure(1, weight=1)
        ttk.Label(url_row, text="URL Playlist").grid(row=0, column=0, sticky="w")
        ttk.Entry(url_row, textvariable=self.playlist_url).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(url_row, text="Muat Playlist", command=self._start_load_playlist_items).grid(row=0, column=2)
        ttk.Button(url_row, text="Tambah URL", command=self._add_download_queue_item).grid(row=0, column=3, padx=(6, 0))

        folder_row = ttk.Frame(main)
        folder_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=4)
        folder_row.columnconfigure(1, weight=1)
        self._file_row(folder_row, 0, "Folder", self.download_dir, self._choose_download_dir)

        format_box = ttk.LabelFrame(main, text="Format download", padding=10)
        format_box.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        ttk.Radiobutton(format_box, text="Video MP4 terbaik", variable=self.download_format, value="video").pack(side="left", padx=(0, 14))
        ttk.Radiobutton(format_box, text="Audio MP3 saja", variable=self.download_format, value="audio").pack(side="left")

        self.download_queue_list = self._download_list_panel(
            main, 5, 0, "Antrian Download", self._remove_download_queue_items
        )
        self.downloaded_list = self._download_list_panel(main, 5, 1, "Sudah Terdownload", None)

        buttons = ttk.Frame(main)
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Download Antrian", command=self._start_playlist_download).pack(side="left")
        ttk.Button(buttons, text="Keluar", command=self.root.destroy).pack(side="right")

    def _media_list_panel(self, parent: ttk.Frame, row: int, column: int, title: str, add_command, remove_command, shuffle_command) -> Listbox:
        frame = ttk.LabelFrame(parent, text=title, padding=8)
        frame.grid(row=row, column=column, sticky="nsew", padx=(0, 6) if column == 0 else (6, 0))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        listbox = Listbox(frame, selectmode=EXTENDED, exportselection=False, height=7)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar_y = ttk.Scrollbar(frame, orient="vertical", command=listbox.yview)
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x = ttk.Scrollbar(frame, orient="horizontal", command=listbox.xview)
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        listbox.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Tambah", command=add_command).pack(side="left")
        ttk.Button(buttons, text="Hapus Terpilih", command=remove_command).pack(side="left", padx=6)
        ttk.Button(buttons, text="Acak", command=shuffle_command).pack(side="left")
        return listbox

    def _download_list_panel(self, parent: ttk.Frame, row: int, column: int, title: str, remove_command) -> Listbox:
        frame = ttk.LabelFrame(parent, text=title, padding=8)
        frame.grid(row=row, column=column, sticky="nsew", padx=(0, 6) if column == 0 else (6, 0))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        listbox = Listbox(frame, selectmode=EXTENDED, exportselection=False, height=8)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar_y = ttk.Scrollbar(frame, orient="vertical", command=listbox.yview)
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x = ttk.Scrollbar(frame, orient="horizontal", command=listbox.xview)
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        listbox.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        if remove_command is not None:
            ttk.Button(frame, text="Hapus Terpilih", command=remove_command).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        return listbox

    def _build_progress_and_log(self, main: ttk.Frame, start_row: int) -> None:
        main.columnconfigure(0, weight=1)
        main.rowconfigure(start_row + 2, weight=1)
        progress_row = ttk.Frame(main)
        progress_row.grid(row=start_row, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        progress_row.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(progress_row, variable=self.progress, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.progress_label = ttk.Label(progress_row, text="0%")
        self.progress_label.grid(row=0, column=1, sticky="e")

        ttk.Label(main, textvariable=self.status).grid(row=start_row + 1, column=0, columnspan=3, sticky="w")
        log_frame = ttk.Frame(main)
        log_frame.grid(row=start_row + 2, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = ttk.Treeview(log_frame, columns=("pesan",), show="headings", height=6)
        self.log.heading("pesan", text="Log")
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll_y = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_scroll_y.grid(row=0, column=1, sticky="ns")
        log_scroll_x = ttk.Scrollbar(log_frame, orient="horizontal", command=self.log.xview)
        log_scroll_x.grid(row=1, column=0, sticky="ew")
        self.log.configure(yscrollcommand=log_scroll_y.set, xscrollcommand=log_scroll_x.set)

    def _file_row(self, parent: ttk.Frame, row: int, label: str, variable: StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(parent, text="Pilih...", command=command).grid(row=row, column=2, sticky="ew", pady=4)

    def _check_tools(self) -> None:
        missing: list[str] = []
        if not find_tool("ffmpeg"):
            missing.append("ffmpeg")
        if not find_tool("yt-dlp"):
            missing.append("yt-dlp")
        if missing:
            tools = ", ".join(missing)
            messagebox.showwarning("Tool belum ditemukan", f"Install {tools} dan pastikan tersedia di PATH.")
            self.status.set(f"Tool belum ditemukan di PATH: {tools}.")

    def _choose_video(self) -> None:
        self._add_video_files()

    def _choose_audio(self) -> None:
        self._add_audio_files()

    def _add_video_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Tambah satu atau banyak video", filetypes=VIDEO_EXTENSIONS)
        if paths:
            self.video_files.extend(Path(path) for path in paths)
            self._refresh_media_lists()
            self._suggest_output()
            self._log_duration("Video", self.video_files)

    def _add_audio_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Tambah satu atau banyak audio", filetypes=AUDIO_EXTENSIONS)
        if paths:
            self.audio_files.extend(Path(path) for path in paths)
            self._refresh_media_lists()
            self._log_duration("Audio", self.audio_files)

    def _remove_selected_videos(self) -> None:
        self.video_files = self._remove_selected_paths(self.video_files, self.video_list)
        self._refresh_media_lists()

    def _remove_selected_audios(self) -> None:
        self.audio_files = self._remove_selected_paths(self.audio_files, self.audio_list)
        self._refresh_media_lists()

    def _remove_selected_paths(self, paths: list[Path], listbox: Listbox | None) -> list[Path]:
        if listbox is None:
            return paths
        selected = set(listbox.curselection())
        return [path for index, path in enumerate(paths) if index not in selected]

    def _shuffle_videos(self) -> None:
        random.shuffle(self.video_files)
        self._refresh_media_lists()
        self._add_log("Urutan video diacak.")

    def _shuffle_audios(self) -> None:
        random.shuffle(self.audio_files)
        self._refresh_media_lists()
        self._add_log("Urutan audio diacak.")

    def _shuffle_all_media(self) -> None:
        random.shuffle(self.video_files)
        random.shuffle(self.audio_files)
        self._refresh_media_lists()
        self._add_log("Urutan video dan audio diacak.")

    def _refresh_media_lists(self) -> None:
        self._refresh_path_list(self.video_list, self.video_files)
        self._refresh_path_list(self.audio_list, self.audio_files)
        self.video_path.set(self._selection_label(self.video_files) if self.video_files else "")
        self.audio_path.set(self._selection_label(self.audio_files) if self.audio_files else "")

    def _refresh_path_list(self, listbox: Listbox | None, paths: Sequence[Path]) -> None:
        if listbox is None:
            return
        listbox.delete(0, END)
        for index, path in enumerate(paths, start=1):
            listbox.insert(END, f"{index}. {path}")

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(title="Simpan hasil", defaultextension=".mp4", filetypes=OUTPUT_EXTENSIONS)
        if path:
            self.output_path.set(path)

    def _choose_download_dir(self) -> None:
        path = filedialog.askdirectory(title="Pilih folder download")
        if path:
            self.download_dir.set(path)

    def _add_download_queue_item(self) -> None:
        url = self.playlist_url.get().strip()
        if not url:
            messagebox.showerror("URL kosong", "Isi URL playlist YouTube terlebih dahulu.")
            return
        self.download_queue_items.append(DownloadItem(title=url, url=url))
        self._refresh_download_lists()
        self.playlist_url.set("")

    def _start_load_playlist_items(self) -> None:
        try:
            command = self._build_playlist_probe_command()
        except ValueError as exc:
            messagebox.showerror("Input download belum lengkap", str(exc))
            return
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start(10)
        self.status.set("Memuat daftar lagu/video dari playlist...")
        self._add_log("Mengambil daftar item playlist dengan yt-dlp...")
        threading.Thread(target=self._load_playlist_items, args=(command,), daemon=True).start()

    def _build_playlist_probe_command(self) -> list[str]:
        yt_dlp = find_tool("yt-dlp")
        if not yt_dlp:
            raise ValueError("yt-dlp tidak ditemukan di PATH.")
        return build_youtube_playlist_probe_command(yt_dlp, self.playlist_url.get())

    def _load_playlist_items(self, command: list[str]) -> None:
        result = run_command(command)
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "yt-dlp gagal membaca playlist."
            self.log_queue.put(f"GAGAL::{error}")
            return
        try:
            items = parse_youtube_playlist_items(result.stdout)
        except json.JSONDecodeError as exc:
            self.log_queue.put(f"GAGAL::Metadata playlist tidak valid: {exc}")
            return
        if not items:
            self.log_queue.put("GAGAL::Playlist tidak berisi item yang bisa didownload.")
            return
        self.log_queue.put(f"QUEUE_ITEMS::{json.dumps([item.__dict__ for item in items])}")

    def _remove_download_queue_items(self) -> None:
        if self.download_queue_list is None:
            return
        selected = set(self.download_queue_list.curselection())
        self.download_queue_items = [
            item for index, item in enumerate(self.download_queue_items) if index not in selected
        ]
        self._refresh_download_lists()

    def _queued_download_items(self) -> list[DownloadItem]:
        return list(self.download_queue_items)

    def _refresh_download_lists(self) -> None:
        self._refresh_download_listbox(self.download_queue_list, self.download_queue_items)
        self._refresh_download_listbox(self.downloaded_list, self.downloaded_items)

    def _refresh_download_listbox(self, listbox: Listbox | None, items: Sequence[DownloadItem]) -> None:
        if listbox is None:
            return
        listbox.delete(0, END)
        for index, item in enumerate(items, start=1):
            listbox.insert(END, f"{index}. {item.title}")

    def _suggest_output(self) -> None:
        if self.output_path.get() or not self.video_files:
            return
        video = self.video_files[0]
        self.output_path.set(str(video.with_name(f"{video.stem}_gabung_audio.mp4")))

    def _selection_label(self, paths: Sequence[Path]) -> str:
        if len(paths) == 1:
            return str(paths[0])
        return f"{len(paths)} file dipilih: {paths[0].name} ... {paths[-1].name}"

    def _log_duration(self, label: str, paths: Sequence[Path]) -> None:
        duration = total_duration(paths)
        self._add_log(f"{label}: {len(paths)} file ({format_duration(duration)})")

    def _start_merge(self) -> None:
        try:
            command, expected_duration, cleanup_paths = self._build_ffmpeg_command()
        except ValueError as exc:
            messagebox.showerror("Input belum lengkap", str(exc))
            return
        self._set_progress(0)
        self.progress_bar.configure(mode="determinate")
        if expected_duration is None:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(10)
        self.status.set("Memproses... jangan tutup aplikasi.")
        self._add_log("Menjalankan FFmpeg...")
        threading.Thread(target=self._run_merge, args=(command, expected_duration, cleanup_paths), daemon=True).start()

    def _start_playlist_download(self) -> None:
        try:
            commands = self._build_playlist_download_commands()
        except ValueError as exc:
            messagebox.showerror("Input download belum lengkap", str(exc))
            return
        self._set_progress(0)
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start(10)
        self.status.set("Mengunduh antrian playlist... jangan tutup aplikasi.")
        self._add_log("Menjalankan yt-dlp untuk antrian download...")
        threading.Thread(target=self._run_playlist_downloads, args=(commands,), daemon=True).start()

    def _build_playlist_download_commands(self) -> list[tuple[DownloadItem, list[str]]]:
        yt_dlp = find_tool("yt-dlp")
        if not yt_dlp:
            raise ValueError("yt-dlp tidak ditemukan di PATH.")
        items = self._queued_download_items()
        if not items:
            url = self.playlist_url.get().strip()
            items = [DownloadItem(title=url, url=url)]
        commands: list[tuple[DownloadItem, list[str]]] = []
        for item in items:
            command = build_youtube_item_command(
                yt_dlp, item.url, Path(self.download_dir.get()), self.download_format.get()
            )
            commands.append((item, command))
        return commands

    def _build_playlist_download_command(self) -> list[str]:
        commands = self._build_playlist_download_commands()
        return commands[0][1]

    def _build_ffmpeg_command(self) -> tuple[list[str], float | None, list[Path]]:
        ffmpeg = find_tool("ffmpeg")
        if not ffmpeg:
            raise ValueError("FFmpeg tidak ditemukan di PATH.")
        output_name = self.output_path.get().strip()
        if not output_name:
            raise ValueError("Lokasi output belum dipilih.")
        output = Path(output_name)
        output_parent = output.expanduser().resolve().parent
        if not output_parent.is_dir():
            raise ValueError(f"Folder output tidak ditemukan: {output_parent}")
        if not self.video_files or any(not path.is_file() for path in self.video_files):
            raise ValueError("File video belum dipilih atau ada yang tidak ditemukan.")
        if not self.audio_files or any(not path.is_file() for path in self.audio_files):
            raise ValueError("File audio belum dipilih atau ada yang tidak ditemukan.")

        cleanup_paths: list[Path] = []
        video_input = self.video_files[0]
        audio_input = self.audio_files[0]
        video_is_concat_list = len(self.video_files) > 1
        audio_is_concat_list = len(self.audio_files) > 1
        if video_is_concat_list:
            video_input = write_concat_list(self.video_files)
            cleanup_paths.append(video_input)
        if audio_is_concat_list:
            audio_input = write_concat_list(self.audio_files)
            cleanup_paths.append(audio_input)

        command = [ffmpeg, "-y" if self.overwrite.get() else "-n"]
        command.extend(
            build_looped_input_args(
                video_input,
                audio_input,
                self.duration_mode.get(),
                video_is_concat_list=video_is_concat_list,
                audio_is_concat_list=audio_is_concat_list,
            )
        )

        video_gain = self.video_volume.get() / 100
        audio_gain = self.audio_volume.get() / 100
        filters: list[str] = []
        audio_inputs: list[str] = []
        if video_gain > 0:
            filters.append(f"[0:a]volume={video_gain:.2f}[vold]")
            audio_inputs.append("[vold]")
        filters.append(f"[1:a]volume={audio_gain:.2f}[anew]")
        audio_inputs.append("[anew]")
        filters.append(f"{''.join(audio_inputs)}amix=inputs={len(audio_inputs)}:duration=longest:dropout_transition=0[aout]")

        command.extend(["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[aout]", "-progress", "pipe:1", "-nostats"])
        command.append("-shortest")
        command.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)])
        return command, self._expected_duration(), cleanup_paths

    def _expected_duration(self) -> float | None:
        video_duration = total_duration(self.video_files)
        audio_duration = total_duration(self.audio_files)
        if self.duration_mode.get() == "video":
            return video_duration
        if self.duration_mode.get() == "audio":
            return audio_duration
        if video_duration is None or audio_duration is None:
            return None
        return min(video_duration, audio_duration)

    def _run_merge(self, command: list[str], expected_duration: float | None, cleanup_paths: Sequence[Path]) -> None:
        startupinfo = None
        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return_code = 1
        output_lines: list[str] = []
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo,
            )
            assert process.stdout is not None
            for line in process.stdout:
                stripped = line.strip()
                self._handle_progress_line(stripped, expected_duration)
                if not stripped.startswith(("frame=", "fps=", "out_time_ms=", "progress=")):
                    output_lines.append(stripped)
            return_code = process.wait()
        finally:
            for path in cleanup_paths:
                path.unlink(missing_ok=True)
        if return_code == 0:
            self.log_queue.put("PROGRESS::100")
            self.log_queue.put("SELESAI::Berhasil membuat file output.")
        else:
            error = output_lines[-1] if output_lines else "FFmpeg gagal tanpa pesan."
            self.log_queue.put(f"GAGAL::{error}")

    def _run_playlist_downloads(self, commands: Sequence[tuple[DownloadItem, list[str]]]) -> None:
        for item, command in commands:
            ok = self._run_playlist_download(item, command)
            if not ok:
                return
        self.log_queue.put("PROGRESS::100")
        self.log_queue.put("SELESAI::Antrian playlist berhasil diunduh.")

    def _run_playlist_download(self, item: DownloadItem, command: list[str]) -> bool:
        startupinfo = None
        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return_code = 1
        output_lines: list[str] = []
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            startupinfo=startupinfo,
        )
        assert process.stdout is not None
        for line in process.stdout:
            stripped = line.strip()
            self._handle_download_line(stripped)
            if stripped:
                output_lines.append(stripped)
        return_code = process.wait()
        if return_code == 0:
            self.log_queue.put(f"DOWNLOAD_DONE::{json.dumps(item.__dict__)}")
            return True
        error = output_lines[-1] if output_lines else "yt-dlp gagal tanpa pesan."
        self.log_queue.put(f"GAGAL::{error}")
        return False

    def _handle_download_line(self, line: str) -> None:
        if line.startswith("download:"):
            percent_text = line.removeprefix("download:").strip().rstrip("%")
            try:
                self.log_queue.put(f"PROGRESS::{float(percent_text):.1f}")
            except ValueError:
                return
        elif line:
            self.log_queue.put(f"LOG::{line}")

    def _handle_progress_line(self, line: str, expected_duration: float | None) -> None:
        if expected_duration is None or expected_duration <= 0 or not line.startswith("out_time_ms="):
            return
        try:
            encoded_seconds = int(line.split("=", 1)[1]) / 1_000_000
        except ValueError:
            return
        percent = min(99.0, max(0.0, encoded_seconds / expected_duration * 100))
        self.log_queue.put(f"PROGRESS::{percent:.1f}")

    def _poll_log_queue(self) -> None:
        while not self.log_queue.empty():
            message = self.log_queue.get()
            if message.startswith("PROGRESS::"):
                self._set_progress(float(message.removeprefix("PROGRESS::")))
            elif message.startswith("LOG::"):
                self._add_log(message.removeprefix("LOG::"))
            elif message.startswith("QUEUE_ITEMS::"):
                self._add_loaded_queue_items(message.removeprefix("QUEUE_ITEMS::"))
            elif message.startswith("DOWNLOAD_DONE::"):
                self._mark_download_done(message.removeprefix("DOWNLOAD_DONE::"))
            elif message.startswith("SELESAI::"):
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
                self._set_progress(100)
                self.status.set(message.removeprefix("SELESAI::"))
                self._add_log(self.status.get())
                messagebox.showinfo("Selesai", self.status.get())
            elif message.startswith("GAGAL::"):
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
                self.status.set("Proses gagal. Lihat log.")
                self._add_log(message.removeprefix("GAGAL::"))
                messagebox.showerror("Gagal", self.log.item(self.log.get_children()[-1], "values")[0])
        self.root.after(200, self._poll_log_queue)

    def _mark_download_done(self, payload: str) -> None:
        data = json.loads(payload)
        item = DownloadItem(title=str(data["title"]), url=str(data["url"]))
        self.downloaded_items.append(item)
        self.download_queue_items = [queued for queued in self.download_queue_items if queued.url != item.url]
        self._refresh_download_lists()
        self._add_log(f"Selesai download: {item.title}")

    def _add_loaded_queue_items(self, payload: str) -> None:
        data = json.loads(payload)
        self.download_queue_items.extend(DownloadItem(title=str(item["title"]), url=str(item["url"])) for item in data)
        self._refresh_download_lists()
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.status.set(f"Berhasil memuat {len(data)} item ke antrian download.")
        self._add_log(self.status.get())

    def _set_progress(self, percent: float) -> None:
        self.progress.set(percent)
        self.progress_label.configure(text=f"{percent:.0f}%")

    def _add_log(self, message: str) -> None:
        self.log.insert("", "end", values=(message,))
        self.log.yview_moveto(1)


def main() -> None:
    root = Tk()
    MergerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
