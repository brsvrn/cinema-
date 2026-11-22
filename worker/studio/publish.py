"""Subtitles (TR/EN SRT), thumbnail, YouTube metadata."""
from __future__ import annotations

from pathlib import Path

import skia

from . import config
from .rig import col, fill, stroke


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(entries: list[tuple[float, float, str]], out: Path) -> Path:
    lines = []
    for i, (s, e, text) in enumerate(entries, 1):
        lines += [str(i), f"{_ts(s)} --> {_ts(e)}", text, ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def thumbnail(frame_png: Path, title: str, series: str, out: Path, w: int = 1280, h: int = 720) -> Path:
    img = skia.Image.open(str(frame_png))
    surf = skia.Surface(w, h)
    c = surf.getCanvas()
    c.drawImageRect(img, skia.Rect.MakeWH(w, h), skia.SamplingOptions(skia.FilterMode.kLinear))
    sh = skia.GradientShader.MakeLinear([(0, h * 0.45), (0, h)], [col("#000000", 0), col("#000000", 0.75)])
    c.drawRect(skia.Rect.MakeWH(w, h), skia.Paint(Shader=sh))
    face = skia.Typeface.MakeFromFile(config.font_path(True))
    f1 = skia.Font(face, 84)
    f2 = skia.Font(face, 40)
    y = h - 70
    c.drawString(title.upper(), 48, y, f1, stroke(col("#000000"), 14))
    c.drawString(title.upper(), 48, y, f1, fill(col("#ffd84a")))
    c.drawString(series, 52, y - 100, f2, stroke(col("#000000"), 8))
    c.drawString(series, 52, y - 100, f2, fill(col("#ffffff")))
    surf.makeImageSnapshot().save(str(out), skia.kPNG)
    return out


def metadata(series: dict, script: dict, characters: dict[str, dict]) -> dict:
    yt = script.get("youtube") or {}
    names = [c["name"] for c in characters.values()]
    title = yt.get("title") or f"{series['title']} | Bölüm {script['episode_number']}: {script['title']}"
    desc = yt.get("description") or (
        f"{script.get('summary', '')}\n\n"
        f"🇬🇧 {script.get('summary_en', '')}\n\n"
        f"{series['title']} ({series.get('title_en', '')}) - Bölüm {script['episode_number']}\n"
        f"Karakterler: {', '.join(names)}\n#animasyon #çizgifilm #shorts")
    tags = yt.get("tags") or ["animasyon", "çizgi film", "animation", "kids", "mini dizi", series["title"],
                              series.get("title_en", ""), *names, script["title"], script.get("title_en", "")]
    return {"title": title[:100], "title_en": f"{series.get('title_en', '')} | Ep {script['episode_number']}: "
                                               f"{script.get('title_en', '')}"[:100],
            "description": desc[:4900], "tags": [t for t in tags if t][:30],
            "summary": script.get("summary", ""), "summary_en": script.get("summary_en", ""),
            "category": "Film & Animation", "made_for_kids": True}
