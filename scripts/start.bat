@echo off
setlocal EnableDelayedExpansion
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
) || echo [INFO] Ollama tidak terpasang ^(analisis saran klip lokal tidak tersedia sampai Ollama dijalankan^).

pushd backend
for /f %%p in ('python -c "from app.config import get_settings; print(get_settings().port)"') do set "ASF_BIND_PORT=%%p"
for /f %%h in ('python -c "from app.config import get_settings; print(get_settings().host)"') do set "ASF_BIND_HOST=%%h"

rem Cek port tanpa mengasumsikan alamat bind tertentu (loopback atau LAN).
netstat -ano | findstr LISTENING | findstr /R /C:":!ASF_BIND_PORT! " >nul && (echo [GAGAL] Port !ASF_BIND_PORT! sudah dipakai. Jalankan scripts\stop.bat atau ubah ASF_PORT di .env. & popd & exit /b 1)

echo.
echo Server lokal: http://127.0.0.1:!ASF_BIND_PORT!
if not "!ASF_BIND_HOST!"=="127.0.0.1" echo Bind host: !ASF_BIND_HOST! ^(perangkat lain perlu IP LAN komputer ini dan origin yang diizinkan di .env^)
echo Log JSON: storage\logs\app.jsonl   ^|   Tekan Ctrl+C untuk berhenti.
start "" "http://127.0.0.1:!ASF_BIND_PORT!"
python -m app.main
popd
endlocal
