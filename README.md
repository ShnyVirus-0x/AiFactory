# AI Shorts Factory

Studio pembuat video pendek yang berjalan **100% lokal** di Windows: transkripsi (faster-whisper), face tracking, subtitle per kata, dan render FFmpeg.
Server hanya mengikat `127.0.0.1`; tanpa unggah ke cloud, tanpa API AI eksternal, tanpa analitik.

> **Status jujur:** Fase 1–2 selesai, Fase 4 **sebagian** (Smart Crop & Render per klip), Fase 6 **sebagian** (Batch Renderer dan Export Center dasar). Deteksi klip AI (Qwen), editor timeline, template, thumbnail,
> diarization, dan jeda/lanjut antrean belum tersedia dan tampil "belum tersedia" di UI. Detail: `DEVELOPMENT_STATUS.md`.

## Fitur yang berfungsi
- **Proyek & perpustakaan video:** unggah banyak file (MP4/MOV/MKV/WEBM/AVI), validasi FFprobe, thumbnail, duplikat (sha256), cari/filter/urut, ganti nama, hapus.
- **Dashboard & diagnostik:** CPU/RAM/disk, GPU NVIDIA (`nvidia-smi`), NVENC (uji encode sungguhan), kompatibilitas CUDA untuk faster-whisper, model di memori (dapat dilepas), batas worker/VRAM/mode CPU.
- **Transkripsi:** faster-whisper, timestamp per kata, pemisahan kalimat, bahasa Indonesia/Inggris/otomatis, editor (edit, pisah, gabung, hapus, cari-ganti), pencarian, ekspor SRT/VTT/TXT, antrean persisten + batal. Model diunduh hanya setelah persetujuan (ukuran + ruang disk ditampilkan).
- **Smart Crop & Render:** klip manual dari video, face tracking OpenCV (multi-wajah, pemilihan pembicara, smoothing, kamera dikunci bila pembicara diam), layout isi/letterbox/split, crop manual/center, subtitle ASS karaoke (8 preset), pratinjau frame 9:16, render H.264/H.265, verifikasi hasil dengan FFprobe, unduh.
- **Batch Renderer & Export Center:** antrekan beberapa klip terpilih per proyek, batalkan job aktif, coba ulang job gagal, pratinjau video selesai, dan unduh hasil render. Jeda/lanjut antrean belum tersedia.
- **Encoder jujur:** NVENC dipakai hanya bila lolos uji encode; jika tidak, CPU — dan UI menampilkan encoder yang benar-benar dipakai.

## Instalasi (Windows 10/11)
Prasyarat: Python 3.11–3.13, Node.js 20+, FFmpeg + FFprobe di PATH. GPU NVIDIA opsional (driver dengan CUDA 12).
```
scripts\install.bat      :: venv, dependensi, .env, folder, database SQLite, build frontend, pemeriksaan GPU/CUDA/Ollama
scripts\start.bat        :: verifikasi layanan, jalankan Ollama bila ada, server, buka browser
scripts\stop.bat
scripts\check_gpu.bat
scripts\download_models.bat   :: unduh model dengan persetujuan; progres + ukuran ditampilkan
```
Buka http://127.0.0.1:8000. Model Whisper bawaan `large-v3-turbo` (±1.6 GB) diunduh dari halaman **Transkripsi** atau `download_models.bat` — tidak pernah otomatis.

### Menggunakan salinan dari GitHub

Di Windows, pasang prasyarat di atas, lalu jalankan dari PowerShell:
```
git clone https://github.com/ShnyVirus-0x/AiFactory.git
cd AiFactory
scripts\install.bat
scripts\start.bat
```
Setelah aplikasi terbuka, buat proyek, unggah video yang Anda miliki atau berhak olah, buat klip, lalu render. Batch Renderer menerima klip pilihan dari satu proyek; hasil yang selesai dapat dilihat dan diunduh di Export Center. Aplikasi berjalan lokal di komputer pengguna dan bukan situs demo yang di-host di GitHub.

## Pengembangan & tes
```
cd backend && pip install -r requirements-dev.txt && python -m pytest        # backend + integrasi
cd frontend && npm install && npm run dev && npm test
```
Catatan: pakai OpenCV 4.x (sudah dikunci di requirements). Build 5.x dari PyPI tidak menyertakan file cascade wajah.

## Keamanan
Bind 127.0.0.1; cek Origin pada WebSocket/CORS; nama file disanitasi dan disimpan acak; anti path traversal; unduhan hanya dari folder `storage/outputs`; argumen FFmpeg dibangun
sebagai list (tanpa shell); teks subtitle disanitasi dari injeksi override ASS; log JSON menyamarkan rahasia. Gunakan hanya video yang Anda miliki atau berhak olah.
