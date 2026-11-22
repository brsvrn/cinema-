"""Procedural (royalty-free, generated) music + sound effects and final mix.

Everything is synthesized with numpy so there are no licensing issues and no
paid services.  Music is mood/key driven and seeded by the series id so a
series keeps a recognisable theme across episodes (audio continuity).
"""
from __future__ import annotations

import math
import random
import wave
from pathlib import Path

import numpy as np

from .config import SAMPLE_RATE as SR

NOTE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
MOODS = {
    # root, scale intervals, chord degrees, tempo, brightness
    "warm":       ("D", [0, 2, 4, 5, 7, 9, 11], [0, 5, 3, 4], 84, 0.8),
    "mystery":    ("A", [0, 2, 3, 5, 7, 8, 10], [0, 5, 3, 6], 72, 0.5),
    "adventure":  ("G", [0, 2, 4, 5, 7, 9, 11], [0, 4, 5, 3], 104, 0.9),
    "tense":      ("E", [0, 1, 3, 5, 7, 8, 10], [0, 1, 5, 4], 92, 0.45),
    "wonder":     ("F", [0, 2, 4, 6, 7, 9, 11], [0, 4, 1, 5], 76, 0.75),
}


def midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _env(n: int, a: float, r: float) -> np.ndarray:
    e = np.ones(n, dtype=np.float32)
    na, nr = int(a * SR), int(r * SR)
    if na > 0:
        e[:na] = np.linspace(0, 1, na)
    if nr > 0:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _lowpass(x: np.ndarray, k: float) -> np.ndarray:
    # cheap one-pole low-pass via cumulative filter
    y = np.empty_like(x)
    acc = 0.0
    a = k
    for i in range(0, len(x), 1):
        acc += a * (x[i] - acc)
        y[i] = acc
    return y


