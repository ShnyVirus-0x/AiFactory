# AI Shorts Factory — Fase 1 (Fondasi)

Studio pembuat video pendek yang berjalan **100% lokal** di Windows. Server hanya mengikat `127.0.0.1`,
tanpa unggah ke cloud, tanpa API AI eksternal, tanpa analitik.

> **Status jujur:** hanya **Fase 1 dari 8** yang selesai. Modul lain tampil di UI sebagai "belum tersedia".
> Lihat `DEVELOPMENT_STATUS.md`.

## Yang sudah berfungsi (Fase 1)
- Proyek: buat, ubah, arsip, hapus (file ikut terhapus, hanya di dalam `storage/`)
- Unggah banyak video (MP4/MOV/MKV/WEBM/AVI) dengan progres nyata, validasi ffprobe, thumbnail, deteksi duplikat (sha256)
- Perpustakaan: cari, filter, urutkan, ganti nama, hapus, pratinjau
- Dashboard & diagnostik: CPU/RAM/disk, GPU NVIDIA (via `nvidia-smi`), NVENC (uji encode sungguhan), cek FFmpeg/Ollama
- Database SQLite + migrasi Alembic (11 tabel), WebSocket event real-time

## Instalasi (Windows)
Prasyarat: Python 3.11+, Node.js 20+, FFmpeg di PATH.
```
scripts\install.bat
scripts\start.bat
```
Buka http://127.0.0.1:8000. Berhenti: `scripts\stop.bat`. Cek GPU: `scripts\check_gpu.bat`.

## Pengembangan
```
cd backend && pip install -r requirements-dev.txt && python -m pytest
cd frontend && npm install && npm run dev   # proxy ke backend :8000
```

## Keamanan
Bind 127.0.0.1, cek Origin pada WebSocket/CORS, nama file disanitasi dan disimpan acak, anti path traversal,
unduhan hanya dari folder aplikasi, tidak ada eksekusi shell dari input pengguna.
Gunakan hanya video yang Anda miliki atau berhak olah.
