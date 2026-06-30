#!/usr/bin/env python3
"""A simple desktop app to merge video and audio with FFmpeg.

Targeted for Python 3.14+ and uses only the standard library plus an installed
``ffmpeg`` executable. The UI is intentionally compact and Indonesian-language
for easy local use.
"""
from __future__ import annotations

import json
import queue
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, Tk, filedialog, messagebox, ttk
from typing import Iterable, Sequence

APP_TITLE = "Penggabung Video & Audio (FFmpeg)"
VIDEO_EXTENSIONS = (("Video", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"), ("Semua file", "*.*"))
AUDIO_EXTENSIONS = (("Audio", "*.mp3 *.wav *.aac *.m4a *.ogg *.flac"), ("Semua file", "*.*"))
OUTPUT_EXTENSIONS = (("MP4", "*.mp4"), ("MKV", "*.mkv"), ("Semua file", "*.*"))


@dataclass(frozen=True)
class MediaInfo:
    duration: float | None


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


class MergerApp:
    """Tkinter UI for combining selected video files with selected audio files."""

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("760x520")
        self.root.minsize(700, 480)

        self.video_files: list[Path] = []
        self.audio_files: list[Path] = []
        self.video_path = StringVar()
        self.audio_path = StringVar()
        self.output_path = StringVar()
        self.duration_mode = StringVar(value="shortest")
        self.video_volume = IntVar(value=0)
        self.audio_volume = IntVar(value=100)
        self.overwrite = BooleanVar(value=True)
        self.status = StringVar(value="Pilih file video dan audio untuk mulai.")
        self.progress = DoubleVar(value=0)
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self._poll_log_queue()
        self._check_ffmpeg()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)

        title = ttk.Label(main, text=APP_TITLE, font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        subtitle = ttk.Label(main, text="Gabungkan video dan audio, lalu pilih cara menyesuaikan durasi hasil.")
        subtitle.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

        self._file_row(main, 2, "Video", self.video_path, self._choose_video)
        self._file_row(main, 3, "Audio", self.audio_path, self._choose_audio)
        self._file_row(main, 4, "Output", self.output_path, self._choose_output)

        options = ttk.LabelFrame(main, text="Penyesuaian durasi", padding=12)
        options.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(14, 8))
        for value, text in (
            ("shortest", "Selesai di durasi terpendek (audio/video dipotong otomatis)"),
            ("video", "Ikuti durasi video (audio dipotong atau diulang sampai cukup)"),
            ("audio", "Ikuti durasi audio (video di-loop bila audio lebih panjang)"),
        ):
            ttk.Radiobutton(options, text=text, variable=self.duration_mode, value=value).pack(anchor="w", pady=2)

        mix = ttk.LabelFrame(main, text="Volume", padding=12)
        mix.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(6, 8))
        mix.columnconfigure(1, weight=1)
        ttk.Label(mix, text="Audio asli video").grid(row=0, column=0, sticky="w")
        ttk.Scale(mix, from_=0, to=100, variable=self.video_volume).grid(row=0, column=1, sticky="ew", padx=10)
        ttk.Label(mix, textvariable=self.video_volume).grid(row=0, column=2)
        ttk.Label(mix, text="Audio baru").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Scale(mix, from_=0, to=150, variable=self.audio_volume).grid(row=1, column=1, sticky="ew", padx=10, pady=(8, 0))
        ttk.Label(mix, textvariable=self.audio_volume).grid(row=1, column=2, pady=(8, 0))
        ttk.Checkbutton(mix, text="Timpa file output jika sudah ada", variable=self.overwrite).grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        buttons = ttk.Frame(main)
        buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 8))
        ttk.Button(buttons, text="Gabungkan Sekarang", command=self._start_merge).pack(side="left")
        ttk.Button(buttons, text="Keluar", command=self.root.destroy).pack(side="right")

        progress_row = ttk.Frame(main)
        progress_row.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        progress_row.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(progress_row, variable=self.progress, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.progress_label = ttk.Label(progress_row, text="0%")
        self.progress_label.grid(row=0, column=1, sticky="e")

        ttk.Label(main, textvariable=self.status).grid(row=9, column=0, columnspan=3, sticky="w")
        self.log = ttk.Treeview(main, columns=("pesan",), show="headings", height=6)
        self.log.heading("pesan", text="Log")
        self.log.grid(row=10, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        main.rowconfigure(10, weight=1)

    def _file_row(self, parent: ttk.Frame, row: int, label: str, variable: StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(parent, text="Pilih...", command=command).grid(row=row, column=2, sticky="ew", pady=4)

    def _check_ffmpeg(self) -> None:
        if not find_tool("ffmpeg"):
            messagebox.showwarning("FFmpeg belum ditemukan", "Install FFmpeg dan pastikan perintah 'ffmpeg' tersedia di PATH.")
            self.status.set("FFmpeg belum ditemukan di PATH.")

    def _choose_video(self) -> None:
        paths = filedialog.askopenfilenames(title="Pilih satu atau banyak video", filetypes=VIDEO_EXTENSIONS)
        if paths:
            self.video_files = [Path(path) for path in paths]
            self.video_path.set(self._selection_label(self.video_files))
            self._suggest_output()
            self._log_duration("Video", self.video_files)

    def _choose_audio(self) -> None:
        paths = filedialog.askopenfilenames(title="Pilih satu atau banyak audio", filetypes=AUDIO_EXTENSIONS)
        if paths:
            self.audio_files = [Path(path) for path in paths]
            self.audio_path.set(self._selection_label(self.audio_files))
            self._log_duration("Audio", self.audio_files)

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(title="Simpan hasil", defaultextension=".mp4", filetypes=OUTPUT_EXTENSIONS)
        if path:
            self.output_path.set(path)

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
