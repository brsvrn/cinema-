"""Story + visual continuity checks run before an episode is produced."""
from __future__ import annotations

from typing import Any

from .bible import design_hash, knowledge, open_threads
from .rig import EXPRESSIONS, POSES
from .tts import voice_hash


def check_script(script: dict, series: dict, characters: dict[str, dict], locations: dict[str, dict]) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    n = script.get("episode_number")
    prev = [e["number"] for e in series.get("episodes", [])]
    if prev and n not in prev and n != max(prev) + 1:
        warnings.append(f"bölüm numarası {n}, son bölüm {max(prev)} - atlama var")
    if script.get("continues_from") and script["continues_from"] not in prev:
        errors.append(f"continues_from={script['continues_from']} henüz üretilmemiş")

    for sc in script.get("scenes") or []:
        lid = sc.get("location_id")
        if lid and lid not in series.get("locations", []):
            errors.append(f"sahne {sc.get('id')}: mekân {lid} dizide kayıtlı değil")
        elif lid and lid not in locations:
            errors.append(f"sahne {sc.get('id')}: mekân kaydı bulunamadı: {lid}")
    if script.get("location_id") not in series.get("locations", []):
        errors.append(f"mekân {script.get('location_id')} dizide kayıtlı değil")
    elif script["location_id"] not in locations:
        errors.append(f"mekân kaydı bulunamadı: {script['location_id']}")

    cast = set(series.get("characters", []))
    for cid in cast:
        ch = characters.get(cid)
        if not ch:
            errors.append(f"karakter kaydı yok: {cid}")
            continue
        if not ch.get("approved"):
            errors.append(f"{cid} onaylanmamış - önce Karakter Stüdyosu'nda onaylayın")
        if ch.get("design_hash") != design_hash(ch["design"]):
            errors.append(f"{cid} tasarımı onaylı sürümden farklı (design_hash uyuşmuyor)")
        if ch.get("voice_hash") != voice_hash(ch["voice"]):
            errors.append(f"{cid} ses profili onaylı sürümden farklı")

    # knowledge: facts known before this episode + learnt during it
    known = {k: set(v) for k, v in knowledge(series, upto_episode=n).items()}
    fact_ids = {f["id"] for f in series.get("facts", [])} | {f["id"] for f in script.get("new_facts", [])}
    new_facts = {f["id"]: f for f in script.get("new_facts", [])}
    beats = script.get("beats", [])
    if not beats:
        errors.append("senaryoda sahne/replik yok")
    line_count = 0
    for i, b in enumerate(beats):
        if b.get("type") not in ("line", "action"):
            errors.append(f"beat {i}: geçersiz tip {b.get('type')}")
            continue
        if b["type"] == "line":
            line_count += 1
            spk = b.get("speaker")
            if spk not in cast:
                errors.append(f"beat {i}: konuşan {spk} dizi kadrosunda değil")
            if not b.get("text"):
                errors.append(f"beat {i}: boş replik")
            if not b.get("text_en"):
                warnings.append(f"beat {i}: İngilizce altyazı metni eksik")
            if b.get("emotion") and b["emotion"] not in EXPRESSIONS:
                warnings.append(f"beat {i}: bilinmeyen duygu {b['emotion']} (neutral kullanılacak)")
            if b.get("action") and b["action"] not in POSES:
                warnings.append(f"beat {i}: bilinmeyen hareket {b['action']}")
            for fid in b.get("uses_facts", []):
                if fid not in fact_ids:
                    errors.append(f"beat {i}: bilinmeyen bilgi {fid}")
                elif fid not in known.get(spk, set()):
                    errors.append(f"beat {i}: {spk} '{fid}' bilgisini henüz bilmiyor (bilgi tutarsızlığı)")
        for fid in b.get("new_facts", []):
            for cid in new_facts.get(fid, {}).get("known_by", []):
                known.setdefault(cid, set()).add(fid)
        for fid, learners in (b.get("teaches") or {}).items():
            for cid in learners:
                known.setdefault(cid, set()).add(fid)
    if line_count > 9 and len(script.get("scenes") or [None]) <= 1 and float(script.get("target_seconds", 30)) <= 90:
        warnings.append(f"{line_count} replik 30 sn için fazla olabilir")

    open_ids = {t["id"] for t in open_threads(series)}
    opened_now = {t["id"] for t in script.get("threads_opened", [])}
    for tid in script.get("threads_resolved", []):
        if tid not in open_ids and tid not in opened_now:
            errors.append(f"çözülen hikâye '{tid}' açık değil")

    # timeline monotonic
    days = [t.get("day", 0) for t in series.get("timeline", []) if t.get("episode", 0) < (n or 0)]
    if days and script.get("timeline", {}).get("day", max(days)) < max(days):
        errors.append("zaman çizelgesi geriye gidiyor")

    # visual continuity with previous episode end-state
    es = (series.get("end_states") or {}).get(str(script.get("continues_from")))
    if script.get("continues_from") and es:
        for cid, b in (script.get("blocking") or {}).items():
            prev_b = (es.get("blocking") or {}).get(cid)
            if prev_b and abs(prev_b.get("x", 0) - b.get("x", prev_b.get("x", 0))) > 50:
                warnings.append(f"{cid} önceki bölüm sonundaki konumundan farklı başlıyor")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def resolve_blocking(script: dict, series: dict, characters: dict[str, dict]) -> tuple[dict, dict]:
    """Starting blocking/env for the episode: inherits the previous episode's end state."""
    es = (series.get("end_states") or {}).get(str(script.get("continues_from"))) or {}
    blocking: dict[str, Any] = {}
    inherit = bool(es)
    for cid in series.get("characters", []):
        base = dict((es.get("blocking") or {}).get(cid, {})) if inherit else {}
        base.update((script.get("blocking") or {}).get(cid, {}))
        if "x" not in base:
            base["x"] = 1000 + 600 * len(blocking)
            base["dir"] = 1 if not blocking else -1
            base["turn"] = 0.45 * base["dir"]
        blocking[cid] = base
    env = {}
    if inherit:
        # carry story state (e.g. lighthouse lamp) - not atmosphere (rain/fireflies/signals follow the new script)
        env.update({k: v for k, v in (es.get("env") or {}).items() if k in ("lamp",)})
    env.update(script.get("env_start", {}))
    return blocking, env
