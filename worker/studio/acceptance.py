"""Acceptance checks for multi-episode continuity (appearance, voice, location, story)."""
from __future__ import annotations

from .bible import design_hash
from .tts import voice_hash


def continuity_report(store, series_id: str) -> dict:
    series = store.get("series", series_id)
    eps = sorted(store.list("episodes", series_id=series_id), key=lambda e: e["episode_number"])
    chars = {cid: store.get("characters", cid) for cid in series["characters"]}
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    ready = [e for e in eps if e.get("status") == "ready"]
    chk("en az iki bölüm hazır", len(ready) >= 2, f"{len(ready)} hazır")
    for e in ready:
        q = e.get("qc", {}).get("formats", {})
        chk(f"{e['id']} gerçek MP4 + QC", all(v.get("ok") for v in q.values()) and bool(q),
            ", ".join(f"{k}:{v.get('width')}x{v.get('height')} {v.get('duration', 0):.1f}s" for k, v in q.items()))
    # appearance + voice identity
    for cid, ch in chars.items():
        hashes = {e["id"]: e.get("character_hashes", {}).get(cid) for e in ready
                  if cid in e.get("character_hashes", {})}
        if not hashes:
            continue
        vals = {(h or {}).get("design") for h in hashes.values()}
        chk(f"{cid} görünüm sabit", len(vals) == 1 and design_hash(ch["design"]) in vals, str(vals))
        vv = {(h or {}).get("voice") for h in hashes.values()}
        chk(f"{cid} ses profili sabit", len(vv) == 1 and voice_hash(ch["voice"]) in vv, str(vv))
    # location
    locs = {e["script"]["location_id"] for e in ready[:2]}
    chk("mekân aynı (sabit set)", len(locs) == 1, str(locs))
    # story continuity
    if len(ready) >= 2:
        e1, e2 = ready[0], ready[1]
        chk("2. bölüm 1. bölümün devamı", e2["script"].get("continues_from") == e1["episode_number"])
        # ep2 starting blocking == ep1 end blocking
        end1 = e1.get("end_state", {}).get("blocking", {})
        start2 = e2.get("start_state", {}).get("blocking", {})
        ok = bool(start2) and all(abs(end1[c]["x"] - start2.get(c, {}).get("x", -9999)) < 50 for c in end1)
        chk("karakter konumları 1. bölüm sonundan devam ediyor", ok,
            ", ".join(f"{c}: {end1[c]['x']:.0f}->{start2.get(c, {}).get('x', 0):.0f}" for c in end1))
        chk("prop devamlılığı (kabuk 2. bölüme taşındı)", start2.get("chr_ada", {}).get("prop") == "shell")
        props = {c: b.get("prop") for c, b in end1.items() if b.get("prop")}
        chk("1. bölüm sonunda Ada kabuğu taşıyor (2. bölüme aktarılır)", props.get("chr_ada") == "shell", str(props))
        used = {f for b in e2["script"]["beats"] for f in b.get("uses_facts", [])}
        ep1_facts = {f["id"] for f in e1["script"].get("new_facts", [])}
        chk("2. bölüm 1. bölümde öğrenilen bilgileri kullanıyor", bool(used & ep1_facts), str(sorted(used & ep1_facts)))
        resolved = [t for t in series["threads"] if t.get("resolved_in") == 2]
        chk("1. bölümde açılan hikâye 2. bölümde çözüldü", any(t["opened_in"] == 1 for t in resolved),
            str([t["id"] for t in resolved]))
        chk("çözülmemiş hikâye kayıtlı", any(not t.get("resolved_in") for t in series["threads"]))
        chk("bölüm özetleri hafızada", len(series["episodes"]) >= 2)
        e2c = e2.get("continuity", {})
        chk("2. bölüm tutarlılık kontrolünden geçti", e2c.get("ok"), "; ".join(e2c.get("errors", [])))
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
