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

## Isi Workbook yang Digenerate

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
