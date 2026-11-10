# Status pengembangan

Dokumen ini mencatat fitur yang sudah tersedia, hasil pengujian yang pernah dijalankan, dan pekerjaan yang masih perlu dilakukan. Status pengujian di bawah bukan jaminan bahwa fitur tersebut sudah diuji pada setiap komputer.

## Fitur yang sudah tersedia

- **Proyek dan perpustakaan video:** FastAPI, SQLite/Alembic (migrasi 0001–0003), unggah dan validasi video, metadata, thumbnail, pencarian, serta operasi proyek dan video.
- **Diagnostik dan pengelolaan sumber daya:** informasi CPU, RAM, disk, GPU/NVENC/CUDA, pengaturan batas sumber daya, dan pengelolaan model yang dimuat.
- **Transkripsi:** katalog dan unduhan model Whisper dengan persetujuan, ekstraksi audio 16 kHz mono, adaptor faster-whisper dengan word timestamps dan VAD, antrean persisten, editor transkrip, serta ekspor SRT/VTT/TXT.
- **Smart Crop & Render:** pembuatan klip manual, deteksi wajah OpenCV, crop dan layout, subtitle ASS, pratinjau, render, serta pemeriksaan hasil dengan FFprobe.
- **Batch Renderer dan Export Center (dasar):** antrean beberapa klip per proyek, pembatalan job, retry untuk job gagal, pratinjau, dan unduhan hasil.

## Hasil pengujian yang tercatat

Pengujian berikut dijalankan di lingkungan sandbox Linux, menggunakan CPU dan tanpa GPU:

- Backend: 82 tes lulus.
- Integrasi server: 1 tes lulus dan 1 tes dilewati. Tes bind-loopback dilewati karena sandbox tidak memiliki alamat non-loopback.
- Seluruh tes Python dari `backend/`: 83 lulus dan 1 dilewati.
- Frontend: 2 tes Vitest lulus; `tsc -b` dan `vite build` berhasil.
- Smoke test Playwright: alur proyek, unggah, pembuatan klip, analisis wajah, render, dan unduh selesai tanpa error konsol.
- Pada sampel pengujian, wajah tetap terlihat di awal dan akhir hasil render saat berpindah dari kiri ke kanan. Center crop memotong wajah; perbedaan piksel juga mengonfirmasi subtitle ter-render di area caption.

Pengujian batch renderer di Windows mencatat 3 tes lulus untuk antrean, validasi atau skip job aktif, dan retry job gagal. Build frontend belum dijalankan di lingkungan Windows tersebut karena Node.js/npm tidak tersedia.

## Yang belum diverifikasi atau belum tersedia

- **Inferensi Whisper sungguhan:** model tidak bisa diunduh di sandbox karena akses ke huggingface.co diblokir. Adaptor diuji dengan model tiruan, bukan inferensi sungguhan. Akurasi timestamp belum diukur; yang diuji hanya durasi audio hasil ekstraksi (selisih sekitar 0,15 detik) dan struktur timestamp.
- **GPU, NVENC, dan CUDA di Windows:** tidak ada GPU di sandbox. Pemilihan encoder diuji dengan monkeypatch, tetapi encode NVENC/HEVC NVENC dan registrasi DLL CUDA Windows belum diuji.
- **Skrip Windows:** file `.bat` sudah ditulis dan ditinjau, tetapi belum dijalankan dalam pengujian yang tercatat.
- **Deteksi klip otomatis:** integrasi Ollama/Qwen belum ada; saat ini yang diperiksa hanya status koneksinya.
- **Deteksi wajah:** memakai Haar cascade dan lebih cocok untuk wajah frontal. Wajah menyamping atau tertutup bisa terlewat.
- **Editor dan layout lanjutan:** editor belum memiliki timeline, waveform, undo/redo, atau penggabungan klip. Split screen masih berupa layout dasar dari satu sumber; unggah sumber gameplay terpisah dan pengaturan pembatas belum tersedia.
- **Fitur produksi lain:** template, watermark, BGM, thumbnail, diarization, judul AI, dan peningkatan audio belum tersedia. Antrean juga belum mendukung jeda/lanjut.
- **Video berdurasi panjang:** kualitas dan penggunaan memori untuk video berjam-jam belum diukur. Transkripsi dirancang untuk memproses audio per segmen.
- **Penghapusan file:** penghapusan aman dengan overwrite belum diterapkan.

## Berikutnya

1. Jalankan instalasi dan skrip pemeriksaan GPU di Windows, lalu uji transkripsi model Whisper dan render NVENC dengan video pendek.
2. Jika diteruskan, integrasikan analisis klip menggunakan Ollama/Qwen dan uji hasilnya pada video nyata.
3. Lanjutkan editor timeline dan fitur produksi seperti template, watermark, dan BGM; lengkapi kontrol jeda/lanjut antrean.
