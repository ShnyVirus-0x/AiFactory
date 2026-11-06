@echo off
echo === Unduh model (opsional, TIDAK otomatis) ===
echo Fase 1 tidak membutuhkan model AI. Skrip ini baru bermakna mulai Fase 2-3.
echo.
echo Perkiraan ukuran:
echo   Qwen (Ollama) qwen2.5:7b-instruct  ~4.7 GB
echo   faster-whisper large-v3-turbo      ~1.6 GB
echo.
where ollama >nul 2>nul || (echo Ollama belum terpasang: https://ollama.com & exit /b 1)
set /p OK=Unduh qwen2.5:7b-instruct sekarang? (y/N): 
if /i "%OK%"=="y" ollama pull qwen2.5:7b-instruct
echo Model Whisper akan diunduh oleh Fase 2 dengan konfirmasi dan progres tersendiri.
