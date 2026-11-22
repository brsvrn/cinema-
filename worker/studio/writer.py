"""Episode script writer.

* With ANTHROPIC_API_KEY: Claude writes the script from the Series Bible memory
  brief, in the strict JSON schema below, then a second call reviews continuity.
* Without a key: a deterministic free template writer produces a valid (simple)
  episode so the whole pipeline still works at zero cost.
"""
from __future__ import annotations

import json
import re
from typing import Any

import requests

from . import config
from .rig import EXPRESSIONS, POSES

SCHEMA_DOC = """
Return ONLY a JSON object:
{
 "title": str (Turkish), "title_en": str,
 "lighting": "day"|"sunset"|"dusk"|"night",
 "music_mood": "warm"|"mystery"|"adventure"|"tense"|"wonder",
 "timeline": {"day": int, "time": str},
 "env_start": {"lamp": 0|1, "boat_signal": 0|"blink", "fireflies": 0..1, "rain": 0..1},
 "beats": [  // 6-8 lines + 2-4 actions, total spoken text <= 70 words for a 30 s episode
   {"type":"action","duration":1.2-2.6,"description":str,
    "camera": optional "wide"|"insert:<object>"|"mcu:<character_id>",
    "moves": optional {character_id: spot_name_or_x}, "poses": optional {character_id: pose},
    "expressions": optional {character_id: emotion}, "props": optional {character_id: prop|null},
    "events": optional {"lamp": 0|1|"flicker", "boat_signal": 0|"blink"},
    "sfx": optional [[name, offset_s, gain, pan]]},
   {"type":"line","speaker":character_id,"text":Turkish,"text_en":English,
    "emotion":emotion,"action":optional pose,"look_at":optional character_id|object,
    "reaction":optional emotion for listeners,"uses_facts":[fact ids the speaker relies on],
    "new_facts":[ids introduced here]}
 ],
 "new_facts":[{"id":"f_...","text":str,"known_by":[character ids]}],
 "events":[str], "threads_opened":[{"id":"t_...","text":str}], "threads_resolved":[thread ids],
 "summary": Turkish, "summary_en": English,
 "youtube": {"title": str, "description": str, "tags": [str]}
}
"""


def _vocab(location: dict) -> str:
    return (f"poses: {', '.join(POSES)}\nemotions: {', '.join(EXPRESSIONS)}\n"
            f"objects: lamp, tower, door, boat, sea, bench, ground\nspots: {', '.join(location.get('spots', {}))}\n"
            "sfx: waves, wind, rain, seagull, chime, magic, foghorn, click, buzz, footsteps, whoosh, gasp")


def claude(messages: list[dict], system: str, max_tokens: int = 4000) -> str:
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                               "content-type": "application/json"},
                      json={"model": config.ANTHROPIC_MODEL, "max_tokens": max_tokens, "system": system,
                            "messages": messages}, timeout=180)
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("model did not return JSON")
    return json.loads(m.group(0))


def write_episode(memory: dict, topic: str, episode_number: int, location: dict) -> dict:
    if config.ANTHROPIC_API_KEY:
        return _write_llm(memory, topic, episode_number, location)
    return _write_template(memory, topic, episode_number, location)


def _write_llm(memory: dict, topic: str, n: int, location: dict) -> dict:
    system = ("You are the head writer of a children's/family animated mini-series. You must keep strict "
              "continuity with the Series Bible: never contradict past events, characters may only use facts "
              "they know (see 'knows'), keep personalities and relationships, respect universe rules, and "
              "advance or resolve open threads. Episodes are 30 seconds long.")
    user = (f"SERIES BIBLE MEMORY:\n{json.dumps(memory, ensure_ascii=False)}\n\n"
            f"EPISODE NUMBER: {n}\nUSER TOPIC: {topic}\nLOCATION: {location['id']}\n\n"
            f"ALLOWED VOCABULARY:\n{_vocab(location)}\n\n{SCHEMA_DOC}")
    script = _json(claude([{"role": "user", "content": user}], system))
    script.update({"episode_number": n, "location_id": location["id"], "series_id": memory["series"]["id"]})
    if n > 1:
        script.setdefault("continues_from", n - 1)
    return script


