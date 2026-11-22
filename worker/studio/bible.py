"""Series Bible: persistent story memory + character identity registry.

The bible is the single source of truth checked before every new episode:
character histories, relationships, events, episode summaries, timeline,
locations, universe rules, open/resolved threads, who-knows-what, future plans,
and the end-state (blocking/props/lighting) of the last episode for visual continuity.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from typing import Any

from .rig import EXPRESSIONS, POSES, VISEMES


def design_hash(design: dict) -> str:
    return hashlib.sha256(json.dumps(design, sort_keys=True).encode()).hexdigest()[:16]


def new_character(spec: dict, series_id: str) -> dict:
    """Create a persistent character record (Character ID) from a spec."""
    from .tts import voice_hash
    ch = copy.deepcopy(spec)
    ch.setdefault("id", "chr_" + hashlib.sha1(spec["name"].encode()).hexdigest()[:8])
    ch["series_id"] = series_id
    ch["version"] = ch.get("version", 1)
    ch["approved"] = ch.get("approved", True)
    ch["design_hash"] = design_hash(ch["design"])
    ch["voice_hash"] = voice_hash(ch["voice"])
    ch["library"] = {
        "views": ["front", "three_quarter", "side", "back"],
        "skeleton": ["hip", "spine", "neck", "head", "shoulder_l", "elbow_l", "hand_l", "shoulder_r", "elbow_r",
                     "hand_r", "hip_l", "knee_l", "ankle_l", "hip_r", "knee_r", "ankle_r"],
        "expressions": list(EXPRESSIONS.keys()),
        "mouth_shapes": VISEMES,
        "motions": list(POSES.keys()) + ["walk"],
    }
    ch.setdefault("lora", None)          # set when a character LoRA is trained (pro/GPU modes)
    ch.setdefault("reference_images", {})
    ch["created_at"] = ch.get("created_at", time.time())
    return ch


def new_series(spec: dict) -> dict:
    s = copy.deepcopy(spec)
    s.setdefault("episodes", [])          # [{number, id, title, summary, summary_en}]
    s.setdefault("events", [])            # [{episode, text}]
    s.setdefault("timeline", [])          # [{episode, day, time}]
    s["facts"] = [dict(f, episode=0) for f in s.pop("initial_facts", [])] + s.get("facts", [])
    s.setdefault("threads", [])           # [{id, text, opened_in, resolved_in}]
    s.setdefault("relationships", [])
    s.setdefault("universe_rules", [])
    s.setdefault("future_plans", [])
    s.setdefault("end_state", None)       # blocking/props/env at end of last episode
    s.setdefault("character_history", {})  # cid -> [episode notes]
    return s


def knowledge(series: dict, upto_episode: int | None = None) -> dict[str, set[str]]:
    """Who knows which fact ids (optionally only facts learnt before an episode)."""
    out: dict[str, set[str]] = {}
    for f in series.get("facts", []):
        if upto_episode is not None and f.get("episode", 0) >= upto_episode:
            continue
        for cid in f.get("known_by", []):
            out.setdefault(cid, set()).add(f["id"])
    return out


def open_threads(series: dict) -> list[dict]:
    return [t for t in series.get("threads", []) if not t.get("resolved_in")]


def memory_brief(series: dict, characters: dict[str, dict], locations: dict[str, dict]) -> dict:
    """Compact memory handed to the script writer (LLM or template)."""
    k = knowledge(series)
    return {
        "series": {kk: series.get(kk) for kk in ("id", "title", "logline", "universe_rules", "future_plans",
                                                 "relationships")},
        "previous_episodes": [{"number": e["number"], "title": e["title"], "summary": e["summary"]}
                              for e in series.get("episodes", [])],
        "timeline": series.get("timeline", []),
        "open_threads": open_threads(series),
        "facts": [{"id": f["id"], "text": f["text"], "known_by": f.get("known_by", [])} for f in series.get("facts", [])],
        "characters": [{"id": c["id"], "name": c["name"], "personality": c.get("personality"),
                        "backstory": c.get("backstory"), "knows": sorted(k.get(c["id"], set())),
                        "history": series.get("character_history", {}).get(c["id"], [])}
                       for c in characters.values()],
        "locations": [{"id": l["id"], "name": l["name"], "description": l.get("description")}
                      for l in locations.values()],
        "end_state": series.get("end_state"),
    }


def apply_episode(series: dict, script: dict, end_state: dict) -> dict:
    """Write an approved/rendered episode back into the bible."""
    n = script["episode_number"]
    s = copy.deepcopy(series)
    s["episodes"] = [e for e in s["episodes"] if e["number"] != n] + [{
        "number": n, "id": script.get("id"), "title": script["title"], "title_en": script.get("title_en"),
        "summary": script.get("summary", ""), "summary_en": script.get("summary_en", "")}]
    s["episodes"].sort(key=lambda e: e["number"])
    s["events"] = [e for e in s["events"] if e["episode"] != n] + [{"episode": n, "text": t} for t in script.get("events", [])]
    s["timeline"] = [e for e in s["timeline"] if e["episode"] != n] + [{"episode": n, **script.get("timeline", {})}]
    ids = {f["id"] for f in s["facts"]}
    for f in script.get("new_facts", []):
        if f["id"] not in ids:
            s["facts"].append(dict(f, episode=n))
    # facts taught during the episode
    for b in script.get("beats", []):
        for fid, learners in (b.get("teaches") or {}).items():
            for f in s["facts"]:
                if f["id"] == fid:
                    f["known_by"] = sorted(set(f.get("known_by", [])) | set(learners))
    known = {t["id"] for t in s["threads"]}
    for t in script.get("threads_opened", []):
        if t["id"] not in known:
            s["threads"].append({**t, "opened_in": n, "resolved_in": None})
    for tid in script.get("threads_resolved", []):
        for t in s["threads"]:
            if t["id"] == tid:
                t["resolved_in"] = n
    for cid in {b.get("speaker") for b in script.get("beats", []) if b.get("speaker")}:
        s["character_history"].setdefault(cid, [])
        s["character_history"][cid] = [h for h in s["character_history"][cid] if h["episode"] != n]
        s["character_history"][cid].append({"episode": n, "lines": sum(1 for b in script["beats"] if b.get("speaker") == cid)})
    s["end_state"] = {"episode": n, **end_state}
    s.setdefault("end_states", {})[str(n)] = {"episode": n, **end_state}
    return s
