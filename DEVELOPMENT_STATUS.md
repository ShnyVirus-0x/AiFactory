# DEVELOPMENT STATUS

## Fase saat ini: 1 — Fondasi (SELESAI), Fase 2–8 BELUM dikerjakan

## Selesai
- Backend FastAPI: proyek, video (upload/list/filter/rename/delete/thumbnail/stream), dashboard, health, GPU, resources, WebSocket
- DB SQLite WAL + Alembic migrasi 0001 (users, projects, videos, transcripts, transcript_segments, clips, clip_edits, templates, render_jobs, settings, activity_log)
- Frontend React 19 + Vite + Tailwind v4: Dashboard, Proyek, Perpustakaan Video, Pengaturan; halaman modul lain = "belum tersedia"
- Skrip Windows: install/start/stop/check_gpu/download_models

## Hasil tes (dijalankan di sandbox Linux)
- Backend pytest: **33 passed**
- Frontend: `tsc -b` dan `vite build` berhasil
- Smoke test Playwright (buat proyek → unggah video → dashboard → pengaturan → halaman fase): tanpa error konsol

## BELUM diverifikasi
- GPU NVIDIA/NVENC/CUDA nyata (sandbox tanpa GPU; kode deteksi hanya diuji dengan parser dan jalur "tidak tersedia")
- Skrip .bat di Windows sungguhan (ditulis, belum dijalankan)
- Ollama/Qwen, faster-whisper (belum diintegrasikan)

## Belum tersedia (endpoint mengembalikan 501 `not_available`)
Fase 2 transkripsi · Fase 3 deteksi klip AI · Fase 4 editor/face tracking/split screen · Fase 5 subtitle/template · Fase 6 batch renderer/export · Fase 7 thumbnail · Fase 8 optimasi/tes akhir

## Masalah diketahui
- Frontend belum punya tes otomatis (hanya type-check + smoke test manual)
- Penghapusan aman berlapis (overwrite) belum ada; hapus biasa saja

## Langkah berikutnya
Fase 2: integrasi faster-whisper large-v3-turbo (unduh model dengan konfirmasi ukuran & progres), transkrip + segmen kata ke DB.
