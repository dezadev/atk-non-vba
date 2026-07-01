## Aplikasi Desktop Penggabung Video & Audio

Repository ini juga menyediakan aplikasi desktop sederhana berbasis **Python 3.14**, **Tkinter**, **FFmpeg**, dan opsional **yt-dlp** untuk menggabungkan file video/audio serta mengunduh playlist YouTube.

### Fitur

- Mengelola daftar file video dan audio melalui list yang dapat ditambah, dipilih beberapa itemnya, dihapus, dan diacak urutannya.
- Menggabungkan banyak video secara berurutan dan banyak audio secara berurutan menggunakan FFmpeg, termasuk opsi acak agar hasil setiap proses bisa berbeda.
- Mode penyesuaian durasi:
  - **Durasi terpendek**: hasil berhenti saat audio atau video yang paling pendek selesai.
  - **Ikuti durasi video**: audio baru dipotong atau di-loop otomatis sampai durasi video cukup.
  - **Ikuti durasi audio**: video dipotong atau di-loop otomatis sampai durasi audio cukup.
- Pengaturan volume audio asli video dan audio baru.
- Tampilan desktop sederhana berbahasa Indonesia.
- Progress bar saat proses berjalan dan popup notifikasi ketika proses selesai atau gagal.
- Download playlist YouTube melalui tab **Download YouTube** menggunakan `yt-dlp`, lengkap dengan list antrian download dan list item yang sudah terdownload.
- Pilihan download playlist sebagai video MP4 terbaik atau audio MP3 saja.

### Prasyarat

1. Install Python 3.14 atau versi lebih baru.
2. Install FFmpeg dan pastikan perintah berikut bisa dijalankan dari terminal:

```bash
ffmpeg -version
ffprobe -version
```

`ffprobe` digunakan untuk membaca durasi media. Aplikasi tetap bisa berjalan tanpa `ffprobe`, tetapi informasi durasi tidak akan tampil.

3. Untuk fitur download playlist YouTube, install `yt-dlp` dan pastikan perintah berikut bisa dijalankan dari terminal:

```bash
yt-dlp --version
```

### Cara Menjalankan

```bash
python video_audio_merger.py
```

Setelah aplikasi terbuka, gunakan tab **Gabung Media** untuk menggabungkan file lokal:

1. Klik **Tambah** pada panel **Daftar Video** lalu pilih satu atau banyak file video.
2. Klik **Tambah** pada panel **Daftar Audio** lalu pilih satu atau banyak file audio.
3. Gunakan **Hapus Terpilih** untuk menghapus beberapa item yang dipilih dari masing-masing list.
4. Gunakan **Acak** pada salah satu list atau **Acak Semua** untuk mengubah urutan video/audio sebelum proses gabung.
5. Tentukan file **Output**.
6. Pilih mode penyesuaian durasi.
7. Atur volume jika diperlukan.
8. Klik **Gabungkan Sekarang** dan pantau progress bar sampai popup selesai muncul.

Gunakan tab **Download YouTube** untuk mengunduh playlist:

1. Tempel URL playlist YouTube pada kolom **URL Playlist**.
2. Klik **Tambah ke Antrian** untuk memasukkan URL ke list **Antrian Download**.
3. Ulangi langkah sebelumnya jika ingin menambahkan beberapa playlist.
4. Pilih folder download lokal.
5. Pilih format **Video MP4 terbaik** atau **Audio MP3 saja**.
6. Klik **Download Antrian** dan pantau log/progress sampai popup selesai muncul.
7. Playlist yang selesai diproses akan dipindahkan ke list **Sudah Terdownload**.

Gunakan tab **Download YouTube** untuk mengunduh playlist:

1. Tempel URL playlist YouTube pada kolom **URL Playlist**.
2. Pilih folder download lokal.
3. Pilih format **Video MP4 terbaik** atau **Audio MP3 saja**.
4. Klik **Download Playlist** dan pantau log/progress sampai popup selesai muncul.

### Catatan Output

Aplikasi memakai metode cepat dengan concat demuxer untuk banyak file, `-stream_loop` untuk looping audio/video, dan menyalin stream video (`-c:v copy`) pada semua mode, sehingga video tidak di-encode ulang. Hanya audio output yang di-encode ke `aac` 192 kbps agar kompatibel dengan banyak pemutar video. Mode **Ikuti durasi video** akan me-loop audio bila audio lebih pendek, sedangkan mode **Ikuti durasi audio** akan me-loop video bila video lebih pendek. Agar mode super cepat tetap stabil, gunakan file video dalam urutan dengan codec/resolusi yang kompatibel. Jika file output sudah ada, opsi **Timpa file output jika sudah ada** dapat dimatikan untuk mencegah overwrite.
