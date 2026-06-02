#!/usr/bin/env python3
"""Generate a no-VBA Excel workbook for Fotokopi & ATK management.

Uses only Python standard library to write XLSX Open XML parts. The workbook
contains Excel formulas, tables, validation, conditional formatting, charts, and
hyperlink-based app navigation. No macro/VBA parts are emitted.
"""
from __future__ import annotations

import html
import os
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

OUT = Path("dist/Sistem_Manajemen_Usaha_Fotokopi_ATK_No_VBA.xlsx")

DARK = "17365D"
BLUE = "1F4E79"
ACCENT = "5B9BD5"
LIGHT = "F3F6FA"
GRAY = "D9E2F3"
GREEN = "70AD47"
YELLOW = "FFC000"
RED = "C00000"
WHITE = "FFFFFF"
TEXT = "1F2937"

SHEETS = [
    "Dashboard", "Data Barang", "Barang Masuk", "Barang Keluar", "Penjualan", "Pembelian",
    "Stok Barang", "Hutang Supplier", "Piutang Pelanggan", "Data Karyawan", "Absensi", "Penggajian",
    "Laporan Harian", "Laporan Bulanan", "Laporan Tahunan", "Laba Rugi", "Pengaturan",
    "Nota A4", "Nota 58mm", "Nota 80mm", "Pivot Summary", "Panduan",
]

MENU = SHEETS[:17]

@dataclass
class Cell:
    v: Optional[object] = None
    f: Optional[str] = None
    s: Optional[int] = None
    t: Optional[str] = None

@dataclass
class Table:
    name: str
    ref: str
    headers: List[str]

@dataclass
class Validation:
    sqref: str
    formula1: str
    type: str = "list"
    allow_blank: bool = True

@dataclass
class CF:
    sqref: str
    formula: str
    dxf: int
    priority: int

@dataclass
class ChartSpec:
    title: str
    cat_ref: str
    val_ref: str
    anchor: str
    kind: str = "line"

@dataclass
class Sheet:
    name: str
    cells: Dict[Tuple[int,int], Cell] = field(default_factory=dict)
    widths: Dict[int, float] = field(default_factory=dict)
    merges: List[str] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    validations: List[Validation] = field(default_factory=list)
    cfs: List[CF] = field(default_factory=list)
    hyperlinks: Dict[Tuple[int,int], str] = field(default_factory=dict)
    charts: List[ChartSpec] = field(default_factory=list)
    freeze: Optional[str] = None

    def set(self, r, c, v=None, f=None, s=None, t=None):
        self.cells[(r,c)] = Cell(v, f, s, t)


def col(n: int) -> str:
    s = ""
    while n:
        n, rem = divmod(n-1, 26)
        s = chr(65+rem) + s
    return s

def cell_ref(r: int, c: int) -> str:
    return f"{col(c)}{r}"

def esc(x: object) -> str:
    return html.escape(str(x), quote=True)

