"""Cost estimation + budget enforcement (USD)."""
from __future__ import annotations

import time

# Unit prices (USD). Free tiers are tracked separately; the estimator always
# prefers the free path when one exists.
PRICES = {
    "github_actions_min": 0.008,     # linux runner after free minutes (2000/mo private, unlimited public)
    "claude_script": 0.03,           # one script + review (~6k tokens)
    "elevenlabs_char": 0.00018,      # creator tier approx
    "runpod_gpu_sec": 0.00044,       # ~RTX 4090 serverless / sec
    "storage_gb_month": 0.015,       # R2
}
SECONDS_PER_EPISODE_CPU = {"economic": 6 * 60, "advanced": 14 * 60, "cinematic": 4 * 60}


def estimate(mode: str, duration_s: float = 30.0, chars_of_dialogue: int = 400, use_llm: bool = False,
             use_elevenlabs: bool = False, free_actions_left_min: float = 2000.0) -> dict:
    items = []
    cpu_min = SECONDS_PER_EPISODE_CPU.get(mode, 360) * (duration_s / 30.0) / 60.0
    billable = max(0.0, cpu_min - free_actions_left_min)
    items.append({"item": "GitHub Actions render", "qty": round(cpu_min, 1), "unit": "min",
                  "usd": round(billable * PRICES["github_actions_min"], 4), "free": billable == 0})
    if use_llm:
        items.append({"item": "Claude senaryo + tutarlılık", "qty": 1, "unit": "call", "usd": PRICES["claude_script"],
                      "free": False})
    else:
        items.append({"item": "Şablon senaryo (ücretsiz)", "qty": 1, "unit": "call", "usd": 0.0, "free": True})
    if use_elevenlabs:
        items.append({"item": "ElevenLabs ses", "qty": chars_of_dialogue, "unit": "char",
                      "usd": round(chars_of_dialogue * PRICES["elevenlabs_char"], 4), "free": False})
    else:
        items.append({"item": "Piper TTS (ücretsiz)", "qty": chars_of_dialogue, "unit": "char", "usd": 0.0, "free": True})
    if mode == "cinematic":
        gpu_s = duration_s * 40  # ~40 GPU-sec per output second (Wan 2.x i2v, 480p->upscale)
        items.append({"item": "RunPod GPU (Wan/ComfyUI)", "qty": gpu_s, "unit": "gpu-sec",
                      "usd": round(gpu_s * PRICES["runpod_gpu_sec"], 4), "free": False})
    items.append({"item": "Depolama (~60 MB)", "qty": 0.06, "unit": "GB", "usd": round(0.06 * PRICES["storage_gb_month"], 4),
                  "free": True})
    total = round(sum(i["usd"] for i in items if not i["free"]), 4)
    return {"mode": mode, "items": items, "total_usd": total, "requires_paid_approval": any(not i["free"] and i["usd"] > 0 for i in items)}


def check_budget(store, estimate_usd: float, daily_limit: float, monthly_limit: float) -> dict:
    now = time.time()
    ledger = store.list("cost_ledger")
    day = sum(e.get("usd", 0) for e in ledger if now - e.get("ts", 0) < 86400)
    month = sum(e.get("usd", 0) for e in ledger if now - e.get("ts", 0) < 30 * 86400)
    ok = day + estimate_usd <= daily_limit and month + estimate_usd <= monthly_limit
    return {"ok": ok, "spent_today": round(day, 4), "spent_month": round(month, 4),
            "daily_limit": daily_limit, "monthly_limit": monthly_limit}


def record(store, job_id: str, usd: float, item: str):
    store.put("cost_ledger", f"{job_id}_{item}_{int(time.time())}", {"job_id": job_id, "usd": usd, "item": item,
                                                                    "ts": time.time()})
