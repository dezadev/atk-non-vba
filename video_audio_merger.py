#!/usr/bin/env python3
"""A desktop app to merge media with FFmpeg and download YouTube playlists.

Targeted for Python 3.14+ and uses only the standard library plus installed
``ffmpeg`` and optional ``yt-dlp`` executables. The UI is intentionally compact
and Indonesian-language for easy local use.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import random
import shutil
import subprocess
import tempfile
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tkinter import END, EXTENDED, BooleanVar, DoubleVar, IntVar, Listbox, StringVar, Tk, filedialog, messagebox, ttk
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

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


def display_media_name(path: str | Path) -> str:
    """Return only the filename for media list display."""
    return re.split(r"[/\\]+", str(path))[-1]


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


WEB_INDEX_HTML = """<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Toolkit Video & Audio</title>
  <style>
    :root{--bg:#eef2f7;--card:#fff;--muted:#64748b;--text:#111827;--primary:#2563eb;--danger:#dc2626;--border:#d8dee9}
    *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 "Segoe UI",Arial,sans-serif}
    .app{max-width:1180px;margin:0 auto;padding:22px}.hero{background:#1e3a8a;color:white;border-radius:18px;padding:22px 24px;margin-bottom:16px;box-shadow:0 18px 40px #1e293b22}.hero p{color:#dbeafe;margin:5px 0 0}.tabs{display:flex;gap:8px;margin-bottom:14px}.tab{border:1px solid var(--border);background:var(--card);padding:12px 18px;border-radius:999px;font-weight:700;cursor:pointer}.tab.active{background:var(--primary);color:#fff;border-color:var(--primary)}
    .panel{display:none}.panel.active{display:block}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.merge-options{display:grid;grid-template-columns:1.4fr 1.2fr auto;gap:14px;align-items:start;margin-top:14px}.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:14px;box-shadow:0 8px 20px #3341550d}h1,h2,h3{margin:0 0 10px}label{font-weight:700}.row{display:flex;gap:8px;align-items:center;margin:10px 0}.grow{flex:1}input[type=text],select{width:100%;border:1px solid var(--border);border-radius:10px;padding:10px;background:white}.list{height:180px;overflow:auto;border:1px solid var(--border);border-radius:12px;background:#f8fafc;padding:8px}.item{padding:7px 9px;border-radius:8px;margin-bottom:4px;word-break:break-word}.item:hover{background:#e0e7ff}.item.selected{background:#2563eb;color:#fff}button{border:1px solid var(--border);border-radius:10px;background:#fff;padding:10px 13px;font-weight:700;cursor:pointer}button.primary{background:var(--primary);border-color:var(--primary);color:#fff}button.danger{color:var(--danger)}.options{display:grid;gap:8px}.actions{display:flex;flex-direction:column;gap:10px;min-width:150px}.muted{color:var(--muted);font-weight:400}.status{margin-top:14px}.bar{height:14px;border-radius:999px;background:#dbeafe;overflow:hidden}.fill{height:100%;width:0;background:var(--primary);transition:width .2s}.log{height:165px;overflow:auto;background:#0f172a;color:#dbeafe;border-radius:14px;padding:12px;font-family:Consolas,monospace;white-space:pre-wrap}.hidden{display:none}@media(max-width:900px){.grid,.merge-options{grid-template-columns:1fr}.app{padding:12px}}
  </style>
</head>
<body><main class="app">
  <section class="hero"><h1>Toolkit Video & Audio</h1><p>Aplikasi web lokal offline untuk FFmpeg dan yt-dlp. Server berjalan di komputer ini dan ditampilkan melalui PyWebView.</p><p id="mode" class="muted"></p></section>
  <nav class="tabs"><button class="tab active" data-tab="merge">Gabung Media</button><button class="tab" data-tab="download">Download YouTube</button></nav>
  <section id="merge" class="panel active">
    <div class="grid"><div class="card"><h3>Daftar Video</h3><div id="videos" class="list"></div><div class="row"><button onclick="chooseVideos()">Tambah</button><button onclick="removeSelected('videos')">Hapus Terpilih</button><button onclick="shuffleList('videos')">Acak</button></div></div>
    <div class="card"><h3>Daftar Audio</h3><div id="audios" class="list"></div><div class="row"><button onclick="chooseAudios()">Tambah</button><button onclick="removeSelected('audios')">Hapus Terpilih</button><button onclick="shuffleList('audios')">Acak</button></div></div></div>
    <div class="merge-options">
      <div class="card"><h3>Output</h3><div class="row"><input id="output" class="grow" type="text"><button onclick="chooseOutput()">Pilih...</button></div><label><input id="overwrite" type="checkbox" checked> Timpa file output jika sudah ada</label></div>
      <div class="card"><h3>Penyesuaian durasi</h3><div class="options"><label><input type="radio" name="duration" value="shortest" checked> Selesai di durasi terpendek</label><label><input type="radio" name="duration" value="video"> Ikuti durasi video</label><label><input type="radio" name="duration" value="audio"> Ikuti durasi audio</label></div><div class="grid"><label>Audio asli video <input id="videoVolume" type="range" min="0" max="100" value="0"></label><label>Audio baru <input id="audioVolume" type="range" min="0" max="150" value="100"></label></div></div>
      <div class="card"><h3>Aksi</h3><div class="actions"><button class="primary" onclick="startMerge()">Gabungkan Sekarang</button><button onclick="shuffleAll()">Acak Semua</button></div></div>
    </div>
  </section>
  <section id="download" class="panel"><div class="card"><div class="row"><label>URL Playlist</label><input id="playlistUrl" class="grow" type="text"><button onclick="loadPlaylist()">Muat Playlist</button><button onclick="addUrl()">Tambah URL</button></div><div class="row"><label>Folder</label><input id="downloadDir" class="grow" type="text"><button onclick="chooseDownloadDir()">Pilih...</button></div><div class="row"><label><input type="radio" name="format" value="video" checked> Video MP4 terbaik</label><label><input type="radio" name="format" value="audio"> Audio MP3 saja</label></div></div><div class="grid"><div class="card"><h3>Antrian Download</h3><div id="queue" class="list"></div><button onclick="removeSelected('queue')">Hapus Terpilih</button></div><div class="card"><h3>Sudah Terdownload</h3><div id="done" class="list"></div></div></div><div class="row"><button class="primary" onclick="startDownload()">Download Antrian</button></div></section>
  <section class="status"><div class="bar"><div id="progress" class="fill"></div></div><p id="status">Memuat aplikasi...</p><div id="log" class="log"></div></section>
</main><script src="/app.js"></script></body></html>"""

WEB_APP_JS = r"""
let state={video_files:[],audio_files:[],download_queue_items:[],downloaded_items:[],status:'',progress:0,log:[],mode:''};
const selected={videos:new Set(),audios:new Set(),queue:new Set()};
async function api(path, data){const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data||{})}); const j=await r.json(); if(!r.ok||j.error){alert(j.error||'Permintaan gagal');} await refresh(); return j;}
async function refresh(){const r=await fetch('/api/state'); state=await r.json(); render();}
function fileName(value){return String(value).split(/[\\/]/).pop();}
function renderList(id, values){const box=document.getElementById(id); box.innerHTML=''; values.forEach((v,i)=>{const d=document.createElement('div'); d.className='item '+(selected[id]?.has(i)?'selected':''); const text=(id==='videos'||id==='audios')?fileName(v):(v.title||v); d.textContent=(i+1)+'. '+text; d.title=(v.title||v); d.onclick=()=>{selected[id].has(i)?selected[id].delete(i):selected[id].add(i); render();}; box.appendChild(d);});}
function render(){document.getElementById('mode').textContent='Mode: '+state.mode; renderList('videos',state.video_files); renderList('audios',state.audio_files); renderList('queue',state.download_queue_items); renderList('done',state.downloaded_items); document.getElementById('downloadDir').value=state.download_dir||''; const out=document.getElementById('output'); if(document.activeElement!==out) out.value=state.output_path||out.value; document.getElementById('status').textContent=state.status||''; document.getElementById('progress').style.width=(state.progress||0)+'%'; document.getElementById('log').textContent=(state.log||[]).join('\n'); document.getElementById('log').scrollTop=document.getElementById('log').scrollHeight;}
async function chooseVideos(){const paths=await window.pywebview.api.choose_videos(); if(paths?.length) await api('add_media',{kind:'video',paths});}
async function chooseAudios(){const paths=await window.pywebview.api.choose_audios(); if(paths?.length) await api('add_media',{kind:'audio',paths});}
async function chooseOutput(){const path=await window.pywebview.api.choose_output(); if(path) document.getElementById('output').value=path;}
async function chooseDownloadDir(){const path=await window.pywebview.api.choose_download_dir(); if(path) await api('set_download_dir',{path});}
function removeSelected(kind){api('remove',{kind,indices:[...selected[kind]]}); selected[kind].clear();}
function shuffleList(kind){api('shuffle',{kind});} function shuffleAll(){api('shuffle',{kind:'all'});} function val(n){return document.querySelector('input[name='+n+']:checked').value;}
function startMerge(){api('merge',{output:document.getElementById('output').value,duration_mode:val('duration'),video_volume:+document.getElementById('videoVolume').value,audio_volume:+document.getElementById('audioVolume').value,overwrite:document.getElementById('overwrite').checked});}
function addUrl(){api('add_url',{url:document.getElementById('playlistUrl').value}); document.getElementById('playlistUrl').value='';}
function loadPlaylist(){api('load_playlist',{url:document.getElementById('playlistUrl').value});}
function startDownload(){api('download',{url:document.getElementById('playlistUrl').value,media_format:val('format')});}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab,.panel').forEach(x=>x.classList.remove('active')); b.classList.add('active'); document.getElementById(b.dataset.tab).classList.add('active');});
refresh(); setInterval(refresh,1000);
"""


class MergerApp:
    """Tkinter UI for merging media and downloading YouTube playlists."""

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x680")
        self.root.minsize(760, 560)
        self._configure_styles()

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

    def _configure_styles(self) -> None:
        """Apply a calmer, more polished ttk theme."""
        self.root.configure(bg="#eef2f7")
        self.root.option_add("*Font", ("Segoe UI", 10))
        self.root.option_add("*Listbox.Font", ("Segoe UI", 10))
        self.root.option_add("*Listbox.Background", "#ffffff")
        self.root.option_add("*Listbox.Foreground", "#111827")
        self.root.option_add("*Listbox.SelectBackground", "#2563eb")
        self.root.option_add("*Listbox.SelectForeground", "#ffffff")

        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        colors = {
            "bg": "#eef2f7",
            "surface": "#ffffff",
            "surface_alt": "#f8fafc",
            "border": "#d8dee9",
            "text": "#111827",
            "muted": "#64748b",
            "primary": "#2563eb",
            "primary_hover": "#1d4ed8",
        }
        style.configure(".", background=colors["bg"], foreground=colors["text"], font=("Segoe UI", 10))
        style.configure("TFrame", background=colors["bg"])
        style.configure("Card.TFrame", background=colors["surface"], relief="flat")
        style.configure("Hero.TFrame", background="#1e3a8a", relief="flat")
        style.configure("TLabel", background=colors["bg"], foreground=colors["text"])
        style.configure("Card.TLabel", background=colors["surface"], foreground=colors["text"])
        style.configure("HeroTitle.TLabel", background="#1e3a8a", foreground="#ffffff", font=("Segoe UI", 18, "bold"))
        style.configure("HeroSubtitle.TLabel", background="#1e3a8a", foreground="#dbeafe", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=colors["surface"], foreground=colors["muted"])
        style.configure("TLabelframe", background=colors["surface"], bordercolor=colors["border"], relief="solid")
        style.configure("TLabelframe.Label", background=colors["surface"], foreground=colors["text"], font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook", background=colors["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", colors["surface"]), ("active", colors["surface_alt"])])
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10, "bold"), borderwidth=1)
        style.configure("Accent.TButton", background=colors["primary"], foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", colors["primary_hover"]), ("pressed", "#1e40af")])
        style.configure("TEntry", fieldbackground="#ffffff", bordercolor=colors["border"], padding=6)
        style.configure("Horizontal.TProgressbar", background=colors["primary"], troughcolor="#dbeafe", bordercolor="#dbeafe")
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground=colors["text"], rowheight=24, bordercolor=colors["border"])
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background=colors["surface_alt"])

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

        merge_tab = ttk.Frame(notebook, padding=18)
        download_tab = ttk.Frame(notebook, padding=18)
        notebook.add(merge_tab, text="Gabung Media")
        notebook.add(download_tab, text="Download YouTube")

        self._build_merge_tab(merge_tab)
        self._build_download_tab(download_tab)
        self._build_progress_and_log(status_frame, start_row=0)

    def _build_merge_tab(self, main: ttk.Frame) -> None:
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        self._section_header(
            main,
            "Penggabung Video & Audio",
            "Kelola daftar video/audio, acak urutan bila perlu, lalu gabungkan dengan kontrol durasi yang jelas.",
        )

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
        ttk.Button(buttons, text="Gabungkan Sekarang", style="Accent.TButton", command=self._start_merge).pack(side="left")
        ttk.Button(buttons, text="Acak Semua", command=self._shuffle_all_media).pack(side="left", padx=8)
        ttk.Button(buttons, text="Keluar", command=self.root.destroy).pack(side="right")

    def _build_download_tab(self, main: ttk.Frame) -> None:
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(5, weight=1)

        self._section_header(
            main,
            "YouTube Playlist Downloader",
            "Tambahkan URL ke antrian, lalu download sebagai video MP4 terbaik atau audio MP3 berkualitas tinggi.",
        )

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
        ttk.Button(buttons, text="Download Antrian", style="Accent.TButton", command=self._start_playlist_download).pack(side="left")
        ttk.Button(buttons, text="Keluar", command=self.root.destroy).pack(side="right")


    def _section_header(self, parent: ttk.Frame, title: str, subtitle: str) -> None:
        hero = ttk.Frame(parent, style="Hero.TFrame", padding=(18, 14))
        hero.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        hero.columnconfigure(0, weight=1)
        ttk.Label(hero, text=title, style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(hero, text=subtitle, style="HeroSubtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

    def _media_list_panel(self, parent: ttk.Frame, row: int, column: int, title: str, add_command, remove_command, shuffle_command) -> Listbox:
        frame = ttk.LabelFrame(parent, text=title, padding=8)
        frame.grid(row=row, column=column, sticky="nsew", padx=(0, 6) if column == 0 else (6, 0))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        listbox = Listbox(frame, selectmode=EXTENDED, exportselection=False, height=7, relief="flat", borderwidth=0, highlightthickness=1, highlightbackground="#d8dee9", activestyle="none")
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

        listbox = Listbox(frame, selectmode=EXTENDED, exportselection=False, height=8, relief="flat", borderwidth=0, highlightthickness=1, highlightbackground="#d8dee9", activestyle="none")
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
        self.log = ttk.Treeview(log_frame, columns=("pesan",), show="headings", height=6, style="Treeview")
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
            listbox.insert(END, f"{index}. {display_media_name(path)}")

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


class SimpleVar:
    """Small variable wrapper matching Tkinter Variable.get for shared command builders."""

    def __init__(self, value: Any = None) -> None:
        self.value = value

    def get(self) -> Any:
        return self.value

    def set(self, value: Any) -> None:
        self.value = value


class WebMergerApp:
    """Headless application state used by the local web UI."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.video_files: list[Path] = []
        self.audio_files: list[Path] = []
        self.download_queue_items: list[DownloadItem] = []
        self.downloaded_items: list[DownloadItem] = []
        self.output_path = SimpleVar("")
        self.playlist_url = SimpleVar("")
        self.download_dir = SimpleVar(str(Path.home() / "Downloads"))
        self.download_format = SimpleVar("video")
        self.duration_mode = SimpleVar("shortest")
        self.video_volume = SimpleVar(0)
        self.audio_volume = SimpleVar(100)
        self.overwrite = SimpleVar(True)
        self.status = "Pilih file video dan audio untuk mulai."
        self.progress = 0.0
        self.logs: list[str] = []
        self.lock = threading.Lock()
        self._check_tools()

    def _check_tools(self) -> None:
        missing = [tool for tool in ("ffmpeg", "yt-dlp") if not find_tool(tool)]
        if missing:
            self.status = "Tool belum ditemukan di PATH: " + ", ".join(missing)
            self._add_log(self.status)

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "mode": self.mode,
                "video_files": [str(path) for path in self.video_files],
                "audio_files": [str(path) for path in self.audio_files],
                "download_queue_items": [item.__dict__ for item in self.download_queue_items],
                "downloaded_items": [item.__dict__ for item in self.downloaded_items],
                "download_dir": self.download_dir.get(),
                "output_path": self.output_path.get(),
                "status": self.status,
                "progress": self.progress,
                "log": self.logs[-250:],
            }

    def add_media(self, kind: str, paths: Sequence[str]) -> None:
        files = [Path(path) for path in paths]
        with self.lock:
            if kind == "video":
                self.video_files.extend(files)
                if not self.output_path.get() and self.video_files:
                    video = self.video_files[0]
                    self.output_path.set(str(video.with_name(f"{video.stem}_gabung_audio.mp4")))
            elif kind == "audio":
                self.audio_files.extend(files)
            else:
                raise ValueError("Jenis media tidak valid.")
        self._add_log(f"{kind.title()}: {len(files)} file ditambahkan.")

    def remove(self, kind: str, indices: Sequence[int]) -> None:
        selected = set(indices)
        with self.lock:
            if kind == "videos":
                self.video_files = [path for index, path in enumerate(self.video_files) if index not in selected]
            elif kind == "audios":
                self.audio_files = [path for index, path in enumerate(self.audio_files) if index not in selected]
            elif kind == "queue":
                self.download_queue_items = [item for index, item in enumerate(self.download_queue_items) if index not in selected]
            else:
                raise ValueError("Jenis daftar tidak valid.")

    def shuffle(self, kind: str) -> None:
        with self.lock:
            if kind in ("videos", "all"):
                random.shuffle(self.video_files)
            if kind in ("audios", "all"):
                random.shuffle(self.audio_files)
        self._add_log("Urutan media diacak.")

    def add_url(self, url: str) -> None:
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("URL playlist YouTube belum diisi.")
        with self.lock:
            self.download_queue_items.append(DownloadItem(title=clean_url, url=clean_url))
        self._add_log("URL ditambahkan ke antrian download.")

    def load_playlist(self, url: str) -> None:
        self.playlist_url.set(url)
        command = MergerApp._build_playlist_probe_command(self)  # reuse validated builder
        self.status = "Memuat daftar lagu/video dari playlist..."
        self._add_log("Mengambil daftar item playlist dengan yt-dlp...")
        threading.Thread(target=self._load_playlist_items, args=(command,), daemon=True).start()

    def start_merge(self, data: dict[str, Any]) -> None:
        self.output_path.set(str(data.get("output", "")))
        self.duration_mode.set(str(data.get("duration_mode", "shortest")))
        self.video_volume.set(int(data.get("video_volume", 0)))
        self.audio_volume.set(int(data.get("audio_volume", 100)))
        self.overwrite.set(bool(data.get("overwrite", True)))
        command, expected_duration, cleanup_paths = MergerApp._build_ffmpeg_command(self)
        self.progress = 0
        self.status = "Memproses... jangan tutup aplikasi."
        self._add_log("Menjalankan FFmpeg...")
        threading.Thread(target=self._run_merge, args=(command, expected_duration, cleanup_paths), daemon=True).start()

    def start_download(self, url: str, media_format: str) -> None:
        self.playlist_url.set(url)
        self.download_format.set(media_format)
        commands = MergerApp._build_playlist_download_commands(self)
        self.progress = 0
        self.status = "Mengunduh antrian playlist... jangan tutup aplikasi."
        self._add_log("Menjalankan yt-dlp untuk antrian download...")
        threading.Thread(target=self._run_playlist_downloads, args=(commands,), daemon=True).start()

    _queued_download_items = MergerApp._queued_download_items
    _expected_duration = MergerApp._expected_duration
    _build_ffmpeg_command = MergerApp._build_ffmpeg_command
    _build_playlist_download_commands = MergerApp._build_playlist_download_commands
    _build_playlist_probe_command = MergerApp._build_playlist_probe_command

    def _load_playlist_items(self, command: list[str]) -> None:
        result = run_command(command)
        if result.returncode != 0:
            self._fail(result.stderr.strip() or result.stdout.strip() or "yt-dlp gagal membaca playlist.")
            return
        try:
            items = parse_youtube_playlist_items(result.stdout)
        except json.JSONDecodeError as exc:
            self._fail(f"Metadata playlist tidak valid: {exc}")
            return
        with self.lock:
            self.download_queue_items.extend(items)
            self.status = f"Berhasil memuat {len(items)} item ke antrian download."
        self._add_log(self.status)

    def _run_merge(self, command: list[str], expected_duration: float | None, cleanup_paths: Sequence[Path]) -> None:
        try:
            MergerApp._run_merge(self, command, expected_duration, cleanup_paths)
        except Exception as exc:
            self._fail(str(exc))

    def _run_playlist_downloads(self, commands: Sequence[tuple[DownloadItem, list[str]]]) -> None:
        for item, command in commands:
            if not self._run_playlist_download(item, command):
                return
        self._set_progress(100)
        self.status = "Antrian playlist berhasil diunduh."
        self._add_log(self.status)

    def _run_playlist_download(self, item: DownloadItem, command: list[str]) -> bool:
        return MergerApp._run_playlist_download(self, item, command)

    def _handle_progress_line(self, line: str, expected_duration: float | None) -> None:
        if expected_duration is None or expected_duration <= 0 or not line.startswith("out_time_ms="):
            return
        try:
            encoded_seconds = int(line.split("=", 1)[1]) / 1_000_000
        except ValueError:
            return
        self._set_progress(min(99.0, max(0.0, encoded_seconds / expected_duration * 100)))

    def _handle_download_line(self, line: str) -> None:
        if line.startswith("download:"):
            try:
                self._set_progress(float(line.removeprefix("download:").strip().rstrip("%")))
            except ValueError:
                pass
        elif line:
            self._add_log(line)

    def _mark_download_done(self, payload: str) -> None:
        data = json.loads(payload)
        item = DownloadItem(title=str(data["title"]), url=str(data["url"]))
        with self.lock:
            self.downloaded_items.append(item)
            self.download_queue_items = [queued for queued in self.download_queue_items if queued.url != item.url]
        self._add_log(f"Selesai download: {item.title}")

    def _set_progress(self, percent: float) -> None:
        with self.lock:
            self.progress = round(percent, 1)

    def _add_log(self, message: str) -> None:
        with self.lock:
            self.logs.append(message)

    def _fail(self, message: str) -> None:
        with self.lock:
            self.status = "Proses gagal. Lihat log."
        self._add_log(message)

    @property
    def log_queue(self):
        class QueueProxy:
            def __init__(self, app: WebMergerApp) -> None:
                self.app = app
            def put(self, message: str) -> None:
                if message.startswith("PROGRESS::"):
                    self.app._set_progress(float(message.removeprefix("PROGRESS::")))
                elif message.startswith("SELESAI::"):
                    self.app.status = message.removeprefix("SELESAI::")
                    self.app._add_log(self.app.status)
                elif message.startswith("GAGAL::"):
                    self.app._fail(message.removeprefix("GAGAL::"))
                elif message.startswith("DOWNLOAD_DONE::"):
                    self.app._mark_download_done(message.removeprefix("DOWNLOAD_DONE::"))
                elif message.startswith("LOG::"):
                    self.app._add_log(message.removeprefix("LOG::"))
        return QueueProxy(self)


