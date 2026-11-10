# DEVELOPMENT STATUS

## Fase saat ini
Fase 1 SELESAI · Fase 2 SELESAI (inferensi Whisper nyata BELUM terverifikasi) · Fase 4 SEBAGIAN · Fase 6 SEBAGIAN · Fase 3, 5, 7, 8 BELUM.

## Selesai
**Fase 1 (fondasi):** FastAPI + SQLite/Alembic (migrasi 0001–0003), proyek, unggah/perpustakaan video, dashboard, diagnostik GPU/NVENC/CUDA, batas sumber daya yang dapat diubah (disimpan di DB),
model manager (satu model besar di VRAM, unload, mode CPU/GPU/auto), log JSON terstruktur, WebSocket event, skrip Windows (install/start/stop/check_gpu/download_models), git.
**Fase 2 (transkripsi):** katalog model Whisper + unduhan atomik dengan persetujuan, ekstraksi audio 16 kHz mono, adaptor faster-whisper (word timestamps, VAD), pemisahan kalimat, antrean persisten (batal, pemulihan saat start),
editor transkrip (edit/pisah/gabung/hapus/cari-ganti/cari), ekspor SRT/VTT/TXT, UI.
**Fase 4 (sebagian, dipindahkan dari ClipForge):** klip manual, deteksi wajah OpenCV, smart crop, subtitle ASS, layout fill/letterbox/split, pratinjau, render + verifikasi FFprobe, UI "Smart Crop & Render".
**Fase 6 (sebagian):** batch render klip terpilih per proyek, antrean job dengan pembatalan, coba ulang job gagal, serta halaman Batch Renderer dan Export Center untuk pratinjau/unduh hasil.

## Hasil tes (dijalankan di sandbox Linux, CPU, tanpa GPU)
- Backend pytest (`backend/tests`): **82 passed**
- Integrasi server sungguhan (`tests/integration`): **1 passed, 1 skipped** (tes bind-loopback di-skip karena sandbox tak punya alamat non-loopback; BELUM terbukti di sini)
- Total `python -m pytest` dari `backend/`: 83 passed, 1 skipped
- Frontend vitest: **2 passed**; `tsc -b` dan `vite build` berhasil
- Batch renderer (verifikasi lokal Windows): **3 passed** untuk antrean batch, validasi/skip job aktif, dan retry job gagal. Frontend build belum dijalankan di lingkungan ini karena `npm`/Node.js tidak tersedia.
- Smoke test browser (Playwright): proyek → unggah → klip → analisis wajah → render → unduh, tanpa error konsol
- Bukti nyata: wajah (gambar astronaut) tetap ada dalam hasil render pada awal DAN akhir saat wajah berpindah kiri→kanan; center crop memotong wajah; subtitle terbukti ter-burn (perbedaan piksel terkonsentrasi di area caption, warna highlight terdeteksi).

## BELUM diverifikasi / keterbatasan jujur
- **Whisper nyata:** sandbox tidak bisa mengunduh model (huggingface.co diblokir). Tes memakai test-double pada antarmuka `Transcriber`; adaptor faster-whisper diuji dengan model tiruan (tanpa inferensi). Akurasi timestamp Whisper TIDAK terukur; yang terukur: durasi audio hasil ekstraksi (±0.15 dtk) dan validasi struktur timestamp.
- **GPU/NVENC/CUDA:** tidak ada GPU di sandbox. Logika pemilihan encoder diuji dengan monkeypatch; encode NVENC, HEVC NVENC, dan registrasi DLL CUDA di Windows (`register_cuda_dlls`) belum pernah dijalankan.
- **Skrip `.bat`:** ditulis dan ditinjau, belum dijalankan di Windows.
- **Ollama/Qwen:** belum diintegrasikan (Fase 3). Hanya status koneksi yang diperiksa.
- Deteksi wajah memakai Haar cascade: hanya andal untuk wajah frontal; wajah menyamping/tertutup bisa terlewat. Model yang lebih kuat belum ada.
- Punctuation: mengandalkan keluaran Whisper (tidak ada model tanda baca terpisah).
- Split screen baru layout dasar dari SATU sumber (kamera atas + layar bawah). Unggah video tambahan/gameplay, garis pembatas, jarak: belum ada.
- Editor klip belum punya timeline/waveform/undo-redo/gabung klip. Watermark/BGM/template (Fase 5) belum dipindahkan dari ClipForge.
- Penghapusan aman (overwrite) belum ada; hapus biasa.
- Kontrol kualitas video panjang (jam-an) belum diuji; transkripsi streaming per segmen dirancang untuk memori konstan tetapi tidak diukur.

## Belum tersedia (UI menampilkan "belum tersedia")
Fase 3 deteksi klip AI (Qwen) · Fase 4 editor timeline · Fase 5 studio subtitle/template/watermark/branding · Sisa Fase 6 (jeda/lanjut antrean dan fitur ekspor lanjutan) · Fase 7 diarization, thumbnail, judul AI, peningkatan audio · Fase 8 finalisasi.

## Langkah berikutnya
1. Verifikasi di Windows RTX 4070 Ti: `install.bat`, `check_gpu.bat`, unduh `large-v3-turbo`, transkripsi video pendek nyata, render dengan NVENC (lihat badge encoder).
2. Fase 3: klien Ollama + Qwen2.5 7B, jendela analisis tumpang tindih, skor 0–100 multi-dimensi, kandidat 10–30 klip.
3. Fase 5: pindahkan watermark/BGM/hook SFX/template dari ClipForge; lanjutkan Fase 6 dengan jeda/lanjut antrean setelah build frontend dapat diverifikasi.
