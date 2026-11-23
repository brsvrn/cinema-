"""15-stage, checkpointed, resumable episode production pipeline.

Every stage writes its artifacts to the job work dir and records completion in
state.json (mirrored to the store + storage).  If the worker dies (runner
timeout, network loss, phone screen off - the phone is never involved), the
next worker run downloads the checkpoint and continues from the first
unfinished stage / unfinished shot.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any, Callable

import skia

from . import config
from .bible import apply_episode, memory_brief
from .continuity import check_script, resolve_blocking
from .location import GROUND_Y, make_location, object_camera, world_objects
from .lipsync import cues_for
from .performance import Performance
from .publish import metadata, thumbnail, write_srt
from .qc import check_master, check_segment
from .render import FrameRenderer, RenderContext, encode_shot, still
from .rig import CharacterRig
from .storyboard import Shot, TimedBeat, build_shots, episode_duration, time_beats, time_scenes
from .camera import CamKey
from .tts import synthesize
from . import audio as audio_mod
from . import packaging
from . import writer

STAGES = [
    ("memory", "Dizi hafızasını oku"),
    ("script", "Senaryoyu üret"),
    ("continuity", "Hikâye tutarlılığını kontrol et"),
    ("storyboard", "Storyboard oluştur"),
    ("voices", "Diyalogları seslendir"),
    ("animate", "Karakterleri hareketlendir"),
    ("lipsync", "Dudak senkronizasyonu"),
    ("staging", "Mekân ve kamera açıları"),
    ("audio", "Müzik ve ses efektleri"),
    ("render", "Sahneleri render et"),
    ("assemble", "Videoyu birleştir"),
    ("qc", "Kalite kontrolü"),
    ("repair", "Başarısız sahneleri yeniden üret"),
    ("upload", "Depolama alanına yükle"),
    ("publish", "Uygulamada yayınla"),
]
FORMATS = {"youtube": (1920, 1080, False), "shorts": (1080, 1920, True)}
TARGET_SECONDS = 30.0


class PipelineError(RuntimeError):
    pass


SHORTS_MAX = 58.0


def normalize_script(script: dict) -> dict:
    """Flatten `scenes` into one beat list (each beat tagged with `_scene`).

    Single-scene (legacy 30 s) scripts become one scene built from the top-level fields.
    """
    s = json.loads(json.dumps(script))
    if s.get("scenes"):
        beats, metas = [], []
        for k, sc in enumerate(s["scenes"]):
            for b in sc.get("beats", []):
                beats.append({**b, "_scene": k})
            metas.append({kk: vv for kk, vv in sc.items() if kk != "beats"})
        s["beats"] = beats
        s["scenes"] = metas
        first = metas[0]
        for key in ("location_id", "lighting", "blocking", "env_start", "ambience", "music_mood"):
            if key in first and key not in s:
                s[key] = first[key]
    else:
        s["beats"] = [{**b, "_scene": 0} for b in s.get("beats", [])]
        s["scenes"] = [{"id": "s1", **{k: s[k] for k in ("location_id", "lighting", "blocking", "env_start",
                                                          "ambience", "music_mood") if k in s}}]
    return s


def is_long(script: dict) -> bool:
    return len(script.get("scenes", [])) > 1 or float(script.get("target_seconds", 30)) > 90


class Pipeline:
    def __init__(self, store, episode_id: str, work_root: Path | None = None,
                 formats: tuple[str, ...] = ("youtube", "shorts"), progress: Callable[[dict], None] | None = None,
                 force_continuity: bool = False, quality: str = "economic", stop_after: str | None = None):
        self.store = store
        self.episode_id = episode_id
        self.work = Path(work_root or config.WORK_DIR) / episode_id
        self.work.mkdir(parents=True, exist_ok=True)
        self.formats = formats
        self.progress_cb = progress
        self.force = force_continuity
        self.quality = quality
        self.stop_after = stop_after
        self.state = self._load_state()
        self._invalidate_if_script_changed()

    # ------------------------------------------------------------ state
    def _invalidate_if_script_changed(self):
        """If the owner edited the script in the app, redo everything from the script stage."""
        import hashlib
        ep = self.store.get("episodes", self.episode_id) or {}
        sc = ep.get("script")
        h = hashlib.sha256(json.dumps(sc, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16] if sc else None
        old = self.state.get("script_hash")
        if old and h and old != h:
            self.log("senaryo değişmiş - aşamalar yeniden üretilecek")
            self.state["stages"] = {k: v for k, v in self.state["stages"].items() if k == "memory"}
            self.state["shots_done"] = {}
        if h:
            self.state["script_hash"] = h

    @property
    def key_prefix(self) -> str:
        return f"episodes/{self.episode_id}"

    def _load_state(self) -> dict:
        p = self.work / "state.json"
        if p.exists():
            return json.loads(p.read_text())
        if self.store.download(f"{self.key_prefix}/work/state.json", p):
            st = json.loads(p.read_text())
            for rel in st.get("artifacts", []):
                lp = self.work / rel
                if not lp.exists():
                    self.store.download(f"{self.key_prefix}/work/{rel}", lp)
            return st
        return {"stages": {}, "shots_done": {}, "artifacts": [], "attempts": {}, "log": []}

    def _save_state(self):
        p = self.work / "state.json"
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2))
        tmp.replace(p)
        if self.store.kind != "local":
            self.store.upload(p, f"{self.key_prefix}/work/state.json")

    def _artifact(self, path: Path):
        rel = str(path.relative_to(self.work))
        if rel not in self.state["artifacts"]:
            self.state["artifacts"].append(rel)
        if self.store.kind != "local":
            self.store.upload(path, f"{self.key_prefix}/work/{rel}")

    def _json_w(self, name: str, data: Any) -> Path:
        p = self.work / name
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        self._artifact(p)
        return p

    def _json_r(self, name: str) -> Any:
        return json.loads((self.work / name).read_text())

    def log(self, msg: str):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        self.state["log"] = (self.state.get("log", []) + [line])[-200:]

    def _progress(self, stage: str, frac: float = 0.0, note: str = ""):
        idx = [s for s, _ in STAGES].index(stage)
        pct = round(100 * (idx + frac) / len(STAGES), 1)
        ep = self.store.get("episodes", self.episode_id) or {}
        ep["pipeline"] = {"stage": stage, "stage_label": dict(STAGES)[stage], "percent": pct, "note": note,
                          "stages": self.state["stages"], "updated": time.time()}
        if ep.get("status") not in ("ready",):
            ep["status"] = "rendering"
        self.store.put("episodes", self.episode_id, ep)
        if self.progress_cb:
            self.progress_cb(ep["pipeline"])

    # ------------------------------------------------------------ run
    def run(self) -> dict:
        for stage, label in STAGES:
            if self.state["stages"].get(stage) == "done":
                continue
            self.log(f"▶ {stage}: {label}")
            self.state["stages"][stage] = "running"
            self._save_state()
            self._progress(stage, 0.0, label)
            try:
                getattr(self, f"stage_{stage}")()
            except Exception as e:  # noqa: BLE001
                self.state["stages"][stage] = "failed"
                self.log(f"✖ {stage} failed: {e}")
                self._save_state()
                ep = self.store.get("episodes", self.episode_id) or {}
                ep["status"] = "failed" if not isinstance(e, PipelineError) else "needs_attention"
                ep["error"] = f"{stage}: {e}"
                ep["traceback"] = traceback.format_exc()[-3000:]
                self.store.put("episodes", self.episode_id, ep)
                raise
            self.state["stages"][stage] = "done"
            self._save_state()
            if self.stop_after == stage:
                ep = self.store.get("episodes", self.episode_id) or {}
                ep["status"] = "script_ready"
                ep["pipeline"] = {**(ep.get("pipeline") or {}), "stage_label": "Senaryo + storyboard hazır",
                                  "stages": self.state["stages"]}
                self.store.put("episodes", self.episode_id, ep)
                self.log(f"⏸ {stage} sonrası durduruldu (önizleme)")
                break
        return self.store.get("episodes", self.episode_id)

    # ------------------------------------------------------------ loaders
    def _ep(self) -> dict:
        ep = self.store.get("episodes", self.episode_id)
        if not ep:
            raise PipelineError(f"episode {self.episode_id} not found")
        return ep

    def _world(self):
        ep = self._ep()
        series = self.store.get("series", ep["series_id"])
        chars = {cid: self.store.get("characters", cid) for cid in series["characters"]}
        locs = {lid: self.store.get("locations", lid) for lid in series["locations"]}
        return ep, series, chars, locs

    # ------------------------------------------------------------ stages
    def stage_memory(self):
        ep, series, chars, locs = self._world()
        self._json_w("memory.json", memory_brief(series, chars, locs))

    def stage_script(self):
        ep, series, chars, locs = self._world()
        script = ep.get("script")
        if not script:
            loc = locs[ep.get("location_id") or series["locations"][0]]
            script = writer.write_episode(self._json_r("memory.json"), ep.get("topic", ""), ep["episode_number"], loc)
            ep["script"] = script
            ep["title"] = script.get("title", ep.get("title"))
            self.store.put("episodes", self.episode_id, ep)
            import hashlib
            self.state["script_hash"] = hashlib.sha256(json.dumps(script, sort_keys=True, ensure_ascii=False)
                                                       .encode()).hexdigest()[:16]
        script = normalize_script(script)
        script["id"] = self.episode_id
        self._json_w("script.json", script)

    def stage_continuity(self):
        ep, series, chars, locs = self._world()
        script = self._json_r("script.json")
        rep = check_script(script, series, chars, locs)
        llm = writer.review_llm(script, self._json_r("memory.json")) if config.ANTHROPIC_API_KEY else {"skipped": True}
        rep["llm_review"] = llm
        self._json_w("continuity.json", rep)
        ep["continuity"] = rep
        self.store.put("episodes", self.episode_id, ep)
        for w in rep["warnings"]:
            self.log(f"  ⚠ {w}")
        if not rep["ok"] and not self.force:
            raise PipelineError("tutarlılık hatası: " + "; ".join(rep["errors"]))

    # ------------------------------------------------------------ timing
    def _layout(self, durations: dict[int, float]) -> dict:
        script = self._json_r("script.json")
        if is_long(script):
            timed, ranges, total = time_scenes(script["beats"], durations, min_seconds=script.get("min_seconds"))
        else:
            timed = time_beats(script["beats"], durations, TARGET_SECONDS)
            total = episode_duration(timed, TARGET_SECONDS)
            ranges = [(0.0, total)]
        return {"beats": [{"id": t.id, "type": t.type, "start": t.start, "end": t.end} for t in timed],
                "scenes": ranges, "duration": total, "long": is_long(script)}

    def _timeline(self) -> dict:
        tl = self._json_r("timeline.json")
        if isinstance(tl, list):  # legacy format
            last = tl[-1]["end"] if tl else 0
            tl = {"beats": tl, "scenes": [(0.0, max(TARGET_SECONDS, last + 1.4))],
                  "duration": max(TARGET_SECONDS, last + 1.4), "long": False}
        return tl

    def _timed(self) -> list[TimedBeat]:
        script = self._json_r("script.json")
        tl = self._timeline()
        voices = self._json_r("voices.json")
        cues = self._json_r("lipsync.json")
        out = []
        for t in tl["beats"]:
            tb = TimedBeat(t["id"], t["type"], t["start"], t["end"], script["beats"][t["id"]])
            if str(t["id"]) in voices:
                tb.audio = voices[str(t["id"])]["wav"]
                tb.cues = cues.get(str(t["id"]), [])
            out.append(tb)
        return out

    # ------------------------------------------------------------ scene contexts
    def _scene_cast(self, script: dict, k: int, series: dict) -> list[str]:
        sc = script["scenes"][k]
        if sc.get("cast"):
            return list(sc["cast"])
        cast = set((sc.get("blocking") or {}).keys())
        for b in script["beats"]:
            if b.get("_scene", 0) != k:
                continue
            if b.get("speaker"):
                cast.add(b["speaker"])
            for key in ("moves", "poses", "props", "expressions", "looks", "glow"):
                cast |= set((b.get(key) or {}).keys())
        if k == 0 and not cast:
            cast = set(series["characters"])
        return [c for c in series["characters"] if c in cast]

    def _contexts(self, timed: list[TimedBeat], shots: list[Shot] | None = None, tl: dict | None = None):
        """One render context per scene (own location, lighting, blocking, performance)."""
        ep, series, chars, locs = self._world()
        script = self._json_r("script.json")
        tl = tl or self._timeline()
        total = tl["duration"]
        long_ = tl.get("long", False)
        out = []
        prev = None
        shot_list: list[Shot] = []
        for k, sc in enumerate(script["scenes"]):
            t0, t1 = tl["scenes"][k]
            loc_rec = locs[sc.get("location_id", script["location_id"])]
            loc = make_location(loc_rec, sc.get("lighting", script.get("lighting", "day")))
            cast = self._scene_cast(script, k, series)
            if k == 0:
                base, env0 = resolve_blocking(script, series, chars)
                blocking = {c: base[c] for c in cast if c in base}
            else:
                continuous = sc.get("continuous", prev is not None and
                                    prev["location_id"] == sc.get("location_id", script["location_id"]))
                blocking, env0 = {}, {}
                if continuous and prev:
                    blocking = {c: dict(prev["end_blocking"][c]) for c in cast if c in prev["end_blocking"]}
                    env0 = {kk: vv for kk, vv in prev["end_env"].items() if kk == "lamp"}
            for c in cast:
                b = dict(blocking.get(c, {}))
                b.update((sc.get("blocking") or {}).get(c, {}))
                if "x" not in b:
                    n = len([x for x in blocking if x != c])
                    b.update(x=1100 + 600 * n, dir=1 if n % 2 == 0 else -1)
                    b["turn"] = 0.45 * b["dir"]
                blocking[c] = b
            env0 = {**env0, **(sc.get("env_start") or {})}
            beats_k = [tb for tb in timed if tb.data.get("_scene", 0) == k]
            perf = Performance(beats_k, blocking, loc_rec.get("spots", {}), world_objects(loc),
                               seed=f"{self.episode_id}:{k}", env0=env0)
            rigs = {cid: CharacterRig(chars[cid]["design"]) for cid in blocking}
            if shots is None:
                heights = {cid: rigs[cid].H for cid in rigs}
                cams = {name: object_camera(loc, name) for name in loc.objects()}
                sk = build_shots(beats_k, blocking, heights, t1, cams, seed=f"{self.episode_id}:{k}",
                                 xpos=lambda cid, t, perf=perf: perf.char_x(cid, t)[0], t0=t0, scene=k,
                                 index_offset=len(shot_list))
                shot_list += sk
            else:
                sk = [s for s in shots if s.scene == k]
            caps = [(tb.start, tb.end + 0.15, tb.data["text"]) for tb in timed if tb.type == "line"]
            ctx = RenderContext(loc, rigs, perf, sk, total, caps,
                                title=(series["title"], f"Bölüm {script['episode_number']}: {script['title']}") if k == 0 else None,
                                quality=self.quality)
            ctx.end_card_at = (total - 4.5) if long_ and not packaging.available() else None
            ctx.series_name = series["title"]
            end_blocking = {}
            for cid, ct in perf.chars.items():
                b = dict(perf.blocking[cid])
                b["x"] = perf.char_x(cid, t1)[0]
                b["prop"] = ct.prop.at(t1)[1]
                b["glow"] = ct.glow.at(t1)[1] or 0.0
                b["pose"] = ct.pose.at(t1)[1] or "idle"
                b["expression"] = "neutral"
                end_blocking[cid] = b
            end_env = {kk: tr.keys[-1][1] for kk, tr in perf.env.items() if tr.keys}
            prev = {"location_id": sc.get("location_id", script["location_id"]), "end_blocking": end_blocking,
                    "end_env": end_env, "start_blocking": {cid: {"x": perf.char_x(cid, t0)[0], "prop": ct.prop.at(t0)[1]}
                                                           for cid, ct in perf.chars.items()}}
            out.append({"ctx": ctx, "perf": perf, "loc": loc, "t0": t0, "t1": t1, **prev})
        return out

    def _all_shots(self, scs) -> list[Shot]:
        return [s for sc in scs for s in sc["ctx"].shots]

    # ------------------------------------------------------------ storyboard
    def _contact_sheet(self, scs, shots: list[Shot], out: Path):
        n = len(shots)
        cols = 4 if n <= 16 else 6
        tw, th = (480, 270) if n <= 16 else (320, 180)
        rows = (n + cols - 1) // cols
        surf = skia.Surface(cols * tw + (cols + 1) * 10, rows * (th + 34) + 10)
        c = surf.getCanvas()
        c.clear(skia.Color(24, 24, 28))
        font = skia.Font(skia.Typeface.MakeFromFile(config.font_path(True)), 14)
        renderers = {}
        for i, sh in enumerate(shots):
            sc = scs[sh.scene]
            r = renderers.get(sh.scene) or FrameRenderer(sc["ctx"], tw, th, False)
            renderers[sh.scene] = r
            t = (sh.start + sh.end) / 2
            r.render(max(sh.start, t - 0.05), sh)
            arr = r.render(t, sh)
            img = skia.Image.fromarray(arr, colorType=skia.kBGRA_8888_ColorType)
            x = 10 + (i % cols) * (tw + 10)
            y = 10 + (i // cols) * (th + 34)
            c.drawImage(img, x, y)
            c.drawString(f"#{sh.index} S{sh.scene + 1} {sh.kind} {sh.start:.0f}-{sh.end:.0f}s", x, y + th + 20, font,
                         skia.Paint(Color=skia.ColorWHITE))
        surf.makeImageSnapshot().save(str(out), skia.kPNG)
        self._artifact(out)

    def stage_storyboard(self):
        script = self._json_r("script.json")
        est = {i: max(1.2, len(b["text"]) / 14.0) for i, b in enumerate(script["beats"]) if b["type"] == "line"}
        tl = self._layout(est)
        timed = [TimedBeat(t["id"], t["type"], t["start"], t["end"], script["beats"][t["id"]]) for t in tl["beats"]]
        scs = self._contexts(timed, tl=tl)
        shots = self._all_shots(scs)
        self._json_w("storyboard_draft.json", [s.to_json() for s in shots])
        self._contact_sheet(scs, shots, self.work / "storyboard_draft.png")
        key = f"{self.key_prefix}/storyboard_draft.png"
        self.store.upload(self.work / "storyboard_draft.png", key)
        ep = self.store.get("episodes", self.episode_id) or {}
        ep.setdefault("outputs", {})["storyboard_key"] = key
        ep["estimated_duration"] = tl["duration"]
        self.store.put("episodes", self.episode_id, ep)

    def stage_voices(self):
        ep, series, chars, locs = self._world()
        script = self._json_r("script.json")
        out = self._json_r("voices.json") if (self.work / "voices.json").exists() else {}
        lines = [(i, b) for i, b in enumerate(script["beats"]) if b["type"] == "line"]
        engines = set()
        from .tts import resolve_engine
        for k, (i, b) in enumerate(lines):
            prof = chars[b["speaker"]]["voice"]
            sig = f"{b['speaker']}|{resolve_engine(prof)}|{b['text']}"
            prev = out.get(str(i))
            if prev and prev.get("sig") == sig and (self.work / prev["wav"]).exists():
                continue   # resume: this line was already voiced with the same text/voice
            wav = self.work / "voices" / f"beat_{i:03d}.wav"
            engines.add(resolve_engine(prof))
            dur = synthesize(b["text"], prof, wav, cache_dir=config.WORK_DIR / "_tts_cache")
            self._artifact(wav)
            out[str(i)] = {"wav": str(wav.relative_to(self.work)), "duration": dur, "speaker": b["speaker"], "sig": sig}
            if k % 10 == 0:
                self._json_w("voices.json", out)   # checkpoint long episodes
                self._progress("voices", (k + 1) / len(lines))
        valid = {str(i) for i, _ in lines}
        out = {k: v for k, v in out.items() if k in valid}
        self._json_w("voices.json", out)
        self.log(f"  ses motoru: {', '.join(sorted(engines)) or 'önbellek'}")

    def stage_animate(self):
        voices = self._json_r("voices.json")
        durs = {int(k): v["duration"] for k, v in voices.items()}
        tl = self._layout(durs)
        self._json_w("timeline.json", tl)
        self.log(f"  süre: {tl['duration']:.1f} sn, {len(tl['scenes'])} sahne")

    def stage_lipsync(self):
        script = self._json_r("script.json")
        voices = self._json_r("voices.json")
        cues = {}
        for k, v in voices.items():
            b = script["beats"][int(k)]
            cues[k] = cues_for(self.work / v["wav"], b["text"])
        self._json_w("lipsync.json", cues)

    def _shorts_window(self, timed: list[TimedBeat], tl: dict) -> tuple[float, float]:
        """Pick a 45-58 s highlight for vertical Shorts/Reels/TikTok (long episodes only)."""
        script = self._json_r("script.json")
        if "shorts_window" in script:
            a_id, b_id = script["shorts_window"]
            a = next(t.start for t in timed if t.id == a_id) - 1.0
            b = next(t.end for t in timed if t.id == b_id) + 1.0
            return max(0.0, a), min(tl["duration"], a + SHORTS_MAX, b)
        lines = [t for t in timed if t.type == "line"]
        weight = {"surprised": 3, "scared": 3, "excited": 3, "laugh": 2, "happy": 2, "curious": 2, "worried": 2}
        best, best_score = (0.0, min(SHORTS_MAX, tl["duration"])), -1
        for i, first in enumerate(lines):
            a = max(0.0, first.start - 1.0)
            end_lines = [ln for ln in lines[i:] if ln.end + 0.6 - a <= SHORTS_MAX]
            if not end_lines:
                continue
            b = end_lines[-1].end + 0.6
            if b - a < 40:
                continue
            score = sum(weight.get(ln.data.get("emotion"), 1) for ln in end_lines)
            if score > best_score:
                best, best_score = (round(a, 3), round(b, 3)), score
        return best

    def stage_staging(self):
        timed = self._timed()
        tl = self._timeline()
        scs = self._contexts(timed, tl=tl)
        shots = self._all_shots(scs)
        self._json_w("shots.json", [s.to_json() for s in shots])
        if tl.get("long"):
            a, b = self._shorts_window(timed, tl)
            clipped = []
            for s in shots:
                if s.end <= a or s.start >= b:
                    continue
                d = s.to_json()
                d.update(start=max(s.start, a), end=min(s.end, b), index=len(clipped))
                clipped.append(d)
            self._json_w("shorts.json", {"window": [a, b], "shots": clipped})
            self.log(f"  Shorts kesiti: {a:.1f}-{b:.1f} sn ({b - a:.1f} sn)")
        self._contact_sheet(scs, shots, self.work / "storyboard.png")

    def _load_shots(self, name: str) -> list[Shot]:
        data = self._json_r(name)
        if isinstance(data, dict):
            data = data["shots"]
        out = []
        for d in data:
            d = dict(d)
            d["cam_from"] = CamKey(**d["cam_from"])
            d["cam_to"] = CamKey(**d["cam_to"])
            d.setdefault("scene", 0)
            out.append(Shot(**d))
        return out

    def _shots(self, fmt: str = "youtube") -> list[Shot]:
        if fmt == "shorts" and (self.work / "shorts.json").exists():
            return self._load_shots("shorts.json")
        return self._load_shots("shots.json")

    def _shorts_window_saved(self) -> tuple[float, float] | None:
        p = self.work / "shorts.json"
        return tuple(json.loads(p.read_text())["window"]) if p.exists() else None

    def stage_audio(self):
        script = self._json_r("script.json")
        timed = self._timed()
        tl = self._timeline()
        scs = self._contexts(timed, shots=self._shots(), tl=tl)
        series = self.store.get("series", self._ep()["series_id"])
        dialogue, sfx_events, amb = [], [], []
        for tb in timed:
            b = tb.data
            perf = scs[b.get("_scene", 0)]["perf"]
            if tb.audio:
                x = perf.char_x(b["speaker"], tb.start)[0]
                dialogue.append((tb.start, self.work / tb.audio, (x - 1600) / 1600))
            for s in b.get("sfx", []) or []:
                name, off, gain, pan = (list(s) + [0, 0.5, 0])[:4]
                if name in ("wind", "waves", "rain"):
                    continue
                sfx_events.append((tb.start + float(off), name, float(gain), float(pan)))
            if b.get("moves"):
                sfx_events.append((tb.start, "footsteps", 0.3, 0.0))
        import numpy as np
        total = tl["duration"]
        n = int(total * audio_mod.SR)
        music = np.zeros(n, dtype=np.float32)
        for k, sc in enumerate(script["scenes"]):
            t0, t1 = tl["scenes"][k]
            mood = sc.get("music_mood") or script.get("music_mood") or series.get("music_mood", "warm")
            seg = audio_mod.music(max(2.0, t1 - t0 + 1.0), mood, seed=f"{series['id']}:{mood}")
            i0 = int(t0 * audio_mod.SR)
            seg = seg[: max(0, n - i0)]
            music[i0:i0 + len(seg)] += seg
            for a in sc.get("ambience") or script.get("ambience") or [["waves", 0.4]]:
                amb.append((a[0], float(a[1]), t0, t1))
        stats = audio_mod.mix(total, dialogue, sfx_events, amb, music, self.work / "mix.wav")
        self._artifact(self.work / "mix.wav")
        self._json_w("audio.json", {"duration": total, **stats})

    # ------------------------------------------------------------ render
    def render_shots(self, fmt: str, indices: list[int]) -> list[int]:
        """Render the given shots (no state writes - safe to call from worker processes)."""
        w, h, burn = FORMATS[fmt]
        shots = self._shots(fmt)
        scs = self._contexts(self._timed(), shots=self._load_shots("shots.json"))
        win = self._shorts_window_saved() if fmt == "shorts" else None
        renderers = {}
        for sh in shots:
            if sh.index not in indices:
                continue
            ctx = scs[sh.scene]["ctx"]
            ctx.shorts_window = win
            r = renderers.get(sh.scene) or FrameRenderer(ctx, w, h, burn)
            renderers[sh.scene] = r
            seg = self.work / "segments" / fmt / f"shot_{sh.index:03d}.mp4"
            r.render(max(0.0, sh.start - 1 / config.FPS), sh)  # warm look-at anchors
            encode_shot(ctx, sh, seg, w, h, burn, renderer=r)
        return indices

    def _render_format(self, fmt: str, only: list[int] | None = None):
        shots = self._shots(fmt)
        by_index = {s.index: s for s in shots}
        done = set(self.state["shots_done"].get(fmt, []))
        todo = [s.index for s in shots
                if (only is not None and s.index in only) or
                (only is None and not (s.index in done and (self.work / "segments" / fmt / f"shot_{s.index:03d}.mp4").exists()))]
        if not todo:
            return
        workers = max(1, min(len(todo), int(os.environ.get("STUDIO_RENDER_PROCS", os.cpu_count() or 2))))
        todo.sort(key=lambda i: -(by_index[i].end - by_index[i].start))   # longest first
        t0 = time.time()
        if workers == 1:
            results = ((i, self.render_shots(fmt, [i])) for i in todo)
        else:
            ex = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
            futs = {ex.submit(_render_job, str(self.work.parent), self.episode_id, fmt, [i], self.quality): i for i in todo}
            results = ((futs[f], f.result()) for f in as_completed(futs))
        total = len(shots)
        for i, _ in results:
            seg = self.work / "segments" / fmt / f"shot_{i:03d}.mp4"
            self._artifact(seg)
            done.add(i)
            self.state["shots_done"][fmt] = sorted(done)
            self._save_state()
            self.log(f"  {fmt} shot {len(done)}/{total} ({by_index[i].kind}) done, {time.time() - t0:.0f}s elapsed")
            self._progress("render", len(done) / total / len(self.formats) +
                           (list(self.formats).index(fmt) / len(self.formats)))
        if workers > 1:
            ex.shutdown()

    def stage_render(self):
        for fmt in self.formats:
            self._render_format(fmt)

    def _assemble_format(self, fmt: str) -> Path:
        shots = self._shots(fmt)
        lst = self.work / "segments" / fmt / "list.txt"
        lst.write_text("".join(f"file 'shot_{s.index:03d}.mp4'\n" for s in shots))
        out = self.work / "out" / f"{self.episode_id}_{fmt}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        win = self._shorts_window_saved() if fmt == "shorts" else None
        audio_in = ["-i", str(self.work / "mix.wav")]
        af = []
        if win:
            a, b = win
            audio_in = ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(self.work / "mix.wav")]
            af = ["-af", f"afade=t=in:d=0.4,afade=t=out:st={max(0.0, b - a - 1.2):.3f}:d=1.2"]
        subprocess.run([config.ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        *audio_in, "-map", "0:v", "-map", "1:a", "-c:v", "copy", *af,
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
        return out

    def _package(self, fmt: str, out: Path):
        """Remotion intro + end screen around long YouTube episodes (optional, see packaging.py)."""
        tl = self._timeline()
        if fmt != "youtube" or not tl.get("long") or not packaging.available():
            self.state.pop("packaging", None)
            return
        script = self._json_r("script.json")
        series = self.store.get("series", self._ep()["series_id"])
        import numpy as np
        mood = script["scenes"][-1].get("music_mood") or series.get("music_mood", "warm")
        m = audio_mod.music(packaging.END_S + 0.5, mood, seed=f"{series['id']}:{mood}")
        wav = self.work / "packaging" / "end_music.wav"
        wav.parent.mkdir(parents=True, exist_ok=True)
        audio_mod.write_wav(wav, np.stack([m, m], axis=1) * 0.8)
        n = script["episode_number"]
        offset = packaging.package_long_episode(
            out, self.work, series["title"], f"Bölüm {n}", script["title"],
            script.get("next_title") or f"Bölüm {n + 1}", wav)
        self.state["packaging"] = {"offset": offset, "tail": packaging.END_S}
        self.log(f"  Remotion paketleme: +{offset:.0f} sn açılış, +{packaging.END_S:.0f} sn bitiş ekranı")

    def stage_assemble(self):
        for fmt in self.formats:
            out = self._assemble_format(fmt)
            self._package(fmt, out)
            self._artifact(out)

    def _qc(self) -> dict:
        tl = self._timeline()
        report = {"formats": {}, "failed_shots": {}}
        for fmt in self.formats:
            w, h, _ = FORMATS[fmt]
            shots = self._shots(fmt)
            failed = []
            for sh in shots:
                seg = self.work / "segments" / fmt / f"shot_{sh.index:03d}.mp4"
                exp = (round(sh.end * config.FPS) - round(sh.start * config.FPS)) / config.FPS
                r = check_segment(seg, w, h, exp)
                if not r["ok"]:
                    failed.append({"shot": sh.index, "issues": r["issues"]})
            master = self.work / "out" / f"{self.episode_id}_{fmt}.mp4"
            win = self._shorts_window_saved() if fmt == "shorts" else None
            if win:
                lo, hi = (win[1] - win[0]) - 1.0, min(60.0, (win[1] - win[0]) + 1.0)
            elif tl.get("long"):
                pk = self.state.get("packaging") if fmt == "youtube" else None
                extra = (pk["offset"] + pk["tail"]) if pk else 0.0
                lo, hi = (tl["duration"] + extra) * 0.97, (tl["duration"] + extra) * 1.03
            else:
                lo, hi = 28.0, 32.5
            report["formats"][fmt] = check_master(master, w, h, min_dur=lo, max_dur=hi)
            report["failed_shots"][fmt] = failed
        report["ok"] = all(r["ok"] for r in report["formats"].values()) and not any(report["failed_shots"].values())
        return report

    def stage_qc(self):
        rep = self._qc()
        self._json_w("qc.json", rep)
        self.log(f"  QC ok={rep['ok']} {json.dumps(rep['formats'], ensure_ascii=False)[:400]}")

    def stage_repair(self):
        rep = self._json_r("qc.json")
        tries = 0
        while not rep["ok"] and tries < 2:
            tries += 1
            for fmt in self.formats:
                bad = [f["shot"] for f in rep["failed_shots"].get(fmt, [])]
                if bad:
                    self.log(f"  yeniden render {fmt}: {bad}")
                    self._render_format(fmt, only=bad)
                self._package(fmt, self._assemble_format(fmt))
            rep = self._qc()
            self._json_w("qc.json", rep)
        if not rep["ok"]:
            raise PipelineError("kalite kontrol başarısız: " + json.dumps(rep, ensure_ascii=False)[:500])

    def stage_upload(self):
        ep, series, chars, locs = self._world()
        script = self._json_r("script.json")
        outs: dict[str, str] = {}
        timed = self._timed()
        off = (self.state.get("packaging") or {}).get("offset", 0.0)   # Remotion intro shifts the YouTube master
        tr = [(tb.start + off, tb.end + 0.15 + off, tb.data["text"]) for tb in timed if tb.type == "line"]
        en = [(tb.start + off, tb.end + 0.15 + off, tb.data.get("text_en", "")) for tb in timed if tb.type == "line"]
        files = {
            "srt_tr": write_srt(tr, self.work / "out" / f"{self.episode_id}.tr.srt"),
            "srt_en": write_srt(en, self.work / "out" / f"{self.episode_id}.en.srt"),
        }
        shots = self._shots()
        pick = next((s for s in shots if s.kind in ("cu", "mcu") and any(
            script["beats"][b].get("emotion") in ("surprised", "happy", "curious") for b in s.beat_ids)), shots[len(shots) // 2])
        scs = self._contexts(timed, shots=shots)
        ctx = scs[pick.scene]["ctx"]
        ctx.title = None
        ctx.end_card_at = None
        frame = still(ctx, pick, (pick.start + pick.end) / 2, 1920, 1080, self.work / "out" / "thumb_frame.png")
        files["thumbnail"] = thumbnail(frame, script["title"], series["title"], self.work / "out" / f"{self.episode_id}_thumb.png")
        meta = metadata(series, script, chars)
        mp = self.work / "out" / f"{self.episode_id}_metadata.json"
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        files["metadata"] = mp
        for fmt in self.formats:
            files[f"{fmt}_mp4"] = self.work / "out" / f"{self.episode_id}_{fmt}.mp4"
        files["storyboard"] = self.work / "storyboard.png"
        for k, p in files.items():
            outs[k] = self.store.upload(p, f"{self.key_prefix}/{p.name}")
            outs[k + "_key"] = f"{self.key_prefix}/{p.name}"
        ep["outputs"] = outs
        ep["metadata"] = meta
        ep["qc"] = self._json_r("qc.json")
        self.store.put("episodes", self.episode_id, ep)

    def stage_publish(self):
        ep, series, chars, locs = self._world()
        script = self._json_r("script.json")
        timed = self._timed()
        tl = self._timeline()
        scs = self._contexts(timed, shots=self._shots(), tl=tl)
        last, first = scs[-1], scs[0]
        new_series = apply_episode(series, script, {"blocking": last["end_blocking"], "env": last["end_env"],
                                                     "lighting": script["scenes"][-1].get("lighting"),
                                                     "location_id": last["location_id"]})
        self.store.put("series", series["id"], new_series)
        ep["status"] = "ready"
        pk = self.state.get("packaging")
        ep["duration"] = tl["duration"] + ((pk["offset"] + pk["tail"]) if pk else 0.0)
        ep["packaging"] = pk
        ep["scenes"] = len(scs)
        ep["shorts_window"] = self._shorts_window_saved()
        used = {c for sc in scs for c in sc["perf"].chars}
        ep["character_hashes"] = {cid: {"design": chars[cid]["design_hash"], "voice": chars[cid]["voice_hash"]}
                                  for cid in chars if cid in used}
        ep["end_state"] = {"blocking": last["end_blocking"], "env": last["end_env"]}
        ep["start_state"] = {"blocking": first["start_blocking"]}
        ep["pipeline"] = {**(ep.get("pipeline") or {}), "percent": 100, "stage": "publish", "stage_label": "Hazır"}
        self.store.put("episodes", self.episode_id, ep)
        self.log(f"✔ {self.episode_id} hazır ({tl['duration']:.0f} sn)")


def _render_job(work_root: str, episode_id: str, fmt: str, indices: list[int], quality: str) -> list[int]:
    from .store import get_store
    p = Pipeline(get_store(), episode_id, work_root=Path(work_root), quality=quality)
    return p.render_shots(fmt, indices)


def cleanup(work: Path):
    shutil.rmtree(work, ignore_errors=True)
