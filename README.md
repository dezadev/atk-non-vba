# SISTEM MANAJEMEN USAHA FOTOKOPI & ATK — Excel No VBA

Repository ini menyediakan **generator workbook Excel** untuk aplikasi manajemen usaha Fotokopi & ATK. File workbook `.xlsx` bersifat **binary artifact**, sehingga **tidak disimpan di PR/repository**. Untuk membuat workbook siap pakai secara lokal, jalankan generator:

```bash
python scripts/generate_workbook.py
```

Hasilnya akan dibuat di:

- `dist/Sistem_Manajemen_Usaha_Fotokopi_ATK_No_VBA.xlsx`

Workbook yang dihasilkan ditujukan untuk Microsoft Excel 365 dan Excel 2021 dengan prinsip **100% fitur Excel tanpa VBA, tanpa Macro, dan tanpa Visual Basic**. Database disimpan di sheet Excel dalam bentuk Excel Table, sedangkan perhitungan menggunakan formula modern, data validation, conditional formatting, named range, dan grafik Excel.

## Kenapa File `.xlsx` Tidak Dilacak Git?

File `.xlsx` adalah file biner. Agar PR tetap dapat direview sebagai teks dan tidak ditolak oleh platform yang tidak mendukung file biner, repository hanya melacak:

- `scripts/generate_workbook.py` sebagai sumber pembuatan workbook.
- `README.md` sebagai dokumentasi penggunaan dan struktur workbook.
- `.gitignore` untuk mencegah file hasil generate `.xlsx` ikut ter-commit.

## Isi Workbook yang Dihasilkan

| Area | Sheet / Tabel | Fungsi Utama |
| --- | --- | --- |
| Dashboard | `Dashboard` | Navigasi internal, KPI harian, grafik 30 hari, top barang, search barang berbasis `LET` + `FILTER`. |
| Master Barang | `Data Barang` / `tblBarang` | Auto kode barang, dropdown kategori/satuan/supplier, stok saat ini, status stok. |
| Barang Masuk | `Barang Masuk` / `tblBarangMasuk` | Lookup nama barang, harga beli, total, dan sumber update stok. |
| Barang Keluar | `Barang Keluar` / `tblBarangKeluar` | Lookup barang, harga jual, total, dan pengurang stok. |
| Penjualan | `Penjualan` / `tblPenjualan` | Form kasir sederhana dengan subtotal otomatis. |
| Pembelian | `Pembelian` / `tblPembelian` | Pembelian supplier dan status pembayaran. |
| Stok | `Stok Barang` / `tblStok` | Stok awal, masuk, keluar, penjualan, stok akhir, status warna. |
| Keuangan | `Hutang Supplier`, `Piutang Pelanggan`, `Laba Rugi` | Status lunas otomatis dan laporan laba rugi. |
| SDM | `Data Karyawan`, `Absensi`, `Penggajian` | Master karyawan, jam kerja, terlambat, lembur, gaji bersih. |
| Laporan | `Laporan Harian`, `Laporan Bulanan`, `Laporan Tahunan` | Rekap omzet, pembelian, pengeluaran, dan laba. |
| Cetak Nota | `Nota A4`, `Nota 58mm`, `Nota 80mm` | Template nota cetak beberapa ukuran. |
| Pivot | `Pivot Summary` | Area sumber dan ringkasan siap Pivot Table/Pivot Chart. |
| Pengaturan | `Pengaturan` | Nama toko, alamat, HP, pajak, diskon, kategori, satuan, supplier, pelanggan, status, mode tema. |
| Panduan | `Panduan` | Catatan penggunaan workbook. |

## Named Range

Workbook mendefinisikan named range berikut untuk memudahkan validasi dan pengembangan:

- `rngKategori`
- `rngSatuan`
- `rngSupplier`
- `rngPelanggan`
- `rngStatusBayar`
- `nmPajak`
- `nmDiskonDefault`

## Formula Utama yang Digunakan

- `XLOOKUP` untuk lookup nama barang, harga, data karyawan.
- `INDEX` + `MATCH` sebagai contoh pola lookup alternatif.
- `SUMIFS` dan `COUNTIFS` untuk KPI, stok, hutang/piutang, laporan.
- `FILTER`, `UNIQUE`, `SORT`, dan `LET` untuk search barang dan ringkasan dinamis.
- `IFERROR` untuk tampilan input yang bersih.
- `SUMPRODUCT` untuk rekap laporan bulanan/tahunan berdasarkan bulan dan tahun.

## Cara Validasi Workbook Lokal

Setelah menjalankan generator, workbook dapat divalidasi dengan:

```bash
unzip -t dist/Sistem_Manajemen_Usaha_Fotokopi_ATK_No_VBA.xlsx
```

Generator hanya menggunakan Python standard library dan menghasilkan file `.xlsx` biasa tanpa komponen macro/VBA.

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
- Download playlist YouTube melalui tab **Download YouTube** menggunakan `yt-dlp`, lengkap dengan pemuatan daftar lagu/video satu per satu, list antrian download, dan list item yang sudah terdownload.
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
2. Klik **Muat Playlist** untuk mengambil daftar lagu/video dari playlist dan menampilkannya satu per satu di list **Antrian Download**.
3. Jika ingin menambahkan satu URL langsung tanpa memuat playlist, klik **Tambah URL**.
4. Gunakan **Hapus Terpilih** untuk membuang item tertentu dari antrian.
5. Pilih folder download lokal.
6. Pilih format **Video MP4 terbaik** atau **Audio MP3 saja**.
7. Klik **Download Antrian** dan pantau log/progress sampai popup selesai muncul.
8. Item yang selesai diproses akan dipindahkan satu per satu ke list **Sudah Terdownload**.

### Catatan Output

Aplikasi memakai metode cepat dengan concat demuxer untuk banyak file, `-stream_loop` untuk looping audio/video, dan menyalin stream video (`-c:v copy`) pada semua mode, sehingga video tidak di-encode ulang. Hanya audio output yang di-encode ke `aac` 192 kbps agar kompatibel dengan banyak pemutar video. Mode **Ikuti durasi video** akan me-loop audio bila audio lebih pendek, sedangkan mode **Ikuti durasi audio** akan me-loop video bila video lebih pendek. Agar mode super cepat tetap stabil, gunakan file video dalam urutan dengan codec/resolusi yang kompatibel. Jika file output sudah ada, opsi **Timpa file output jika sudah ada** dapat dimatikan untuk mencegah overwrite.
