"""Mode 3 - cinematic GPU refinement (RunPod serverless + ComfyUI / Wan video).

Flow (per shot): economic render -> keyframes -> ComfyUI workflow on a RunPod
serverless endpoint (Wan 2.x image-to-video, IP-Adapter with the character's
model sheet, optional character LoRA, ControlNet pose from the rig) -> refined
clip replaces the segment.  The endpoint scales to zero when idle, so GPUs only
run during production.

Paid: requires RUNPOD_API_KEY + RUNPOD_ENDPOINT_ID AND owner approval
(settings/budget.allow_paid + STUDIO_ALLOW_PAID=1) AND budget headroom.
"""
from __future__ import annotations

import base64
import time
from pathlib import Path

import requests

from .. import config
from ..cost import check_budget, estimate


class NotAllowed(RuntimeError):
    pass


def ensure_allowed(store, duration: float = 30.0) -> None:
    b = store.get("settings", "budget") or {}
    if not (config.RUNPOD_API_KEY and config.RUNPOD_ENDPOINT_ID):
        raise NotAllowed("Sinematik mod için RUNPOD_API_KEY ve RUNPOD_ENDPOINT_ID gerekli (henüz bağlı değil).")
    if not (b.get("allow_paid") and config.ALLOW_PAID):
        raise NotAllowed("Sinematik mod ücretlidir; Maliyet Kontrolü'nden ücretli işlemlere izin verilmedi.")
    est = estimate("cinematic", duration)["total_usd"]
    bud = check_budget(store, est, b.get("daily_usd", 1), b.get("monthly_usd", 10))
    if not bud["ok"]:
        raise NotAllowed(f"Bütçe limiti: {bud}")


def refine_clip(keyframe_png: Path, prompt: str, seconds: float, out_mp4: Path, lora: str | None = None,
                ref_png: Path | None = None, timeout_s: int = 900) -> Path:
    """Run one i2v refinement on the RunPod ComfyUI worker (runpod-workers/worker-comfyui input format)."""
    def b64(p: Path) -> str:
        return base64.b64encode(p.read_bytes()).decode()
    images = [{"name": "keyframe.png", "image": b64(keyframe_png)}]
    if ref_png:
        images.append({"name": "reference.png", "image": b64(ref_png)})
    payload = {"input": {"workflow": _wan_workflow(prompt, int(seconds * 16), lora, bool(ref_png)), "images": images}}
    h = {"Authorization": f"Bearer {config.RUNPOD_API_KEY}"}
    base = f"https://api.runpod.ai/v2/{config.RUNPOD_ENDPOINT_ID}"
    job = requests.post(f"{base}/run", json=payload, headers=h, timeout=60).json()
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        st = requests.get(f"{base}/status/{job['id']}", headers=h, timeout=30).json()
        if st.get("status") == "COMPLETED":
            data = st["output"]["images"][0]["data"]
            out_mp4.write_bytes(base64.b64decode(data))
            return out_mp4
        if st.get("status") in ("FAILED", "CANCELLED", "TIMED_OUT"):
            raise RuntimeError(f"RunPod job {st.get('status')}: {st.get('error')}")
        time.sleep(5)
    requests.post(f"{base}/cancel/{job['id']}", headers=h, timeout=30)
    raise TimeoutError("RunPod job timed out")


def _wan_workflow(prompt: str, frames: int, lora: str | None, with_ref: bool) -> dict:
    """Minimal ComfyUI API graph for Wan 2.x image-to-video (node ids are strings)."""
    g = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "keyframe.png"}},
        "2": {"class_type": "WanImageToVideo", "inputs": {"positive": ["5", 0], "negative": ["6", 0], "vae": ["4", 2],
                                                          "start_image": ["1", 0], "width": 832, "height": 480,
                                                          "length": frames, "batch_size": 1}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "wan2.1_i2v_480p_14B_fp8.safetensors"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry, deformed, extra limbs, flicker", "clip": ["4", 1]}},
        "7": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["2", 0], "negative": ["2", 1],
                                                   "latent_image": ["2", 2], "seed": 7, "steps": 20, "cfg": 5.0,
                                                   "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 0.55}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveAnimatedWEBP", "inputs": {"images": ["8", 0], "filename_prefix": "shot", "fps": 16,
                                                           "lossless": False, "quality": 90, "method": "default"}},
    }
    if lora:
        g["10"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["4", 0], "lora_name": lora, "strength_model": 0.8}}
        g["7"]["inputs"]["model"] = ["10", 0]
    return g
