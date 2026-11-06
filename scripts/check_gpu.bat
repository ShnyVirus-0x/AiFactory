@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ===== Python =====
where python >nul 2>nul && python --version || echo Python tidak ditemukan
if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe --version & echo venv: ada) else echo venv: belum dibuat
echo.
echo ===== FFmpeg =====
where ffmpeg >nul 2>nul && (ffmpeg -version | findstr /b "ffmpeg version") || echo FFmpeg tidak ditemukan
where ffprobe >nul 2>nul && echo FFprobe: ada || echo FFprobe tidak ditemukan
echo.
echo ===== GPU NVIDIA =====
where nvidia-smi >nul 2>nul && (
  nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free,temperature.gpu --format=csv
  echo.
  nvidia-smi | findstr /i "CUDA Version"
) || echo nvidia-smi tidak ditemukan: driver NVIDIA belum terpasang atau tidak ada GPU NVIDIA.
echo.
echo ===== NVENC =====
ffmpeg -hide_banner -encoders 2>nul | findstr /i nvenc || echo Tidak ada encoder NVENC pada build FFmpeg ini.
echo Uji encode NVENC yang sebenarnya: halaman Pengaturan ^> "Uji ulang NVENC".
echo.
echo ===== CUDA untuk faster-whisper (CTranslate2) =====
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -c "import ctranslate2 as c; print('GPU CUDA terlihat oleh CTranslate2:', c.get_cuda_device_count())" 2>nul || echo ctranslate2 belum terpasang
) else echo Jalankan install.bat terlebih dahulu.
echo Dibutuhkan: driver dengan CUDA 12.x + cuDNN 9.
echo.
pause