def review_llm(script: dict, memory: dict) -> dict:
    """Optional LLM continuity review -> {"ok": bool, "issues": [..]}."""
    if not config.ANTHROPIC_API_KEY:
        return {"ok": True, "issues": [], "skipped": True}
    txt = claude([{"role": "user", "content":
                   f"Bible:\n{json.dumps(memory, ensure_ascii=False)}\n\nNew episode:\n"
                   f"{json.dumps(script, ensure_ascii=False)}\n\nList continuity errors (contradictions, characters "
                   f"knowing things they shouldn't, personality breaks). Return JSON {{\"ok\":bool,\"issues\":[str]}}."}],
                 "You are a meticulous script supervisor.", 1500)
    return _json(txt)


def _write_template(memory: dict, topic: str, n: int, location: dict) -> dict:
    chars = memory["characters"]
    a = chars[0]["id"]
    b = chars[1]["id"] if len(chars) > 1 else chars[0]["id"]
    an, bn = chars[0]["name"], (chars[1]["name"] if len(chars) > 1 else chars[0]["name"])
    prev = memory["previous_episodes"][-1] if memory["previous_episodes"] else None
    thread = memory["open_threads"][0] if memory["open_threads"] else None
    topic = topic.strip().rstrip(".")
    beats = [
        {"type": "action", "duration": 2.0, "description": f"{location['name']} - açılış.",
         "sfx": [["seagull", 0.3, 0.4, -0.4]]},
        {"type": "line", "speaker": a, "emotion": "curious", "action": "talk_open",
         "text": f"{bn.split()[0]}, bugün aklımda tek bir şey var: {topic}.",
         "text_en": f"{bn.split()[0]}, today only one thing is on my mind: {topic}.", "reaction": "thinking"},
        {"type": "line", "speaker": b, "emotion": "thinking", "action": "think",
         "text": ("Dün yaşadıklarımızdan sonra buna şaşırmadım." if prev else "Güzel bir soru. Birlikte bakalım."),
         "text_en": ("After what happened yesterday, I'm not surprised." if prev else "Good question. Let's look together.")},
        {"type": "action", "duration": 2.0, "camera": "wide", "description": "İkisi etrafı inceler.",
         "sfx": [["whoosh", 0.0, 0.3, 0.0]]},
        {"type": "line", "speaker": a, "emotion": "surprised", "action": "point", "look_at": "sea",
         "text": "Bak! Orada bir şey var!", "text_en": "Look! There's something over there!", "reaction": "surprised"},
        {"type": "line", "speaker": b, "emotion": "determined", "action": "hands_hips",
         "text": (f"Belki de bu, {thread['text'].rstrip('?').lower()} sorusunun cevabıdır." if thread
                  else "O zaman yarın daha erken başlarız."),
         "text_en": ("Maybe this is the answer to our open question." if thread else "Then tomorrow we start earlier.")},
        {"type": "line", "speaker": a, "emotion": "happy", "action": "excited",
         "text": "Yeni bir macera başlıyor!", "text_en": "A new adventure begins!", "reaction": "happy"},
    ]
    return {
        "series_id": memory["series"]["id"], "episode_number": n, "title": topic[:60].capitalize(),
        "title_en": topic[:60].capitalize(), "location_id": location["id"], "lighting": "day",
        "music_mood": "adventure", "timeline": {"day": (memory["timeline"][-1]["day"] + 1) if memory["timeline"] else 1,
                                                 "time": "gündüz"},
        "continues_from": n - 1 if prev else None, "blocking": {}, "env_start": {"lamp": 0},
        "ambience": [["waves", 0.45], ["wind", 0.2]], "beats": beats, "new_facts": [], "events": [topic],
        "threads_opened": [], "threads_resolved": [],
        "summary": f"{an} ve {bn} {topic} konusunu araştırır.", "summary_en": f"{an} and {bn} investigate: {topic}.",
        "writer": "template",
    }
