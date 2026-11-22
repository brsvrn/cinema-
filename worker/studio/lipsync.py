"""Lip sync: Rhubarb Lip Sync (phonetic recognizer, language independent) with
an amplitude/text based fallback.  Output: list of {start, end, value} cues
using Rhubarb's mouth shapes A-H, X."""
from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import numpy as np

from . import config


def cues_for(wav: Path, text: str = "") -> list[dict]:
    rb = config.rhubarb_bin()
    if rb:
        try:
            out = subprocess.run([rb, "--recognizer", "phonetic", "-f", "json", "--extendedShapes", "GHX",
                                  str(wav)], check=True, capture_output=True, text=True, timeout=300)
            data = json.loads(out.stdout)
            cues = data.get("mouthCues", [])
            if cues:
                return cues
        except Exception:  # noqa: BLE001 - fall back to amplitude method
            pass
    return amplitude_cues(wav, text)


def amplitude_cues(wav: Path, text: str = "", fps: int = 30) -> list[dict]:
    with wave.open(str(wav), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    hop = sr // fps
    frames = max(1, len(data) // hop)
    rms = np.array([np.sqrt(np.mean(data[i * hop:(i + 1) * hop] ** 2) + 1e-9) for i in range(frames)])
    peak = max(1e-4, float(np.percentile(rms, 95)))
    vowels = [ch for ch in text.lower() if ch in "aeıioöuü"] or ["a"]
    vmap = {"a": "D", "e": "C", "ı": "C", "i": "C", "o": "E", "ö": "E", "u": "F", "ü": "F"}
    cues = []
    vi = 0
    for i, r in enumerate(rms):
        lvl = r / peak
        if lvl < 0.08:
            v = "X"
        elif lvl < 0.3:
            v = "B"
        elif lvl < 0.55:
            v = "C"
        else:
            v = vmap.get(vowels[vi % len(vowels)], "D")
            vi += 1 if i % 3 == 0 else 0
        t0, t1 = i / fps, (i + 1) / fps
        if cues and cues[-1]["value"] == v:
            cues[-1]["end"] = round(t1, 3)
        else:
            cues.append({"start": round(t0, 3), "end": round(t1, 3), "value": v})
    return cues


def viseme_at(cues: list[dict], t: float) -> str:
    for c in cues:
        if c["start"] <= t < c["end"]:
            return c["value"]
    return "X"
