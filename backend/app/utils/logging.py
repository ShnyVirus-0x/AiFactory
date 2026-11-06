"""Logging terstruktur (JSON lines) ke file berotasi + teks ringkas ke konsol.

Data sensitif tidak dicatat: jangan pernah meneruskan isi transkrip, token, atau path lengkap di luar storage/.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import re
from pathlib import Path

_SECRET = re.compile(r"(?i)(authorization|api[_-]?key|token|password|secret)(['\"]?\s*[:=]\s*['\"]?)[^\s,'\"]+")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = _SECRET.sub(r"\1\2***", record.getMessage())
        data = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname, "logger": record.name, "msg": msg}
        extra = getattr(record, "ctx", None)
        if isinstance(extra, dict):
            data["ctx"] = extra
        if record.exc_info:
            data["exc"] = _SECRET.sub(r"\1\2***", self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False)


_configured = False


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    fileh = logging.handlers.RotatingFileHandler(log_dir / "app.jsonl", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fileh.setFormatter(JsonFormatter())
    root.addHandler(console)
    root.addHandler(fileh)
    _configured = True
