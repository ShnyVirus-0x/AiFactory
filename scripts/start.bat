@echo off
cd /d "%~dp0.."
if not exist .venv (echo Jalankan scripts\install.bat dahulu. & exit /b 1)
call .venv\Scripts\activate.bat
echo Membuka http://127.0.0.1:8000 (hanya lokal). Tekan Ctrl+C untuk berhenti.
start "" http://127.0.0.1:8000
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