class LocalWebHandler(BaseHTTPRequestHandler):
    app_state: WebMergerApp

    def log_message(self, format: str, *args: Any) -> None:
        if self.app_state.mode == "development":
            super().log_message(format, *args)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, WEB_INDEX_HTML, "text/html; charset=utf-8")
        elif path == "/app.js":
            self._send(200, WEB_APP_JS, "application/javascript; charset=utf-8")
        elif path == "/api/state":
            self._json(200, self.app_state.state())
        else:
            self._json(404, {"error": "Halaman tidak ditemukan."})

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
            self._route_post(urlparse(self.path).path, data)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _route_post(self, path: str, data: dict[str, Any]) -> None:
        app = self.app_state
        if path == "/api/add_media":
            app.add_media(str(data.get("kind", "")), data.get("paths", []))
        elif path == "/api/remove":
            app.remove(str(data.get("kind", "")), [int(i) for i in data.get("indices", [])])
        elif path == "/api/shuffle":
            app.shuffle(str(data.get("kind", "")))
        elif path == "/api/add_url":
            app.add_url(str(data.get("url", "")))
        elif path == "/api/load_playlist":
            app.load_playlist(str(data.get("url", "")))
        elif path == "/api/set_download_dir":
            app.download_dir.set(str(data.get("path", "")))
        elif path == "/api/merge":
            app.start_merge(data)
        elif path == "/api/download":
            app.start_download(str(data.get("url", "")), str(data.get("media_format", "video")))
        else:
            self._json(404, {"error": "Endpoint tidak ditemukan."})
            return
        self._json(200, {"ok": True})

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        self._send(code, json.dumps(payload), "application/json; charset=utf-8")

    def _send(self, code: int, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class PyWebViewApi:
    """Native file dialogs exposed to JavaScript through PyWebView.

    Keep this object free of PyWebView window references. PyWebView reflects
    public API objects for JavaScript exposure; storing the native window on the
    API object can make that reflection walk platform accessibility objects
    recursively on Windows.
    """

    def choose_videos(self) -> list[str]:
        return self._ask_open_filenames("Pilih video", VIDEO_EXTENSIONS)

    def choose_audios(self) -> list[str]:
        return self._ask_open_filenames("Pilih audio", AUDIO_EXTENSIONS)

    def choose_output(self) -> str:
        root = self._dialog_root()
        try:
            return filedialog.asksaveasfilename(
                parent=root,
                title="Simpan hasil",
                defaultextension=".mp4",
                filetypes=OUTPUT_EXTENSIONS,
            )
        finally:
            root.destroy()

    def choose_download_dir(self) -> str:
        root = self._dialog_root()
        try:
            return filedialog.askdirectory(parent=root, title="Pilih folder download")
        finally:
            root.destroy()

    def _ask_open_filenames(self, title: str, filetypes: Sequence[tuple[str, str]]) -> list[str]:
        root = self._dialog_root()
        try:
            return list(filedialog.askopenfilenames(parent=root, title=title, filetypes=filetypes))
        finally:
            root.destroy()

    def _dialog_root(self) -> Tk:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return root


def run_local_web_app(mode: str) -> None:
    app_state = WebMergerApp(mode)
    LocalWebHandler.app_state = app_state
    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalWebHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    if mode == "development":
        app_state._add_log(f"Server development aktif di {url}")
    try:
        import webview
    except ImportError as exc:
        raise SystemExit("PyWebView belum terinstall. Jalankan: pip install pywebview") from exc
    api = PyWebViewApi()
    webview.create_window(APP_TITLE, url, js_api=api, width=1100, height=760)
    if mode == "development" and os.environ.get("ATK_OPEN_BROWSER") == "1":
        webbrowser.open(url)
    webview.start(debug=mode == "development")
    server.shutdown()

def main() -> None:
    parser = argparse.ArgumentParser(description="Jalankan aplikasi web lokal offline.")
    parser.add_argument("--mode", choices=("development", "production"), default=os.environ.get("ATK_MODE", "production"))
    parser.add_argument("--legacy-tk", action="store_true", help="Jalankan UI Tkinter lama untuk kompatibilitas darurat.")
    args = parser.parse_args()
    if args.legacy_tk:
        root = Tk()
        MergerApp(root)
        root.mainloop()
        return
    run_local_web_app(args.mode)


if __name__ == "__main__":
    main()
