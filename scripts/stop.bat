@echo off
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\activate.bat (
  echo [GAGAL] Virtual environment tidak ditemukan. Hentikan server dengan Ctrl+C.
  exit /b 1
)
call .venv\Scripts\activate.bat
pushd backend
for /f %%p in ('python -c "from app.config import get_settings; print(get_settings().port)"') do set "ASF_BIND_PORT=%%p"

rem Cocokkan semua alamat lokal agar server yang bind ke LAN juga dapat dihentikan.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr LISTENING ^| findstr /R /C:":%ASF_BIND_PORT% "') do (
  echo Menghentikan PID %%p
  taskkill /PID %%p /F >nul 2>nul
)
popd
endlocal
