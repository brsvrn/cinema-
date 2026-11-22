"""Text-to-speech with fixed per-character voice profiles.

Default engine: Piper (free, offline, CPU).  A character's voice profile
(model + pitch + speed + noise) is stored with the Character record and never
changes between episodes, which gives a stable "voice identity".

ElevenLabs is supported but only used when ELEVENLABS_API_KEY is set, the
character has an `elevenlabs_voice_id`, and paid usage is allowed
(STUDIO_ALLOW_PAID=1).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import wave
from pathlib import Path
from typing import Any

import requests

from . import config

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_PATHS = {
    "tr_TR-dfki-medium": "tr/tr_TR/dfki/medium/tr_TR-dfki-medium",
    "en_US-lessac-medium": "en/en_US/lessac/medium/en_US-lessac-medium",
    "en_US-ryan-medium": "en/en_US/ryan/medium/en_US-ryan-medium",
    "en_US-amy-medium": "en/en_US/amy/medium/en_US-amy-medium",
}
_voices: dict[str, Any] = {}


def ensure_piper_model(name: str) -> Path:
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    onnx = config.MODELS_DIR / f"{name}.onnx"
    js = config.MODELS_DIR / f"{name}.onnx.json"
    if onnx.exists() and js.exists():
        return onnx
    rel = PIPER_PATHS.get(name)
    if not rel:
        raise ValueError(f"unknown piper voice {name}")
    for suffix, dst in ((".onnx", onnx), (".onnx.json", js)):
        r = requests.get(f"{PIPER_BASE}/{rel}{suffix}", timeout=300)
        r.raise_for_status()
        dst.write_bytes(r.content)
    return onnx


def _piper_voice(name: str):
    if name not in _voices:
        from piper import PiperVoice
        _voices[name] = PiperVoice.load(str(ensure_piper_model(name)))
    return _voices[name]


def voice_hash(profile: dict[str, Any]) -> str:
    keys = ("engine", "model", "pitch_semitones", "speed", "noise_scale", "elevenlabs_voice_id")
    return hashlib.sha256(json.dumps({k: profile.get(k) for k in keys}, sort_keys=True).encode()).hexdigest()[:16]


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def synthesize(text: str, profile: dict[str, Any], out_wav: Path, cache_dir: Path | None = None) -> float:
    """Render one line to a mono 48 kHz wav.  Returns duration in seconds."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((voice_hash(profile) + "|" + text).encode()).hexdigest()[:20]
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / f"{key}.wav"
        if cached.exists():
            out_wav.write_bytes(cached.read_bytes())
            return wav_duration(out_wav)
    raw = out_wav.with_suffix(".raw.wav")
    use_eleven = (profile.get("elevenlabs_voice_id") and config.ELEVENLABS_API_KEY and config.ALLOW_PAID)
    if use_eleven:
        _eleven(text, profile, raw)
        pitch = 0.0
    else:
        _piper(text, profile, raw)
        pitch = float(profile.get("pitch_semitones", 0.0))
    _post(raw, out_wav, pitch)
    raw.unlink(missing_ok=True)
    if cache_dir:
        (cache_dir / f"{key}.wav").write_bytes(out_wav.read_bytes())
    return wav_duration(out_wav)


def _piper(text: str, profile: dict[str, Any], out: Path):
    from piper import SynthesisConfig
    voice = _piper_voice(profile.get("model", "tr_TR-dfki-medium"))
    speed = float(profile.get("speed", 1.0))
    cfg = SynthesisConfig(length_scale=1.0 / speed, noise_scale=float(profile.get("noise_scale", 0.667)),
                          noise_w_scale=0.8)
    with wave.open(str(out), "wb") as wf:
        voice.synthesize_wav(text, wf, syn_config=cfg)


def _eleven(text: str, profile: dict[str, Any], out: Path):
    vid = profile["elevenlabs_voice_id"]
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{vid}?output_format=pcm_22050",
        headers={"xi-api-key": config.ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={"text": text, "model_id": profile.get("elevenlabs_model", "eleven_multilingual_v2")},
        timeout=120)
    r.raise_for_status()
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(r.content)


def _post(src: Path, dst: Path, semitones: float):
    """Pitch shift (formant-coupled, cartoon style) keeping duration; normalize; 48 kHz mono."""
    with wave.open(str(src), "rb") as w:
        sr = w.getframerate()
    ratio = 2 ** (semitones / 12.0)
    filters = []
    if abs(semitones) > 0.01:
        filters.append(f"asetrate={int(sr * ratio)}")
        filters.append(f"aresample={sr}")
        # atempo accepts 0.5..2.0
        tempo = 1.0 / ratio
        filters.append(f"atempo={tempo:.5f}")
    filters += ["highpass=f=70", "acompressor=threshold=-18dB:ratio=3:attack=5:release=80",
                "loudnorm=I=-16:TP=-1.5:LRA=7", f"aresample={config.SAMPLE_RATE}"]
    subprocess.run([config.ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(src), "-af", ",".join(filters),
                    "-ac", "1", "-ar", str(config.SAMPLE_RATE), str(dst)], check=True)
