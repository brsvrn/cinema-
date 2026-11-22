"""Automatic quality control for shot segments and final masters."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import config


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _filter_log(path: Path, vf: str | None = None, af: str | None = None) -> str:
    cmd = [config.ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(path)]
    if vf:
        cmd += ["-vf", vf, "-an"]
    if af:
        cmd += ["-af", af, "-vn"]
    cmd += ["-f", "null", "-"]
    return subprocess.run(cmd, capture_output=True, text=True).stderr


def check_segment(path: Path, expect_w: int, expect_h: int, expect_dur: float) -> dict:
    issues = []
    if not path.exists() or path.stat().st_size < 10_000:
        return {"ok": False, "issues": ["segment missing or empty"]}
    p = probe(path)
    v = next((s for s in p["streams"] if s["codec_type"] == "video"), None)
    if not v or v["width"] != expect_w or v["height"] != expect_h:
        issues.append(f"resolution {v and v['width']}x{v and v['height']} != {expect_w}x{expect_h}")
    dur = float(p["format"]["duration"])
    if abs(dur - expect_dur) > 0.2:
        issues.append(f"duration {dur:.2f}s != {expect_dur:.2f}s")
    log = _filter_log(path, vf="blackdetect=d=0.5:pix_th=0.06")
    if "black_start" in log:
        issues.append("black frames detected")
    return {"ok": not issues, "issues": issues, "duration": dur}


def check_master(path: Path, expect_w: int, expect_h: int, min_dur: float = 28.0, max_dur: float = 32.5) -> dict:
    issues = []
    p = probe(path)
    v = next((s for s in p["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    dur = float(p["format"]["duration"])
    if not v:
        issues.append("no video stream")
    elif (v["width"], v["height"]) != (expect_w, expect_h):
        issues.append(f"resolution {v['width']}x{v['height']}")
    if not a:
        issues.append("no audio stream")
    if not (min_dur <= dur <= max_dur):
        issues.append(f"duration {dur:.2f}s outside {min_dur}-{max_dur}s")
    # frozen video = slideshow/still image (must be real animation)
    flog = _filter_log(path, vf="freezedetect=n=0.0005:d=2")
    freezes = re.findall(r"freeze_duration: ([\d.]+)", flog)
    if freezes and max(float(x) for x in freezes) > 2.5:
        issues.append(f"frozen video for {max(float(x) for x in freezes):.1f}s")
    alog = _filter_log(path, af="volumedetect")
    m = re.search(r"mean_volume: (-?[\d.]+) dB", alog)
    mean_db = float(m.group(1)) if m else -99.0
    if mean_db < -40:
        issues.append(f"audio too quiet ({mean_db} dB)")
    blog = _filter_log(path, vf="blackdetect=d=0.6:pix_th=0.05")
    if "black_start" in blog:
        issues.append("black segment detected")
    return {"ok": not issues, "issues": issues, "duration": dur, "mean_volume_db": mean_db,
            "size": int(p["format"]["size"]), "width": v and v["width"], "height": v and v["height"]}
