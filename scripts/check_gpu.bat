@echo off
cd /d "%~dp0.."
echo --- nvidia-smi ---
where nvidia-smi >nul 2>nul && nvidia-smi || echo nvidia-smi tidak ditemukan (driver NVIDIA belum terpasang?)
echo --- encoder NVENC di FFmpeg ---
ffmpeg -hide_banner -encoders 2>nul | findstr /i nvenc || echo Tidak ada encoder NVENC di build FFmpeg ini.
echo.
echo Uji nyata NVENC ada di halaman Pengaturan (tombol "Uji ulang NVENC").
