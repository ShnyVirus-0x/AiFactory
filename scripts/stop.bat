@echo off
rem Menghentikan hanya proses yang mendengarkan port 8000 milik aplikasi ini.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "127.0.0.1:8000" ^| findstr LISTENING') do (
  echo Menghentikan PID %%p
  taskkill /PID %%p /F
)