def _lp_fast(x: np.ndarray, k: float) -> np.ndarray:
    """Vectorised approximate low-pass using FFT-domain roll-off."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    cutoff = 200 + k * 6000
    X *= 1 / np.sqrt(1 + (f / cutoff) ** 4)
    return np.fft.irfft(X, n=len(x)).astype(np.float32)


def pluck(freq: float, dur: float, seed: int = 0) -> np.ndarray:
    """Karplus-Strong plucked string."""
    n = int(dur * SR)
    period = max(2, int(SR / freq))
    rng = np.random.default_rng(seed)
    buf = rng.uniform(-1, 1, period).astype(np.float32)
    out = np.empty(n, dtype=np.float32)
    idx = 0
    for i in range(n):
        out[i] = buf[idx]
        nxt = (idx + 1) % period
        buf[idx] = 0.497 * (buf[idx] + buf[nxt])
        idx = nxt
    return out * _env(n, 0.002, min(0.3, dur * 0.5))


def bell(freq: float, dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    for k, (ratio, amp, dec) in enumerate(((1, 1, 2.2), (2.76, 0.5, 3.5), (5.4, 0.25, 5), (8.9, 0.12, 7))):
        out += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-dec * t)
    return out * 0.3


def pad(freqs: list[float], dur: float, bright: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    for f in freqs:
        for det in (-0.12, 0.0, 0.11):
            ff = f * 2 ** (det / 12)
            # soft saw from a few harmonics
            for h in range(1, 6):
                out += (np.sin(2 * np.pi * ff * h * t + h) / h) * (bright ** (h - 1)) * 0.06
    lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.25 * t)
    return out * lfo * _env(n, min(0.8, dur * 0.3), min(0.8, dur * 0.3))


def music(duration: float, mood: str = "warm", seed: str = "series", intensity: float = 0.6) -> np.ndarray:
    root, scale, prog, bpm, bright = MOODS.get(mood, MOODS["warm"])
    rng = random.Random(f"{seed}:{mood}")
    beat = 60.0 / bpm
    bar = beat * 4
    n = int(duration * SR) + SR
    out = np.zeros(n, dtype=np.float32)
    base = 48 + NOTE[root]
    motif = [rng.choice([0, 2, 4, 7, 4, 2]) for _ in range(8)]  # series motif
    t = 0.0
    bar_i = 0
    while t < duration:
        deg = prog[bar_i % len(prog)]
        chord = [base + scale[(deg + k) % 7] + 12 * ((deg + k) // 7) for k in (0, 2, 4)]
        seg = pad([midi_hz(m) for m in chord], bar + 0.6, bright * 0.6)
        i0 = int(t * SR)
        out[i0:i0 + len(seg)] += seg[: max(0, min(len(seg), n - i0))] * 0.9
        # bass
        b = pluck(midi_hz(chord[0] - 12), beat * 2, seed=bar_i) * 0.5
        out[i0:i0 + len(b)] += b[: max(0, min(len(b), n - i0))]
        b2 = pluck(midi_hz(chord[0] - 12), beat * 2, seed=bar_i + 99) * 0.4
        j = int((t + beat * 2) * SR)
        out[j:j + len(b2)] += b2[: max(0, min(len(b2), n - j))]
        # arpeggio / motif
        steps = 8
        for s in range(steps):
            if rng.random() > 0.35 + intensity * 0.5:
                continue
            m = base + 24 + scale[(deg + motif[(bar_i * steps + s) % len(motif)]) % 7]
            note = pluck(midi_hz(m), beat * 0.9, seed=bar_i * 31 + s) * (0.22 + 0.1 * intensity)
            k = int((t + s * beat / 2) * SR)
            out[k:k + len(note)] += note[: max(0, min(len(note), n - k))]
        t += bar
        bar_i += 1
    out = out[: int(duration * SR)]
    fade = int(min(1.5, duration * 0.1) * SR)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return _norm(out, 0.5)


# ------------------------------------------------------------------- sfx

def sfx(name: str, dur: float | None = None, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if name == "waves":
        d = dur or 10.0
        n = int(d * SR)
        noise = rng.standard_normal(n).astype(np.float32)
        brown = np.cumsum(noise)
        brown -= np.convolve(brown, np.ones(4000) / 4000, mode="same")
        brown /= (np.abs(brown).max() + 1e-6)
        t = np.arange(n) / SR
        swell = 0.55 + 0.45 * np.sin(2 * np.pi * t / 6.5) ** 2
        return _norm(brown * swell, 0.35)
    if name == "wind":
        d = dur or 10.0
        n = int(d * SR)
        x = _lp_fast(rng.standard_normal(n).astype(np.float32), 0.08)
        t = np.arange(n) / SR
        return _norm(x * (0.6 + 0.4 * np.sin(2 * np.pi * t / 4.3)), 0.25)
    if name == "rain":
        d = dur or 10.0
        n = int(d * SR)
        x = rng.standard_normal(n).astype(np.float32)
        x = x - _lp_fast(x, 0.3)
        return _norm(x, 0.18)
    if name == "seagull":
        d = 1.2
        n = int(d * SR)
        t = np.arange(n) / SR
        out = np.zeros(n, dtype=np.float32)
        for k, st in enumerate((0.0, 0.35, 0.62)):
            seg = (t >= st) & (t < st + 0.28)
            tt = t[seg] - st
            f = 1400 + 900 * np.sin(np.pi * tt / 0.28) - 600 * tt
            ph = 2 * np.pi * np.cumsum(f) / SR
            out[seg] += np.sin(ph + 2 * np.sin(ph * 0.5)) * np.sin(np.pi * tt / 0.28)
        return _norm(out, 0.25)
    if name == "chime":
        out = np.zeros(int(2.5 * SR), dtype=np.float32)
        for k, m in enumerate((84, 88, 91, 96)):
            b = bell(midi_hz(m), 2.0)
            i = int(k * 0.09 * SR)
            out[i:i + len(b)] += b[: len(out) - i]
        return _norm(out, 0.5)
    if name == "magic":
        n = int(2.0 * SR)
        t = np.arange(n) / SR
        f = 600 + 1800 * t / 2.0
        out = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-1.2 * t) * 0.3
        out += sfx("chime")[:n] if len(sfx("chime")) >= n else 0
        return _norm(out.astype(np.float32), 0.5)
    if name == "foghorn":
        n = int(2.6 * SR)
        t = np.arange(n) / SR
        out = sum(np.sin(2 * np.pi * 98 * h * t) / h for h in range(1, 8)).astype(np.float32)
        return _norm(out * _env(n, 0.25, 0.8), 0.45)
    if name == "click":
        n = int(0.12 * SR)
        x = rng.standard_normal(n).astype(np.float32) * np.exp(-np.arange(n) / (SR * 0.01))
        return _norm(x, 0.5)
    if name == "buzz":  # electric flicker
        n = int(1.2 * SR)
        t = np.arange(n) / SR
        gate = (rng.random(int(n / 800) + 1) > 0.4).repeat(800)[:n]
        x = (np.sign(np.sin(2 * np.pi * 100 * t)) * 0.3 + rng.standard_normal(n) * 0.1) * gate
        return _norm(x.astype(np.float32), 0.3)
    if name == "footsteps":
        d = dur or 2.0
        n = int(d * SR)
        out = np.zeros(n, dtype=np.float32)
        step = int(0.42 * SR)
        for i in range(0, n - 4000, step):
            s = _lp_fast(rng.standard_normal(4000).astype(np.float32), 0.05) * np.exp(-np.arange(4000) / 700)
            out[i:i + 4000] += s
        return _norm(out, 0.35)
    if name == "whoosh":
        n = int(0.8 * SR)
        x = _lp_fast(rng.standard_normal(n).astype(np.float32), 0.2)
        return _norm(x * np.sin(np.linspace(0, np.pi, n)), 0.35)
    if name == "gasp":
        n = int(0.4 * SR)
        x = _lp_fast(rng.standard_normal(n).astype(np.float32), 0.35)
        return _norm(x * np.sin(np.linspace(0, np.pi, n)) ** 2, 0.2)
    raise ValueError(f"unknown sfx {name}")


SFX_NAMES = ["waves", "wind", "rain", "seagull", "chime", "magic", "foghorn", "click", "buzz", "footsteps",
             "whoosh", "gasp"]


def _norm(x: np.ndarray, peak: float) -> np.ndarray:
    m = float(np.abs(x).max()) if len(x) else 0.0
    return (x / m * peak).astype(np.float32) if m > 1e-9 else x.astype(np.float32)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR, f"{path} must be {SR} Hz"
        d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() == 2:
            d = d.reshape(-1, 2).mean(axis=1)
    return d


def write_wav(path: Path, stereo: np.ndarray):
    s = np.clip(stereo, -1, 1)
    pcm = (s * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def mix(duration: float, dialogue: list[tuple[float, Path, float]], sfx_events: list[tuple[float, str, float, float]],
        ambience: list[tuple[str, float]], music_track: np.ndarray | None, out: Path) -> dict:
    """dialogue: (start, wav, pan -1..1); sfx_events: (start, name, gain, pan)."""
    n = int(duration * SR)
    L = np.zeros(n, dtype=np.float32)
    R = np.zeros(n, dtype=np.float32)
    voice_env = np.zeros(n, dtype=np.float32)

    def add(sig, start, gain, pan):
        i = int(start * SR)
        if i >= n:
            return
        sig = sig[: n - i] * gain
        lg = math.cos((pan + 1) * math.pi / 4)
        rg = math.sin((pan + 1) * math.pi / 4)
        L[i:i + len(sig)] += sig * lg
        R[i:i + len(sig)] += sig * rg
        return i, len(sig)

    for start, wav, pan in dialogue:
        sig = read_wav(wav)
        r = add(sig, start, 0.95, pan * 0.35)
        if r:
            voice_env[r[0]:r[0] + r[1]] = 1.0
    for name, gain in ambience:
        sig = sfx(name, duration, seed=hash(name) % 1000)
        add(sig, 0.0, gain, 0.0)
    for start, name, gain, pan in sfx_events:
        add(sfx(name, seed=int(start * 100)), start, gain, pan)
    if music_track is not None:
        # sidechain ducking under dialogue
        k = int(0.25 * SR)
        smooth = np.convolve(voice_env, np.ones(k) / k, mode="same")
        duck = 1.0 - 0.55 * np.clip(smooth, 0, 1)
        m = music_track[:n]
        if len(m) < n:
            m = np.pad(m, (0, n - len(m)))
        L += m * duck * 0.55
        R += m * duck * 0.55
    stereo = np.stack([L, R], axis=1)
    peak = float(np.abs(stereo).max())
    if peak > 0.98:
        stereo *= 0.98 / peak
    write_wav(out, stereo)
    rms = float(np.sqrt(np.mean(stereo ** 2)))
    return {"peak": peak, "rms": rms}
