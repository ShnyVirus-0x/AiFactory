@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0.."
echo ===== Unduh model (SELALU dengan persetujuan Anda) =====
echo Ruang disk tersedia:
powershell -NoProfile -Command "Get-PSDrive -Name ((Get-Location).Drive.Name) | ForEach-Object { '{0:N1} GB' -f ($_.Free/1GB) }"
echo.
echo Perkiraan ukuran unduhan:
echo   [1] Whisper large-v3-turbo (bawaan)   ~1.6 GB  -> models\whisper\large-v3-turbo
echo   [2] Whisper small (CPU/ringan)        ~0.5 GB  -> models\whisper\small
echo   [3] Qwen2.5 7B Instruct (Ollama)      ~4.7 GB  -> folder Ollama (untuk Fase 3)
echo   [0] Batal
echo.
set /p CH=Pilih: 
if "%CH%"=="0" exit /b 0
if not exist .venv\Scripts\python.exe (echo Jalankan install.bat dahulu. & exit /b 1)
if "%CH%"=="1" set "M=large-v3-turbo"
if "%CH%"=="2" set "M=small"
if defined M (
  set /p OK=Unduh !M! dari huggingface.co sekarang? ^(y/N^): 
  if /i not "!OK!"=="y" exit /b 0
  .venv\Scripts\python.exe backend\tools\download_whisper.py !M!
  exit /b %errorlevel%
)
if "%CH%"=="3" (
  where ollama >nul 2>nul || (echo Ollama belum terpasang: https://ollama.com & exit /b 1)
  set /p OK=Jalankan "ollama pull qwen2.5:7b-instruct" ^(~4.7 GB^)? ^(y/N^): 
  if /i "!OK!"=="y" ollama pull qwen2.5:7b-instruct
)
