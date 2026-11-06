@echo off
setlocal
cd /d "%~dp0.."
echo === AI Shorts Factory - instalasi (Fase 1) ===
where python >nul 2>nul || (echo [ERROR] Python 3.11+ tidak ditemukan. Pasang dari python.org lalu ulangi. & exit /b 1)
where node >nul 2>nul || (echo [ERROR] Node.js 20+ tidak ditemukan. Pasang dari nodejs.org lalu ulangi. & exit /b 1)
where ffmpeg >nul 2>nul || echo [PERINGATAN] FFmpeg tidak ada di PATH. Pasang FFmpeg dan tambahkan ke PATH sebelum mengunggah video.
if not exist .venv (python -m venv .venv || exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r backend\requirements.txt || exit /b 1
if not exist .env copy .env.example .env >nul
cd frontend
call npm install || exit /b 1
call npm run build || exit /b 1
cd ..
echo.
echo Selesai. Jalankan scripts\start.bat
echo Catatan: model AI TIDAK diunduh otomatis. Lihat scripts\download_models.bat (Fase 2+).
