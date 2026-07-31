## Aplikasi Web Lokal Penggabung Video & Audio

Repository ini menyediakan aplikasi berbasis **Web Lokal (Offline)** yang berjalan di komputer Windows seperti aplikasi desktop. Saat `video_audio_merger.py` dijalankan, aplikasi otomatis menyalakan server lokal di `127.0.0.1` dan langsung membukanya dengan **PyWebView**, sehingga tampil tanpa address bar browser.

Aplikasi tetap mempertahankan fungsi utama yang sudah ada: menggabungkan video/audio lokal memakai **FFmpeg** dan mengunduh antrian/playlist YouTube memakai **yt-dlp** bila tersedia.

### Fitur

- UI web lokal offline tanpa CDN atau aset internet eksternal.
- Server lokal otomatis aktif saat file Python dijalankan.
- Tampilan desktop melalui PyWebView, tanpa address bar browser.
- Mengelola daftar file video dan audio melalui list yang dapat ditambah, dipilih beberapa itemnya, dihapus, dan diacak urutannya.
- Menggabungkan banyak video secara berurutan dan banyak audio secara berurutan menggunakan FFmpeg, termasuk opsi acak agar hasil setiap proses bisa berbeda.
- Mode penyesuaian durasi:
  - **Durasi terpendek**: hasil berhenti saat audio atau video yang paling pendek selesai.
  - **Ikuti durasi video**: audio baru dipotong atau di-loop otomatis sampai durasi video cukup.
  - **Ikuti durasi audio**: video dipotong atau di-loop otomatis sampai durasi audio cukup.
- Pengaturan volume audio asli video dan audio baru.
- Progress bar saat proses berjalan dan log proses di dalam aplikasi.
- Download playlist YouTube melalui tab **Download YouTube** menggunakan `yt-dlp`, lengkap dengan pemuatan daftar lagu/video satu per satu, list antrian download, dan list item yang sudah terdownload.
- Pilihan download playlist sebagai video MP4 terbaik atau audio MP3 saja.

### Mode Aplikasi

Aplikasi dapat dijalankan dalam dua mode:

#### Mode Development

Mode ini mengaktifkan debug PyWebView dan menampilkan log request HTTP server di terminal. Mode ini cocok untuk pengembangan UI atau debugging.

```bash
python video_audio_merger.py --mode development
```

Opsional, jika ingin membuka URL lokal di browser biasa selain jendela PyWebView:

```bash
set ATK_OPEN_BROWSER=1
python video_audio_merger.py --mode development
```

#### Mode Production

Mode ini adalah mode default. Server lokal tetap berjalan otomatis, tetapi debug dimatikan dan aplikasi langsung tampil sebagai jendela desktop PyWebView.

```bash
python video_audio_merger.py
```

Atau eksplisit:

```bash
python video_audio_merger.py --mode production
```

### Prasyarat

1. Install Python 3.14 atau versi lebih baru.
2. Install dependensi Python lokal:

```bash
pip install -r requirements.txt
```

3. Install FFmpeg dan pastikan perintah berikut bisa dijalankan dari terminal:

```bash
ffmpeg -version
ffprobe -version
```

`ffprobe` digunakan untuk membaca durasi media. Aplikasi tetap bisa berjalan tanpa `ffprobe`, tetapi informasi durasi tidak akan tampil.

4. Untuk fitur download playlist YouTube, install `yt-dlp` dan pastikan perintah berikut bisa dijalankan dari terminal:

```bash
yt-dlp --version
```

> Catatan offline: fitur penggabungan file lokal berjalan tanpa koneksi internet. Fitur YouTube tetap membutuhkan koneksi internet saat mengambil metadata atau mengunduh video/audio.

### Cara Menggunakan

Setelah aplikasi terbuka, gunakan tab **Gabung Media** untuk menggabungkan file lokal:

1. Klik **Tambah** pada panel **Daftar Video** lalu pilih satu atau banyak file video.
2. Klik **Tambah** pada panel **Daftar Audio** lalu pilih satu atau banyak file audio.
3. Gunakan **Hapus Terpilih** untuk menghapus beberapa item yang dipilih dari masing-masing list.
4. Gunakan **Acak** pada salah satu list atau **Acak Semua** untuk mengubah urutan video/audio sebelum proses gabung.
5. Tentukan file **Output**.
6. Pilih mode penyesuaian durasi.
7. Atur volume jika diperlukan.
8. Klik **Gabungkan Sekarang** dan pantau progress bar/log sampai proses selesai.

Gunakan tab **Download YouTube** untuk mengunduh playlist:

1. Tempel URL playlist YouTube pada kolom **URL Playlist**.
2. Klik **Muat Playlist** untuk mengambil daftar lagu/video dari playlist dan menampilkannya satu per satu di list **Antrian Download**.
3. Jika ingin menambahkan satu URL langsung tanpa memuat playlist, klik **Tambah URL**.
4. Gunakan **Hapus Terpilih** untuk membuang item tertentu dari antrian.
5. Pilih folder download lokal.
6. Pilih format **Video MP4 terbaik** atau **Audio MP3 saja**.
7. Klik **Download Antrian** dan pantau log/progress sampai selesai.
8. Item yang selesai diproses akan dipindahkan satu per satu ke list **Sudah Terdownload**.

### Kompatibilitas Darurat

UI Tkinter lama masih tersedia sebagai fallback bila diperlukan:

```bash
python video_audio_merger.py --legacy-tk
```

### Catatan Output

Aplikasi memakai metode cepat dengan concat demuxer untuk banyak file, `-stream_loop` untuk looping audio/video, dan menyalin stream video (`-c:v copy`) pada semua mode, sehingga video tidak di-encode ulang. Hanya audio output yang di-encode ke `aac` 192 kbps agar kompatibel dengan banyak pemutar video. Mode **Ikuti durasi video** akan me-loop audio bila audio lebih pendek, sedangkan mode **Ikuti durasi audio** akan me-loop video bila video lebih pendek. Agar mode super cepat tetap stabil, gunakan file video dalam urutan dengan codec/resolusi yang kompatibel. Jika file output sudah ada, opsi **Timpa file output jika sudah ada** dapat dimatikan untuk mencegah overwrite.