def qsheet(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"

# Style indexes: see styles.xml
ST = {
    "normal": 0, "title": 1, "subtitle": 2, "header": 3, "nav": 4, "card": 5,
    "kpi": 6, "input": 7, "currency": 8, "date": 9, "percent": 10, "note": 11,
    "danger": 12, "good": 13, "warn": 14, "section": 15, "center": 16,
    "small": 17, "total": 18, "table": 19, "link": 20,
}

sheets = {name: Sheet(name) for name in SHEETS}

def add_topbar(ws: Sheet, subtitle: str = ""):
    ws.merge("A1:L1") if False else None
    ws.merges.append("A1:L1")
    ws.set(1,1,"SISTEM MANAJEMEN USAHA FOTOKOPI & ATK",s=ST["title"])
    if subtitle:
        ws.merges.append("A2:L2")
        ws.set(2,1,subtitle,s=ST["subtitle"])
    ws.set(3,1,"← Dashboard",s=ST["link"])
    ws.hyperlinks[(3,1)] = "Dashboard!A1"
    for i, name in enumerate(MENU, start=2):
        if i <= 12:
            ws.set(3,i,name[:14],s=ST["nav"])
            ws.hyperlinks[(3,i)] = f"{qsheet(name)}!A1"
    ws.widths.update({1:16,2:16,3:18,4:15,5:14,6:14,7:14,8:14,9:14,10:14,11:14,12:14})

def add_table(ws: Sheet, start_row: int, headers: List[str], name: str, rows: int = 120, start_col: int = 1):
    for j,h in enumerate(headers,start_col):
        ws.set(start_row,j,h,s=ST["header"])
    ref = f"{cell_ref(start_row,start_col)}:{cell_ref(start_row+rows, start_col+len(headers)-1)}"
    ws.tables.append(Table(name, ref, headers))
    return start_row+1

# Dashboard
ws = sheets["Dashboard"]
ws.merges += ["A1:P1","A2:P2"]
ws.set(1,1,"SISTEM MANAJEMEN USAHA FOTOKOPI & ATK",s=ST["title"])
ws.set(2,1,"Dashboard POS modern tanpa VBA/Macro — Excel 365 & Excel 2021",s=ST["subtitle"])
ws.widths.update({i:14 for i in range(1,17)})
ws.widths[1]=20
ws.set(4,1,"MENU UTAMA",s=ST["section"])
for idx, name in enumerate(MENU):
    r = 5 + idx//4
    c = 1 + (idx%4)*4
    ws.merges.append(f"{cell_ref(r,c)}:{cell_ref(r,c+2)}")
    ws.set(r,c,name,s=ST["nav"])
    ws.hyperlinks[(r,c)] = f"{qsheet(name)}!A1"
ws.set(10,1,"Ringkasan Hari Ini",s=ST["section"])
kpis = [
    ("Total Penjualan Hari Ini", "=SUMIFS(tblPenjualan[Subtotal],tblPenjualan[Tanggal],TODAY())"),
    ("Total Pembelian Hari Ini", "=SUMIFS(tblPembelian[Total],tblPembelian[Tanggal],TODAY())"),
    ("Total Transaksi Hari Ini", "=COUNTIFS(tblPenjualan[Tanggal],TODAY())"),
    ("Total Barang Keluar", "=SUMIFS(tblBarangKeluar[Qty],tblBarangKeluar[Tanggal],TODAY())"),
    ("Total Barang Masuk", "=SUMIFS(tblBarangMasuk[Qty],tblBarangMasuk[Tanggal],TODAY())"),
    ("Total Piutang", "=SUMIFS(tblPiutang[Nominal],tblPiutang[Status],\"Belum Lunas\")"),
    ("Total Hutang", "=SUMIFS(tblHutang[Nominal],tblHutang[Status],\"Belum Lunas\")"),
    ("Total Gaji Bulan Berjalan", "=SUMIFS(tblGaji[Gaji Bersih],tblGaji[Bulan],MONTH(TODAY()),tblGaji[Tahun],YEAR(TODAY()))"),
]
for i,(label,formula) in enumerate(kpis):
    r = 11 + (i//4)*3
    c = 1 + (i%4)*4
    ws.merges.append(f"{cell_ref(r,c)}:{cell_ref(r,c+2)}")
    ws.set(r,c,label,s=ST["card"])
    ws.merges.append(f"{cell_ref(r+1,c)}:{cell_ref(r+2,c+2)}")
    ws.set(r+1,c,f=formula[1:],s=ST["kpi"])
ws.set(18,1,"Filter Dashboard",s=ST["section"])
ws.set(19,1,"Mode",s=ST["header"]); ws.set(19,2,"Light",s=ST["input"])
ws.set(20,1,"Periode Mulai",s=ST["header"]); ws.set(20,2,f="TODAY()-30",s=ST["date"])
ws.set(21,1,"Periode Akhir",s=ST["header"]); ws.set(21,2,f="TODAY()",s=ST["date"])
ws.set(19,4,"Search Barang",s=ST["header"]); ws.set(19,5,"ketik nama/kategori",s=ST["input"])
ws.set(20,4,"Hasil Search (FILTER + LET)",s=ST["section"])
for c,h in enumerate(["Kode","Nama","Kategori","Stok","Harga"],4): ws.set(21,c,h,s=ST["header"])
ws.set(22,4,f='LET(q,$E$19,data,tblBarang[[Kode Barang]:[Harga Jual]],IF(q="","",FILTER(data,ISNUMBER(SEARCH(q,tblBarang[Nama Barang]&tblBarang[Kategori])),"Tidak ditemukan")))',s=ST["input"])
ws.validations.append(Validation("B19", "'Pengaturan'!$H$2:$H$3"))
# chart data helper
ws.set(23,1,"Penjualan 30 Hari Terakhir",s=ST["section"])
for c,h in enumerate(["Tanggal","Penjualan"],1): ws.set(24,c,h,s=ST["header"])
for i in range(30):
    r=25+i
    ws.set(r,1,f=f"TODAY()-{29-i}",s=ST["date"])
    ws.set(r,2,f=f"SUMIFS(tblPenjualan[Subtotal],tblPenjualan[Tanggal],A{r})",s=ST["currency"])
ws.set(23,5,"Top 10 Barang Terjual",s=ST["section"])
ws.set(24,5,"Barang",s=ST["header"]); ws.set(24,6,"Qty",s=ST["header"])
for i in range(10):
    r=25+i
    ws.set(r,5,f=f"IFERROR(INDEX(SORT(UNIQUE(FILTER(tblPenjualan[Nama Barang],tblPenjualan[Nama Barang]<>\"\"))),{i+1}),\"\")")
    ws.set(r,6,f=f"IF(E{r}=\"\",\"\",SUMIFS(tblPenjualan[Qty],tblPenjualan[Nama Barang],E{r}))")
ws.charts += [
    ChartSpec("Penjualan 30 Hari Terakhir", "Dashboard!$A$25:$A$54", "Dashboard!$B$25:$B$54", "H23", "line"),
    ChartSpec("Top 10 Barang Terjual", "Dashboard!$E$25:$E$34", "Dashboard!$F$25:$F$34", "H40", "bar"),
]
ws.freeze="A4"

# Pengaturan
ws=sheets["Pengaturan"]; add_topbar(ws,"Master toko, kategori, supplier, pelanggan, dan tema")
for r,c,v in [(5,1,"Nama Toko"),(6,1,"Alamat"),(7,1,"Nomor HP"),(8,1,"Pajak/PPN"),(9,1,"Diskon Default"),(10,1,"Jam Masuk Standar"),(11,1,"Tarif Lembur/Jam"),(12,1,"Logo (tempel gambar di area kanan)")]: ws.set(r,c,v,s=ST["header"])
vals=["TOKO FOTOKOPI & ATK","Jl. Contoh No. 1","0812-0000-0000",0.11,0, "08:00", 15000, "Area logo"]
for i,v in enumerate(vals,5): ws.set(i,2,v,s=ST["input"] if i not in (8,9,11) else ST["currency"])
list_blocks = {
    "Kategori": ["Fotokopi","Print","Scan","Laminating","Jilid","ATK","Kertas","Tinta","Aksesoris Komputer","Lainnya"],
    "Satuan": ["Pcs","Rim","Lembar","Box","Pack","Unit","Meter","Set"],
    "Supplier": ["Supplier Umum","Distributor ATK","Distributor Kertas","Distributor Tinta"],
    "Pelanggan": ["Umum","Pelanggan Kredit","Instansi","Sekolah"],
    "StatusBayar": ["Lunas","Belum Lunas"],
    "Mode": ["Light","Dark"],
}
start_col=4
for b,(title,items) in enumerate(list_blocks.items()):
    c=start_col+b*2
    ws.set(5,c,title,s=ST["section"])
    for i,item in enumerate(items,6): ws.set(i,c,item,s=ST["input"])
    ws.widths[c]=22
# Data Barang
ws=sheets["Data Barang"]; add_topbar(ws,"Master barang dengan auto kode, dropdown, lookup, dan status stok")
headers=["Kode Barang","Barcode","Nama Barang","Kategori","Satuan","Supplier","Harga Beli","Harga Jual","Minimum Stok","Stok Awal","Stok Saat Ini","Status"]
start=add_table(ws,5,headers,"tblBarang",150)
for r in range(start,start+150):
    ws.set(r,1,f=f"IF(C{r}=\"\",\"\",\"BRG-\"&TEXT(ROW()-5,\"0000\"))")
    ws.set(r,11,f=f"IF(C{r}=\"\",\"\",J{r}+SUMIFS(tblBarangMasuk[Qty],tblBarangMasuk[Kode Barang],A{r})-SUMIFS(tblBarangKeluar[Qty],tblBarangKeluar[Kode Barang],A{r})-SUMIFS(tblPenjualan[Qty],tblPenjualan[Nama Barang],C{r}))")
    ws.set(r,12,f=f"IF(C{r}=\"\",\"\",IF(K{r}<=0,\"Habis\",IF(K{r}<=I{r},\"Menipis\",\"Aman\")))")
ws.validations += [Validation("D6:D155","'Pengaturan'!$D$6:$D$15"), Validation("E6:E155","'Pengaturan'!$F$6:$F$13"), Validation("F6:F155","'Pengaturan'!$H$6:$H$9")]
ws.cfs += [CF("L6:L155", '$L6="Aman"',0,1), CF("L6:L155", '$L6="Menipis"',1,2), CF("L6:L155", '$L6="Habis"',2,3)]
ws.freeze="A6"

# Generic transaction sheets
def make_tx(sheet_name, table_name, headers, formulas, validations=None, subtitle=""):
    ws=sheets[sheet_name]; add_topbar(ws,subtitle)
    st=add_table(ws,5,headers,table_name,200)
    for r in range(st, st+200):
        for c, formula in formulas.items():
            ws.set(r,c,f=formula.format(r=r))
    for val in validations or []: ws.validations.append(val)
    ws.freeze="A6"
    return ws

make_tx("Barang Masuk","tblBarangMasuk",["Tanggal","Nomor Transaksi","Supplier","Kode Barang","Nama Barang","Qty","Harga Beli","Total"],{
    5:"IFERROR(XLOOKUP(D{r},tblBarang[Kode Barang],tblBarang[Nama Barang]),\"\")",
    7:"IFERROR(XLOOKUP(D{r},tblBarang[Kode Barang],tblBarang[Harga Beli]),0)",
    8:"IFERROR(F{r}*G{r},0)",
},[Validation("C6:C205","'Pengaturan'!$H$6:$H$9"),Validation("D6:D205","'Data Barang'!$A$6:$A$155")],"Pencatatan barang masuk dan update stok otomatis")
make_tx("Barang Keluar","tblBarangKeluar",["Tanggal","Nomor Transaksi","Kode Barang","Nama Barang","Qty","Harga Jual","Total"],{
    4:"IFERROR(XLOOKUP(C{r},tblBarang[Kode Barang],tblBarang[Nama Barang]),\"\")",
    6:"IFERROR(XLOOKUP(C{r},tblBarang[Kode Barang],tblBarang[Harga Jual]),0)",
    7:"IFERROR(E{r}*F{r},0)",
},[Validation("C6:C205","'Data Barang'!$A$6:$A$155")],"Pencatatan barang keluar/non-penjualan")
make_tx("Penjualan","tblPenjualan",["Tanggal","No Nota","Nama Barang","Qty","Harga","Diskon","Subtotal"],{
    5:"IFERROR(XLOOKUP(C{r},tblBarang[Nama Barang],tblBarang[Harga Jual]),0)",
    7:"IFERROR(D{r}*E{r}-F{r},0)",
},[Validation("C6:C205","'Data Barang'!$C$6:$C$155")],"Form kasir sederhana: pilih barang, isi qty, subtotal otomatis")
make_tx("Pembelian","tblPembelian",["Tanggal","No Pembelian","Supplier","Kode Barang","Nama Barang","Qty","Harga Beli","Total","Status Bayar"],{
    5:"IFERROR(XLOOKUP(D{r},tblBarang[Kode Barang],tblBarang[Nama Barang]),\"\")",
    7:"IFERROR(XLOOKUP(D{r},tblBarang[Kode Barang],tblBarang[Harga Beli]),0)",
    8:"IFERROR(F{r}*G{r},0)",
},[Validation("C6:C205","'Pengaturan'!$H$6:$H$9"),Validation("D6:D205","'Data Barang'!$A$6:$A$155"),Validation("I6:I205","'Pengaturan'!$L$6:$L$7")],"Pembelian supplier dan status pembayaran")

# Stock report
ws=sheets["Stok Barang"]; add_topbar(ws,"Laporan stok otomatis dengan indikator warna")
headers=["Kode Barang","Nama Barang","Kategori","Stok Awal","Barang Masuk","Barang Keluar","Penjualan","Stok Akhir","Minimum Stok","Status"]
st=add_table(ws,5,headers,"tblStok",150)
for r in range(st,st+150):
    ws.set(r,1,f=f"IFERROR(INDEX(tblBarang[Kode Barang],ROW()-5),\"\")")
    ws.set(r,2,f=f"IFERROR(XLOOKUP(A{r},tblBarang[Kode Barang],tblBarang[Nama Barang]),\"\")")
    ws.set(r,3,f=f"IFERROR(XLOOKUP(A{r},tblBarang[Kode Barang],tblBarang[Kategori]),\"\")")
    ws.set(r,4,f=f"IFERROR(XLOOKUP(A{r},tblBarang[Kode Barang],tblBarang[Stok Awal]),0)")
    ws.set(r,5,f=f"SUMIFS(tblBarangMasuk[Qty],tblBarangMasuk[Kode Barang],A{r})")
    ws.set(r,6,f=f"SUMIFS(tblBarangKeluar[Qty],tblBarangKeluar[Kode Barang],A{r})")
    ws.set(r,7,f=f"SUMIFS(tblPenjualan[Qty],tblPenjualan[Nama Barang],B{r})")
    ws.set(r,8,f=f"D{r}+E{r}-F{r}-G{r}")
    ws.set(r,9,f=f"IFERROR(XLOOKUP(A{r},tblBarang[Kode Barang],tblBarang[Minimum Stok]),0)")
    ws.set(r,10,f=f"IF(A{r}=\"\",\"\",IF(H{r}<=0,\"Habis\",IF(H{r}<=I{r},\"Menipis\",\"Aman\")))")
ws.cfs += [CF("J6:J155", '$J6="Aman"',0,1), CF("J6:J155", '$J6="Menipis"',1,2), CF("J6:J155", '$J6="Habis"',2,3)]

# Receivables/payables/employees/attendance/payroll
make_tx("Hutang Supplier","tblHutang",["Supplier","Tanggal","Nominal","Jatuh Tempo","Dibayar","Status"],{6:"IF(C{r}-E{r}<=0,\"Lunas\",\"Belum Lunas\")"},[Validation("A6:A205","'Pengaturan'!$H$6:$H$9")],"Kontrol hutang supplier")
make_tx("Piutang Pelanggan","tblPiutang",["Pelanggan","Tanggal","Nominal","Jatuh Tempo","Dibayar","Status"],{6:"IF(C{r}-E{r}<=0,\"Lunas\",\"Belum Lunas\")"},[Validation("A6:A205","'Pengaturan'!$J$6:$J$9")],"Kontrol piutang pelanggan")
ws=sheets["Data Karyawan"]; add_topbar(ws,"Master karyawan")
st=add_table(ws,5,["NIK","Nama","Jabatan","Alamat","Nomor HP","Tanggal Masuk","Gaji Pokok","Tunjangan"],"tblKaryawan",80)
ws.freeze="A6"
ws=sheets["Absensi"]; add_topbar(ws,"Absensi manual dengan jam kerja, terlambat, dan lembur otomatis")
st=add_table(ws,5,["Tanggal","NIK","Nama","Jam Masuk","Jam Keluar","Jam Kerja","Terlambat","Lembur"],"tblAbsensi",220)
for r in range(st,st+220):
    ws.set(r,3,f=f"IFERROR(XLOOKUP(B{r},tblKaryawan[NIK],tblKaryawan[Nama]),\"\")")
    ws.set(r,6,f=f"IFERROR((E{r}-D{r})*24,0)")
    ws.set(r,7,f=f"IFERROR(MAX(0,(D{r}-TIMEVALUE(Pengaturan!$B$10))*24),0)")
    ws.set(r,8,f=f"IFERROR(MAX(0,F{r}-8),0)")
ws.validations.append(Validation("B6:B225","'Data Karyawan'!$A$6:$A$85"))
ws=sheets["Penggajian"]; add_topbar(ws,"Penggajian otomatis per bulan")
st=add_table(ws,5,["Bulan","Tahun","NIK","Nama","Gaji Pokok","Tunjangan","Lembur","Potongan","Gaji Bersih"],"tblGaji",120)
for r in range(st,st+120):
    ws.set(r,4,f=f"IFERROR(XLOOKUP(C{r},tblKaryawan[NIK],tblKaryawan[Nama]),\"\")")
    ws.set(r,5,f=f"IFERROR(XLOOKUP(C{r},tblKaryawan[NIK],tblKaryawan[Gaji Pokok]),0)")
    ws.set(r,6,f=f"IFERROR(XLOOKUP(C{r},tblKaryawan[NIK],tblKaryawan[Tunjangan]),0)")
    ws.set(r,7,f=f"IFERROR(SUMIFS(tblAbsensi[Lembur],tblAbsensi[NIK],C{r})*Pengaturan!$B$11,0)")
    ws.set(r,9,f=f"E{r}+F{r}+G{r}-H{r}")
ws.validations.append(Validation("C6:C125","'Data Karyawan'!$A$6:$A$85"))

# Reports
for name,subtitle in [("Laporan Harian","Filter tanggal"),("Laporan Bulanan","Filter bulan dan tahun"),("Laporan Tahunan","Ringkasan tahunan"),("Laba Rugi","Pendapatan, HPP, biaya, dan laba bersih")]:
    ws=sheets[name]; add_topbar(ws,subtitle)
if True:
    ws=sheets["Laporan Harian"]
    ws.set(5,1,"Tanggal",s=ST["header"]); ws.set(5,2,f="TODAY()",s=ST["date"])
    metrics=[("Omzet", "SUMIFS(tblPenjualan[Subtotal],tblPenjualan[Tanggal],$B$5)"),("Pembelian","SUMIFS(tblPembelian[Total],tblPembelian[Tanggal],$B$5)"),("Laba Kotor","B7-B8"),("Gaji","SUMIFS(tblGaji[Gaji Bersih],tblGaji[Bulan],MONTH($B$5),tblGaji[Tahun],YEAR($B$5))"),("Laba Bersih","B9-B10")]
    for i,(m,f) in enumerate(metrics,7): ws.set(i,1,m,s=ST["header"]); ws.set(i,2,f=f,s=ST["currency"])
    ws=sheets["Laporan Bulanan"]; ws.set(5,1,"Bulan",s=ST["header"]); ws.set(5,2,f="MONTH(TODAY())",s=ST["input"]); ws.set(6,1,"Tahun",s=ST["header"]); ws.set(6,2,f="YEAR(TODAY())",s=ST["input"])
    monthf="MONTH(tblPenjualan[Tanggal])" # not used in SUMIFS, use SUMPRODUCT
    rows=[("Penjualan","SUMPRODUCT((MONTH(tblPenjualan[Tanggal])=$B$5)*(YEAR(tblPenjualan[Tanggal])=$B$6)*tblPenjualan[Subtotal])"),("Pembelian","SUMPRODUCT((MONTH(tblPembelian[Tanggal])=$B$5)*(YEAR(tblPembelian[Tanggal])=$B$6)*tblPembelian[Total])"),("Pengeluaran/Gaji","SUMIFS(tblGaji[Gaji Bersih],tblGaji[Bulan],$B$5,tblGaji[Tahun],$B$6)"),("Laba","B8-B9-B10")]
    for i,(m,f) in enumerate(rows,8): ws.set(i,1,m,s=ST["header"]); ws.set(i,2,f=f,s=ST["currency"])
    ws=sheets["Laporan Tahunan"]; ws.set(5,1,"Tahun",s=ST["header"]); ws.set(5,2,f="YEAR(TODAY())",s=ST["input"])
    for i,m in enumerate(range(1,13),7):
        ws.set(i,1,m,s=ST["center"]); ws.set(i,2,f=f"SUMPRODUCT((MONTH(tblPenjualan[Tanggal])=A{i})*(YEAR(tblPenjualan[Tanggal])=$B$5)*tblPenjualan[Subtotal])",s=ST["currency"]); ws.set(i,3,f=f"SUMPRODUCT((MONTH(tblPembelian[Tanggal])=A{i})*(YEAR(tblPembelian[Tanggal])=$B$5)*tblPembelian[Total])",s=ST["currency"]); ws.set(i,4,f=f"B{i}-C{i}",s=ST["currency"])
    for c,h in enumerate(["Bulan","Penjualan","Pembelian","Laba"],1): ws.set(6,c,h,s=ST["header"])
    ws.charts.append(ChartSpec("Tren Laba Rugi Tahunan","'Laporan Tahunan'!$A$7:$A$18","'Laporan Tahunan'!$D$7:$D$18","F6","line"))
    ws=sheets["Laba Rugi"]; ws.set(5,1,"Bulan",s=ST["header"]); ws.set(5,2,f="MONTH(TODAY())",s=ST["input"]); ws.set(6,1,"Tahun",s=ST["header"]); ws.set(6,2,f="YEAR(TODAY())",s=ST["input"])
    lr=[("Pendapatan","SUMPRODUCT((MONTH(tblPenjualan[Tanggal])=$B$5)*(YEAR(tblPenjualan[Tanggal])=$B$6)*tblPenjualan[Subtotal])"),("HPP","SUMPRODUCT((MONTH(tblPembelian[Tanggal])=$B$5)*(YEAR(tblPembelian[Tanggal])=$B$6)*tblPembelian[Total])"),("Gaji","SUMIFS(tblGaji[Gaji Bersih],tblGaji[Bulan],$B$5,tblGaji[Tahun],$B$6)"),("Operasional",0),("Listrik",0),("Internet",0),("Biaya Lain",0),("Laba Bersih","B8-SUM(B9:B14)")]
    for i,(m,f) in enumerate(lr,8): ws.set(i,1,m,s=ST["header"]); ws.set(i,2,f=f if isinstance(f,str) else None, v=f if not isinstance(f,str) else None, s=ST["total"] if m=="Laba Bersih" else ST["currency"])

# Nota templates
for name,width in [("Nota A4",12),("Nota 58mm",8),("Nota 80mm",10)]:
    ws=sheets[name]; add_topbar(ws,f"Template cetak {name.replace('Nota ','')}")
    ws.widths.update({1:width,2:width,3:width,4:width})
    ws.merges += ["A5:D5","A6:D6","A7:D7"]
    ws.set(5,1,f="Pengaturan!B5",s=ST["title"]); ws.set(6,1,f="Pengaturan!B6",s=ST["center"]); ws.set(7,1,f="Pengaturan!B7",s=ST["center"])
    ws.set(9,1,"No Nota",s=ST["header"]); ws.set(9,2,"Input",s=ST["input"]); ws.set(10,1,"Tanggal",s=ST["header"]); ws.set(10,2,f="TODAY()",s=ST["date"])
    for c,h in enumerate(["Barang","Qty","Harga","Total"],1): ws.set(12,c,h,s=ST["header"])
    for r in range(13,23): ws.set(r,4,f=f"B{r}*C{r}",s=ST["currency"])
    ws.set(24,3,"Total",s=ST["header"]); ws.set(24,4,f="SUM(D13:D22)",s=ST["currency"]); ws.set(25,3,"Bayar",s=ST["header"]); ws.set(25,4,0,s=ST["input"]); ws.set(26,3,"Kembalian",s=ST["header"]); ws.set(26,4,f="D25-D24",s=ST["currency"])

# Pivot Summary / dynamic pivot-like summaries
ws=sheets["Pivot Summary"]; add_topbar(ws,"Ringkasan pivot-ready dan area Pivot Table/Pivot Chart")
ws.set(5,1,"Area ini disiapkan untuk Pivot Table/Pivot Chart Excel. Gunakan Insert > PivotTable dari tblPenjualan, tblPembelian, tblStok.",s=ST["note"])
ws.set(7,1,"Kategori",s=ST["header"]); ws.set(7,2,"Qty Terjual",s=ST["header"])
for i in range(10):
    r=8+i; ws.set(r,1,f=f"IFERROR(INDEX('Pengaturan'!$D$6:$D$15,{i+1}),\"\")"); ws.set(r,2,f=f"IF(A{r}=\"\",\"\",SUMPRODUCT((tblBarang[Kategori]=A{r})*SUMIFS(tblPenjualan[Qty],tblPenjualan[Nama Barang],tblBarang[Nama Barang])))")
ws.charts.append(ChartSpec("Kategori Terlaris","'Pivot Summary'!$A$8:$A$17","'Pivot Summary'!$B$8:$B$17","D7","bar"))

# Panduan
ws=sheets["Panduan"]; add_topbar(ws,"Dokumentasi workbook")
notes=[
"Workbook ini 100% tanpa VBA, tanpa macro, dan tanpa Visual Basic.",
"Semua input utama menggunakan Excel Table: tblBarang, tblPenjualan, tblPembelian, tblBarangMasuk, tblBarangKeluar, tblStok, tblHutang, tblPiutang, tblKaryawan, tblAbsensi, tblGaji.",
"Navigasi aplikasi dibuat dengan hyperlink internal pada Dashboard dan topbar setiap sheet.",
"Formula utama memakai XLOOKUP, SUMIFS, COUNTIFS, FILTER/UNIQUE/SORT, LET-ready design, SUMPRODUCT, IFERROR, dan formula dinamis Excel 365/2021.",
"Untuk Pivot Table/Pivot Chart interaktif, gunakan sheet Pivot Summary lalu Insert > PivotTable dari tabel database yang tersedia; workbook sudah menyediakan tabel sumber dan grafik ringkasan.",
"Dark/Light Mode disediakan sebagai selector tema di Dashboard/Pengaturan; warna workbook memakai palet biru tua, putih, dan abu-abu muda.",
]
for i,n in enumerate(notes,5): ws.merges.append(f"A{i}:L{i}"); ws.set(i,1,n,s=ST["note"])
ws.set(12,1,"Contoh INDEX MATCH harga jual barang pertama",s=ST["header"])
ws.set(12,2,f="IFERROR(INDEX(tblBarang[Harga Jual],MATCH(tblBarang[Nama Barang],tblBarang[Nama Barang],0)),0)",s=ST["currency"])

# Add some sample rows for usability
sample = sheets["Data Barang"]
rows=[("", "8990001","Fotokopi Hitam Putih","Fotokopi","Lembar","Supplier Umum",100,300,100,500), ("","8990002","Print Warna A4","Print","Lembar","Supplier Umum",1500,3000,50,100), ("","8990003","Kertas A4 80gsm","Kertas","Rim","Distributor Kertas",48000,55000,5,20), ("","8990004","Pulpen Gel","ATK","Pcs","Distributor ATK",2500,4000,10,50)]
for i,row in enumerate(rows,6):
    for c,v in enumerate(row,1):
        if c!=1: sample.set(i,c,v,s=ST["currency"] if c in (7,8) else ST["input"])

# XML writers
def write_styles() -> str:
    # 21 xf styles, fills include 0 none,1 gray125, then custom indexes 2..8
    fonts = [
        '<font><sz val="11"/><color rgb="FF1F2937"/><name val="Calibri"/></font>',
        '<font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>',
        '<font><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>',
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>',
        '<font><b/><sz val="11"/><color rgb="FF1F4E79"/><u/><name val="Calibri"/></font>',
        '<font><b/><sz val="16"/><color rgb="FF1F4E79"/><name val="Calibri"/></font>',
        '<font><sz val="9"/><color rgb="FF6B7280"/><name val="Calibri"/></font>',
    ]
    fills = ['<fill><patternFill patternType="none"/></fill>','<fill><patternFill patternType="gray125"/></fill>']
    for color in [DARK, BLUE, ACCENT, LIGHT, GRAY, GREEN, YELLOW, RED, WHITE]:
        fills.append(f'<fill><patternFill patternType="solid"><fgColor rgb="FF{color}"/><bgColor indexed="64"/></patternFill></fill>')
    borders = ['<border/>','<border><left style="thin"><color rgb="FFD9E2F3"/></left><right style="thin"><color rgb="FFD9E2F3"/></right><top style="thin"><color rgb="FFD9E2F3"/></top><bottom style="thin"><color rgb="FFD9E2F3"/></bottom></border>']
    numfmts = '<numFmts count="4"><numFmt numFmtId="164" formatCode="#,##0"/><numFmt numFmtId="165" formatCode="dd/mm/yyyy"/><numFmt numFmtId="166" formatCode="0%"/><numFmt numFmtId="167" formatCode="hh:mm"/></numFmts>'
    xfs = []
    def xf(font=0,fill=0,border=1,num=0,align=''):
        attrs=f'numFmtId="{num}" fontId="{font}" fillId="{fill}" borderId="{border}" xfId="0"'
        if num or align: attrs += ' applyNumberFormat="1"' if num else ''
        return f'<xf {attrs}>{align}</xf>' if align else f'<xf {attrs}/>'
    center='<alignment horizontal="center" vertical="center" wrapText="1"/>'
    left='<alignment vertical="center" wrapText="1"/>'
    xfs += [xf(), xf(1,2,1,0,center), xf(2,3,1,0,center), xf(3,3,1,0,center), xf(3,4,1,0,center), xf(3,5,1,0,center), xf(5,8,1,164,center), xf(0,9,1,0,left), xf(0,9,1,164), xf(0,9,1,165), xf(0,9,1,166), xf(6,6,1,0,left), xf(3,9,1,0,center), xf(3,7,1,0,center), xf(0,8,1,0,center), xf(3,3,1,0,left), xf(0,9,1,0,center), xf(6,9,1,0,left), xf(5,9,1,164), xf(3,4,1,0,center), xf(4,9,1,0,center)]
    dxfs = f'<dxfs count="3"><dxf><fill><patternFill patternType="solid"><fgColor rgb="FF{GREEN}"/></patternFill></fill><font><color rgb="FFFFFFFF"/><b/></font></dxf><dxf><fill><patternFill patternType="solid"><fgColor rgb="FF{YELLOW}"/></patternFill></fill><font><color rgb="FF000000"/><b/></font></dxf><dxf><fill><patternFill patternType="solid"><fgColor rgb="FF{RED}"/></patternFill></fill><font><color rgb="FFFFFFFF"/><b/></font></dxf></dxfs>'
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{numfmts}<fonts count="{len(fonts)}">{"".join(fonts)}</fonts><fills count="{len(fills)}">{"".join(fills)}</fills><borders count="{len(borders)}">{"".join(borders)}</borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>{dxfs}</styleSheet>'

def sheet_xml(ws: Sheet, sheet_id: int, table_start_id: int, has_drawing: bool) -> str:
    max_r=max([r for r,c in ws.cells] + [40]); max_c=max([c for r,c in ws.cells] + [12])
    parts=['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">']
    if ws.freeze:
        parts.append(f'<sheetViews><sheetView workbookViewId="0"><pane topLeftCell="{ws.freeze}" activePane="bottomRight" state="frozen" ySplit="{int(ws.freeze[1:])-1}"/></sheetView></sheetViews>')
    else: parts.append('<sheetViews><sheetView workbookViewId="0"/></sheetViews>')
    parts.append('<sheetFormatPr defaultRowHeight="20"/>')
    parts.append('<cols>' + ''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i,w in ws.widths.items()) + '</cols>')
    parts.append('<sheetData>')
    for r in range(1,max_r+1):
        rowcells=[]
        for c in range(1,max_c+1):
            cell=ws.cells.get((r,c))
            if not cell: continue
            ref=cell_ref(r,c); sattr=f' s="{cell.s}"' if cell.s is not None else ''
            if cell.f is not None:
                rowcells.append(f'<c r="{ref}"{sattr}><f>{esc(cell.f)}</f></c>')
            elif isinstance(cell.v,(int,float)):
                rowcells.append(f'<c r="{ref}"{sattr}><v>{cell.v}</v></c>')
            elif cell.v is None:
                rowcells.append(f'<c r="{ref}"{sattr}/>')
            else:
                rowcells.append(f'<c r="{ref}" t="inlineStr"{sattr}><is><t>{esc(cell.v)}</t></is></c>')
        if rowcells: parts.append(f'<row r="{r}">' + ''.join(rowcells) + '</row>')
    parts.append('</sheetData>')
    if ws.merges: parts.append(f'<mergeCells count="{len(ws.merges)}">' + ''.join(f'<mergeCell ref="{m}"/>' for m in ws.merges) + '</mergeCells>')
    if ws.cfs:
        for cf in ws.cfs: parts.append(f'<conditionalFormatting sqref="{cf.sqref}"><cfRule type="expression" dxfId="{cf.dxf}" priority="{cf.priority}"><formula>{esc(cf.formula)}</formula></cfRule></conditionalFormatting>')
    if ws.validations:
        parts.append(f'<dataValidations count="{len(ws.validations)}">')
        for v in ws.validations:
            allow='1' if v.allow_blank else '0'
            parts.append(f'<dataValidation type="{v.type}" allowBlank="{allow}" showErrorMessage="1" sqref="{v.sqref}"><formula1>{esc(v.formula1)}</formula1></dataValidation>')
        parts.append('</dataValidations>')
    if ws.hyperlinks:
        parts.append('<hyperlinks>' + ''.join(f'<hyperlink ref="{cell_ref(r,c)}" location="{esc(loc)}" display="{esc(ws.cells[(r,c)].v or loc)}"/>' for (r,c),loc in ws.hyperlinks.items()) + '</hyperlinks>')
    if has_drawing: parts.append(f'<drawing r:id="rId1"/>')
    if ws.tables:
        parts.append(f'<tableParts count="{len(ws.tables)}">' + ''.join(f'<tablePart r:id="rId{idx+1 if not has_drawing else idx+2}"/>' for idx,_ in enumerate(ws.tables)) + '</tableParts>')
    parts.append('</worksheet>')
    return ''.join(parts)

def table_xml(table: Table, tid:int) -> str:
    cols=''.join(f'<tableColumn id="{i}" name="{esc(h)}"/>' for i,h in enumerate(table.headers,1))
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" id="{tid}" name="{table.name}" displayName="{table.name}" ref="{table.ref}" totalsRowShown="0"><autoFilter ref="{table.ref}"/><tableColumns count="{len(table.headers)}">{cols}</tableColumns><tableStyleInfo name="TableStyleMedium2" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/></table>'

def chart_xml(ch: ChartSpec, cid:int) -> str:
    chart_type = 'barChart' if ch.kind=='bar' else 'lineChart'
    grouping = '<barDir val="bar"/><grouping val="clustered"/>' if ch.kind=='bar' else '<grouping val="standard"/>'
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><c:chart><c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{esc(ch.title)}</a:t></a:r></a:p></c:rich></c:tx></c:title><c:plotArea><c:layout/><c:{chart_type}>{grouping}<c:ser><c:idx val="0"/><c:order val="0"/><c:cat><c:strRef><c:f>{esc(ch.cat_ref)}</c:f></c:strRef></c:cat><c:val><c:numRef><c:f>{esc(ch.val_ref)}</c:f></c:numRef></c:val></c:ser><c:axId val="10"/><c:axId val="20"/></c:{chart_type}><c:catAx><c:axId val="10"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="b"/><c:crossAx val="20"/></c:catAx><c:valAx><c:axId val="20"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="l"/><c:crossAx val="10"/></c:valAx></c:plotArea><c:legend><c:legendPos val="b"/></c:legend></c:chart></c:chartSpace>'''

def drawing_xml(charts: List[ChartSpec]) -> str:
    anchors=[]
    for i,ch in enumerate(charts,1):
        # parse anchor like H23
        import re
        m=re.match(r'([A-Z]+)(\d+)',ch.anchor); ac=m.group(1); ar=int(m.group(2))
        cn=0
        for chh in ac: cn=cn*26+ord(chh)-64
        from_col=cn-1; from_row=ar-1
        anchors.append(f'''<xdr:twoCellAnchor><xdr:from><xdr:col>{from_col}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{from_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>{from_col+7}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{from_row+14}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to><xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="{i}" name="Chart {i}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr><xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" r:id="rId{i}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>''')
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">' + ''.join(anchors) + '</xdr:wsDr>'

def rels_xml(rels: List[Tuple[str,str,str]]) -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="{rid}" Type="{typ}" Target="{target}"/>' for rid,typ,target in rels) + '</Relationships>'

# package
OUT.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(SHEETS)+1)) + ''.join(f'<Override PartName="/xl/tables/table{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>' for i in range(1, sum(len(s.tables) for s in sheets.values())+1)) + ''.join(f'<Override PartName="/xl/charts/chart{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>' for i in range(1, sum(len(s.charts) for s in sheets.values())+1)) + ''.join(f'<Override PartName="/xl/drawings/drawing{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>' for i,s in enumerate([s for s in sheets.values() if s.charts],1)) + '</Types>')
    z.writestr('_rels/.rels', rels_xml([('rId1','http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument','xl/workbook.xml')]))
    defined_names = '<definedNames><definedName name="rngKategori">\'Pengaturan\'!$D$6:$D$15</definedName><definedName name="rngSatuan">\'Pengaturan\'!$F$6:$F$13</definedName><definedName name="rngSupplier">\'Pengaturan\'!$H$6:$H$9</definedName><definedName name="rngPelanggan">\'Pengaturan\'!$J$6:$J$9</definedName><definedName name="rngStatusBayar">\'Pengaturan\'!$L$6:$L$7</definedName><definedName name="nmPajak">\'Pengaturan\'!$B$8</definedName><definedName name="nmDiskonDefault">\'Pengaturan\'!$B$9</definedName></definedNames>'
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + ''.join(f'<sheet name="{esc(name)}" sheetId="{i}" r:id="rId{i}"/>' for i,name in enumerate(SHEETS,1)) + '</sheets>' + defined_names + '<calcPr calcMode="auto"/></workbook>'
    z.writestr('xl/workbook.xml', workbook)
    wb_rels=[(f'rId{i}','http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet',f'worksheets/sheet{i}.xml') for i in range(1,len(SHEETS)+1)] + [('rId100','http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles','styles.xml')]
    z.writestr('xl/_rels/workbook.xml.rels', rels_xml(wb_rels))
    z.writestr('xl/styles.xml', write_styles())
    table_id=1; chart_id=1; drawing_id=1
    for si,name in enumerate(SHEETS,1):
        ws=sheets[name]; has_drawing=bool(ws.charts)
        z.writestr(f'xl/worksheets/sheet{si}.xml', sheet_xml(ws, si, table_id, has_drawing))
        rels=[]
        rid=1
        if has_drawing:
            rels.append(('rId1','http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing',f'../drawings/drawing{drawing_id}.xml')); rid=2
        for t in ws.tables:
            rels.append((f'rId{rid}','http://schemas.openxmlformats.org/officeDocument/2006/relationships/table',f'../tables/table{table_id}.xml'))
            z.writestr(f'xl/tables/table{table_id}.xml', table_xml(t,table_id))
            table_id+=1; rid+=1
        if rels: z.writestr(f'xl/worksheets/_rels/sheet{si}.xml.rels', rels_xml(rels))
        if has_drawing:
            z.writestr(f'xl/drawings/drawing{drawing_id}.xml', drawing_xml(ws.charts))
            drels=[]
            for ch in ws.charts:
                z.writestr(f'xl/charts/chart{chart_id}.xml', chart_xml(ch, chart_id))
                drels.append((f'rId{len(drels)+1}','http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart',f'../charts/chart{chart_id}.xml'))
                chart_id+=1
            z.writestr(f'xl/drawings/_rels/drawing{drawing_id}.xml.rels', rels_xml(drels))
            drawing_id+=1
print(f"Generated {OUT} ({OUT.stat().st_size:,} bytes)")
