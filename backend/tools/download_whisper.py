"""Unduh model Whisper via CLI (dipanggil download_models.bat setelah pengguna setuju). Menampilkan progres."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import whisper_models as wm  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in wm.CATALOG:
        print("Pemakaian: download_whisper.py <" + "|".join(wm.CATALOG) + ">")
        return 2
    name = sys.argv[1]
    spec = wm.CATALOG[name]
    if wm.is_installed(name):
        print(f"Model {name} sudah terpasang di {wm.model_dir(name)}; tidak ditimpa.")
        return 0
    try:
        wm.downloads.start(name)
    except Exception as e:  # noqa: BLE001
        print(f"Gagal memulai: {e}")
        return 1
    print(f"Mengunduh {name} (±{spec.approx_mb} MB) dari {spec.repo} ...")
    while True:
        st = wm.downloads.state(name) or {}
        print(f"\r  {st.get('downloaded_mb', 0):.0f} / ±{spec.approx_mb} MB   ", end="", flush=True)
        if st.get("status") in ("done", "failed"):
            break
        time.sleep(1)
    print()
    if st["status"] == "done":
        print(f"Selesai: {wm.model_dir(name)}")
        return 0
    print(f"Gagal: {st.get('error')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
