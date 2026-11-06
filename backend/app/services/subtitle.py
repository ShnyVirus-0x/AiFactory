"""Generator subtitle ASS (karaoke per kata) dari timestamp kata transkrip. Dipindahkan dari ClipForge dan diadaptasi."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..schemas.render import CaptionSpec

PLAY_W, PLAY_H = 1080, 1920


@dataclass(frozen=True)
class Preset:
    label: str
    base: str
    highlight: str
    outline: str
    outline_w: int
    shadow: int
    bold: bool
    uppercase: bool
    pop: bool


PRESETS: dict[str, Preset] = {
    "pop_yellow": Preset("Viral Pop", "#FFFFFF", "#FFE600", "#000000", 7, 2, True, True, True),
    "neon_green": Preset("Neon Punch", "#FFFFFF", "#39FF14", "#000000", 7, 2, True, True, True),
    "cyber_violet": Preset("Cyber Violet", "#FFFFFF", "#D946EF", "#1B0B2E", 7, 3, True, True, True),
    "fire_red": Preset("Fire Red", "#FFFFFF", "#FF3B30", "#000000", 7, 2, True, True, True),
    "electric_cyan": Preset("Electric Cyan", "#FFFFFF", "#00E5FF", "#001F2E", 7, 2, True, True, True),
    "golden": Preset("Golden Aura", "#FFF4D6", "#FFC107", "#2B1B00", 6, 3, True, False, True),
    "clean": Preset("Clean Minimal", "#FFFFFF", "#FFFFFF", "#000000", 3, 1, False, False, False),
    "bold_outline": Preset("Bold Outline", "#FFFFFF", "#FF8A00", "#000000", 9, 0, True, True, False),
}

_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*|♪[^♪]*♪|<[^>]*>")
_DISALLOWED = re.compile(r"[^\w\s.,%&$?!'’:\-+/@#]", re.UNICODE)
_SENTENCE_END = re.compile(r"[.!?…]$")


def sanitize(text: str) -> str:
    """Hapus tag non-ucapan dan karakter yang dapat menyisipkan override ASS ({ } \\)."""
    text = _BRACKETS.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ").replace("\\", " ")
    return re.sub(r"\s+", " ", _DISALLOWED.sub("", text)).strip()


def hex_to_ass(color: str, alpha: int = 0) -> str:
    c = color.lstrip("#")
    return f"&H{alpha:02X}{c[4:6]}{c[2:4]}{c[0:2]}".upper()


def fmt_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def words_in_range(segments: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    """segments: [{start,end,text,words:[{start,end,word}]}] dalam waktu video. Hasil: kata dalam waktu RELATIF klip."""
    out: list[dict[str, Any]] = []
    for seg in segments:
        if seg["end"] < start or seg["start"] > end:
            continue
        words = seg.get("words") or [{"start": seg["start"], "end": seg["end"], "word": w} for w in seg["text"].split()]
        for w in words:
            if w["end"] <= start or w["start"] >= end:
                continue
            clean = sanitize(w["word"])
            if clean:
                out.append({"start": max(0.0, w["start"] - start), "end": min(end - start, w["end"] - start), "word": clean})
    return out


def _group(words: list[dict], per_line: int, max_chars: int = 22) -> list[list[dict]]:
    groups: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        too_long = cur and (len(" ".join(x["word"] for x in cur)) + 1 + len(w["word"]) > max_chars)
        gap = cur and (w["start"] - cur[-1]["end"] > 0.8)
        if cur and (len(cur) >= per_line or too_long or gap):
            groups.append(cur)
            cur = []
        cur.append(w)
        if _SENTENCE_END.search(w["word"]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _wrap_title(text: str, width: int = 22) -> str:
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\\N".join(lines[:3])


def build_ass(segments: list[dict[str, Any]] | None, clip_start: float, clip_end: float, cap: CaptionSpec, title: str | None, title_seconds: float = 3.0) -> str | None:
    """Isi file .ass, atau None bila tidak ada caption maupun judul."""
    preset = PRESETS.get(cap.preset, PRESETS["pop_yellow"])
    duration = clip_end - clip_start
    events: list[str] = []
    if cap.enabled and segments:
        groups = _group(words_in_range(segments, clip_start, clip_end), cap.words_per_line)
        for gi, grp in enumerate(groups):
            ev_start = grp[0]["start"]
            nxt = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else duration
            ev_end = min(max(grp[-1]["end"], ev_start + 0.25), nxt if nxt - grp[-1]["end"] < 0.3 else grp[-1]["end"] + 0.15)
            ev_end = max(ev_end, ev_start + 0.2)
            parts = []
            for k, w in enumerate(grp):
                w_end = grp[k + 1]["start"] if k + 1 < len(grp) else max(w["end"], w["start"] + 0.1)
                cs = max(1, int(round((w_end - w["start"]) * 100)))
                parts.append(f"{{\\kf{cs}}}{w['word'].upper() if preset.uppercase else w['word']}")
            pop = "{\\fscx88\\fscy88\\t(0,110,\\fscx100\\fscy100)}" if preset.pop else ""
            events.append(f"Dialogue: 1,{fmt_time(ev_start)},{fmt_time(ev_end)},Caption,,0,0,0,,{pop}{' '.join(parts)}")
    title_text = sanitize(title or "")
    if title_text:
        t_end = min(duration, title_seconds) if title_seconds else duration
        events.append(f"Dialogue: 2,{fmt_time(0)},{fmt_time(t_end)},Title,,0,0,0,,{{\\fad(180,180)}}{_wrap_title(title_text)}")
    if not events:
        return None
    margin_v = int(PLAY_H * (1 - cap.y))
    bold = -1 if preset.bold else 0
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_W}
PlayResY: {PLAY_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{cap.font},{cap.size},{hex_to_ass(preset.highlight)},{hex_to_ass(preset.base)},{hex_to_ass(preset.outline)},{hex_to_ass('#000000', 0x80)},{bold},0,0,0,100,100,0,0,1,{preset.outline_w},{preset.shadow},2,60,60,{margin_v},1
Style: Title,{cap.font},{max(40, int(cap.size * 0.8))},{hex_to_ass('#FFFFFF')},{hex_to_ass('#FFFFFF')},{hex_to_ass('#000000')},{hex_to_ass('#000000', 0x60)},-1,0,0,0,100,100,0,0,3,14,0,8,70,70,{int(PLAY_H * 0.08)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n"
