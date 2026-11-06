@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0.."
set "WARN=0"
echo ============================================================
echo  AI Shorts Factory - Instalasi
echo ============================================================

rem --- Python (3.11+ disarankan; 3.14 belum diuji) ---
where python >nul 2>nul || (echo [GAGAL] Python tidak ditemukan. Pasang Python 3.11/3.12 dari python.org lalu ulangi. & exit /b 1)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
python -c "import sys; sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,13) else 1)" || (echo [GAGAL] Python !PYVER! tidak didukung. Gunakan 3.11, 3.12, atau 3.13. & exit /b 1)
echo [OK] Python !PYVER!

rem --- Node.js / npm ---
where node >nul 2>nul || (echo [GAGAL] Node.js 20+ tidak ditemukan. Pasang dari nodejs.org. & exit /b 1)
where npm >nul 2>nul || (echo [GAGAL] npm tidak ditemukan. & exit /b 1)
for /f %%v in ('node --version') do echo [OK] Node.js %%v
for /f %%v in ('npm --version') do echo [OK] npm %%v

rem --- FFmpeg ---
where ffmpeg >nul 2>nul && where ffprobe >nul 2>nul && (echo [OK] FFmpeg + FFprobe ditemukan) || (echo [PERINGATAN] FFmpeg/FFprobe tidak ada di PATH. Wajib untuk unggah video. Pasang dari ffmpeg.org lalu tambahkan ke PATH. & set "WARN=1")

rem --- GPU NVIDIA / CUDA ---
where nvidia-smi >nul 2>nul && (
  echo [OK] GPU NVIDIA:
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
  nvidia-smi | findstr /i "CUDA Version"
  ffmpeg -hide_banner -encoders 2>nul | findstr /i "h264_nvenc" >nul && (echo [OK] Build FFmpeg memiliki encoder h264_nvenc ^(uji encode nyata ada di Pengaturan^)) || (echo [PERINGATAN] FFmpeg ini tidak punya h264_nvenc; render akan memakai CPU. & set "WARN=1")
) || (echo [PERINGATAN] nvidia-smi tidak ditemukan: pasang driver NVIDIA terbaru bila punya GPU. Tanpa GPU, mode CPU dipakai. & set "WARN=1")

rem --- Ollama (opsional, untuk Fase 3) ---
where ollama >nul 2>nul && (echo [OK] Ollama ditemukan) || (echo [INFO] Ollama belum terpasang ^(dibutuhkan mulai Fase 3^): https://ollama.com)

rem --- Virtualenv + dependensi Python ---
if not exist .venv (python -m venv .venv || exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r backend\requirements.txt || (echo [GAGAL] Instal dependensi Python. & exit /b 1)
echo [OK] Dependensi Python terpasang
where nvidia-smi >nul 2>nul && (echo [INFO] Memasang pustaka CUDA 12 + cuDNN 9 untuk faster-whisper ^(besar, ~1 GB^)... & pip install -r backend\requirements-gpu.txt || (echo [PERINGATAN] Gagal memasang pustaka CUDA; transkripsi akan memakai CPU. & set "WARN=1"))

rem --- .env + direktori penyimpanan ---
if not exist .env (copy .env.example .env >nul & echo [OK] .env dibuat dari .env.example) else (echo [OK] .env sudah ada ^(tidak ditimpa^))
for %%d in (storage\uploads storage\outputs storage\thumbnails storage\transcripts storage\cache storage\logs models\whisper) do if not exist "%%d" mkdir "%%d"
echo [OK] Direktori penyimpanan siap

rem --- Inisialisasi SQLite (migrasi Alembic) ---
cd backend
python -c "from app.database import run_migrations; run_migrations()" || (echo [GAGAL] Inisialisasi database. & exit /b 1)
cd ..
echo [OK] Database SQLite diinisialisasi

rem --- Frontend ---
cd frontend
call npm install || (echo [GAGAL] npm install. & exit /b 1)
call npm run build || (echo [GAGAL] build frontend. & exit /b 1)
cd ..

echo.
echo ============================================================
if "!WARN!"=="1" (echo  Instalasi selesai DENGAN PERINGATAN ^(lihat di atas^).) else (echo  Instalasi selesai.)
echo  Jalankan: scripts\start.bat
echo  Model AI TIDAK diunduh otomatis. Unduh lewat halaman Transkripsi atau scripts\download_models.bat
echo ============================================================
endlocal
