@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
if not exist .venv\Scripts\activate.bat (echo [GAGAL] Belum terpasang. Jalankan scripts\install.bat dahulu. & exit /b 1)
if not exist frontend\dist\index.html (echo [GAGAL] Frontend belum di-build. Jalankan scripts\install.bat. & exit /b 1)
call .venv\Scripts\activate.bat

where ffmpeg >nul 2>nul || (echo [GAGAL] FFmpeg tidak ada di PATH. & exit /b 1)
where ffprobe >nul 2>nul || (echo [GAGAL] FFprobe tidak ada di PATH. & exit /b 1)
echo [OK] FFmpeg/FFprobe

where nvidia-smi >nul 2>nul && echo [OK] GPU NVIDIA terdeteksi || echo [INFO] GPU NVIDIA tidak terdeteksi: mode CPU.

rem --- Ollama: dijalankan hanya jika terpasang dan belum berjalan ---
where ollama >nul 2>nul && (
  powershell -NoProfile -Command "try{(Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:11434/api/tags)|Out-Null;exit 0}catch{exit 1}" && (echo [OK] Ollama sudah berjalan) || (echo [INFO] Menjalankan Ollama... & start "Ollama" /min ollama serve)
) || echo [INFO] Ollama tidak terpasang ^(fitur AI Fase 3 belum tersedia^).

rem --- Cek port ---
netstat -ano | findstr "127.0.0.1:8000" | findstr LISTENING >nul && (echo [GAGAL] Port 8000 sudah dipakai. Jalankan scripts\stop.bat atau ubah ASF_PORT di .env. & exit /b 1)

echo.
echo Server: http://127.0.0.1:8000  ^(hanya dapat diakses dari komputer ini^)
echo Log JSON: storage\logs\app.jsonl   ^|   Tekan Ctrl+C untuk berhenti.
start "" http://127.0.0.1:8000
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
endlocal
