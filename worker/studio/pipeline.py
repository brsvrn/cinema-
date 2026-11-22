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
from .location import GROUND_Y, HORIZON_Y, make_location, object_camera
from .lipsync import cues_for
from .performance import Performance
from .publish import metadata, thumbnail, write_srt
from .qc import check_master, check_segment
from .render import FrameRenderer, RenderContext, encode_shot, still
from .rig import CharacterRig
from .storyboard import TimedBeat, build_shots, episode_duration, time_beats
from .tts import synthesize
from . import audio as audio_mod
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


def world_objects(loc) -> dict[str, tuple[float, float, float]]:
    return {
        "lamp": (loc.tower_x, loc.tower_top + 140, 0.0),
        "tower": (loc.tower_x, 700.0, 0.0),
        "door": (loc.tower_x - 20, GROUND_Y - 120, 0.0),
        "boat": (1060.0, HORIZON_Y, 0.0),
        "sea": (500.0, HORIZON_Y + 40, 0.0),
        "ground": (860.0, GROUND_Y + 10, 0.0),
        "bench": (float(loc.loc.get("spots", {}).get("bench", 1100)), GROUND_Y - 100, 0.0),
    }


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
        script = dict(script)
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

    def _context(self, timed: list[TimedBeat], shots=None, lighting=None) -> tuple[RenderContext, Performance, Any]:
        ep, series, chars, locs = self._world()
        script = self._json_r("script.json")
        loc_rec = locs[script["location_id"]]
        loc = make_location(loc_rec, lighting or script.get("lighting", "day"))
        blocking, env0 = resolve_blocking(script, series, chars)
        perf = Performance(timed, blocking, loc_rec.get("spots", {}), world_objects(loc), seed=self.episode_id, env0=env0)
        rigs = {cid: CharacterRig(chars[cid]["design"]) for cid in blocking}
        dur = episode_duration(timed, TARGET_SECONDS)
        if shots is None:
            heights = {cid: rigs[cid].H for cid in rigs}
            cams = {name: object_camera(loc, name) for name in ("lamp", "tower", "door", "boat", "sea", "bench", "ground")}
            shots = build_shots(timed, blocking, heights, dur, cams, seed=self.episode_id,
                                xpos=lambda cid, t: perf.char_x(cid, t)[0])
        caps = [(tb.start, tb.end + 0.15, tb.data["text"]) for tb in timed if tb.type == "line"]
        ctx = RenderContext(loc, rigs, perf, shots, dur, caps,
                            title=(series["title"], f"Bölüm {script['episode_number']}: {script['title']}"),
                            quality=self.quality)
        return ctx, perf, loc

    def _contact_sheet(self, ctx: RenderContext, out: Path, cols: int = 4):
        tw, th = 480, 270
        n = len(ctx.shots)
        rows = (n + cols - 1) // cols
        surf = skia.Surface(cols * tw + (cols + 1) * 10, rows * (th + 40) + 10)
        c = surf.getCanvas()
        c.clear(skia.Color(24, 24, 28))
        font = skia.Font(skia.Typeface.MakeFromFile(config.font_path(True)), 16)
        r = FrameRenderer(ctx, tw, th, False)
        for i, sh in enumerate(ctx.shots):
            t = (sh.start + sh.end) / 2
            r.render(max(sh.start, t - 0.05), sh)
            arr = r.render(t, sh)
            img = skia.Image.fromarray(arr, colorType=skia.kBGRA_8888_ColorType)
            x = 10 + (i % cols) * (tw + 10)
            y = 10 + (i // cols) * (th + 40)
            c.drawImage(img, x, y)
            c.drawString(f"#{i} {sh.kind} {sh.start:.1f}-{sh.end:.1f}s {sh.subject or ''}", x, y + th + 24, font,
                         skia.Paint(Color=skia.ColorWHITE))
        surf.makeImageSnapshot().save(str(out), skia.kPNG)
        self._artifact(out)

    def stage_storyboard(self):
        script = self._json_r("script.json")
        est = {i: max(1.2, len(b["text"]) / 14.0) for i, b in enumerate(script["beats"]) if b["type"] == "line"}
        timed = time_beats(script["beats"], est, TARGET_SECONDS)
        ctx, _, _ = self._context(timed)
        self._json_w("storyboard_draft.json", [s.to_json() for s in ctx.shots])
        self._contact_sheet(ctx, self.work / "storyboard_draft.png")
        key = f"{self.key_prefix}/storyboard_draft.png"
        self.store.upload(self.work / "storyboard_draft.png", key)
        ep = self.store.get("episodes", self.episode_id) or {}
        ep.setdefault("outputs", {})["storyboard_key"] = key
        self.store.put("episodes", self.episode_id, ep)

    def stage_voices(self):
        ep, series, chars, locs = self._world()
        script = self._json_r("script.json")
        out = {}
        lines = [(i, b) for i, b in enumerate(script["beats"]) if b["type"] == "line"]
        for k, (i, b) in enumerate(lines):
            wav = self.work / "voices" / f"beat_{i:02d}.wav"
            dur = synthesize(b["text"], chars[b["speaker"]]["voice"], wav, cache_dir=config.WORK_DIR / "_tts_cache")
            self._artifact(wav)
            out[str(i)] = {"wav": str(wav.relative_to(self.work)), "duration": dur, "speaker": b["speaker"]}
            self._progress("voices", (k + 1) / len(lines))
        self._json_w("voices.json", out)

    def stage_animate(self):
        script = self._json_r("script.json")
        voices = self._json_r("voices.json")
        durs = {int(k): v["duration"] for k, v in voices.items()}
        timed = time_beats(script["beats"], durs, TARGET_SECONDS)
        self._json_w("timeline.json", [{"id": t.id, "type": t.type, "start": t.start, "end": t.end} for t in timed])

    def stage_lipsync(self):
        script = self._json_r("script.json")
        voices = self._json_r("voices.json")
        cues = {}
        for k, v in voices.items():
            b = script["beats"][int(k)]
            cues[k] = cues_for(self.work / v["wav"], b["text"])
        self._json_w("lipsync.json", cues)

    def _timed(self) -> list[TimedBeat]:
        script = self._json_r("script.json")
        tl = self._json_r("timeline.json")
        voices = self._json_r("voices.json")
        cues = self._json_r("lipsync.json")
        out = []
        for t in tl:
            tb = TimedBeat(t["id"], t["type"], t["start"], t["end"], script["beats"][t["id"]])
            if str(t["id"]) in voices:
                tb.audio = voices[str(t["id"])]["wav"]
                tb.cues = cues.get(str(t["id"]), [])
            out.append(tb)
        return out

    def stage_staging(self):
        timed = self._timed()
        ctx, perf, loc = self._context(timed)
        self._json_w("shots.json", [s.to_json() for s in ctx.shots])
        self._contact_sheet(ctx, self.work / "storyboard.png")

    def _shots(self):
        from .camera import CamKey
        from .storyboard import Shot
        out = []
        for d in self._json_r("shots.json"):
            d = dict(d)
            d["cam_from"] = CamKey(**d["cam_from"])
            d["cam_to"] = CamKey(**d["cam_to"])
            out.append(Shot(**d))
        return out

    def stage_audio(self):
        script = self._json_r("script.json")
        timed = self._timed()
        ctx, perf, _ = self._context(timed, shots=self._shots())
        dialogue = []
        sfx_events = []
        for tb in timed:
            b = tb.data
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
        series = self.store.get("series", self._ep()["series_id"])
        mus = audio_mod.music(ctx.duration, script.get("music_mood") or series.get("music_mood", "warm"),
                              seed=series["id"])
        amb = [tuple(a) for a in script.get("ambience", [["waves", 0.4]])]
        stats = audio_mod.mix(ctx.duration, dialogue, sfx_events, amb, mus, self.work / "mix.wav")
        self._artifact(self.work / "mix.wav")
        self._json_w("audio.json", {"duration": ctx.duration, **stats})

    def render_shots(self, fmt: str, indices: list[int]) -> list[int]:
        """Render the given shots (no state writes - safe to call from worker processes)."""
        w, h, burn = FORMATS[fmt]
        ctx, _, _ = self._context(self._timed(), shots=self._shots())
        renderer = FrameRenderer(ctx, w, h, burn)
        for sh in ctx.shots:
            if sh.index not in indices:
                continue
            seg = self.work / "segments" / fmt / f"shot_{sh.index:03d}.mp4"
            renderer.render(max(0.0, sh.start - 1 / config.FPS), sh)  # warm look-at anchors
            encode_shot(ctx, sh, seg, w, h, burn, renderer=renderer)
        return indices

    def _render_format(self, fmt: str, only: list[int] | None = None):
        shots = self._shots()
        done = set(self.state["shots_done"].get(fmt, []))
        todo = [s.index for s in shots
                if (only is not None and s.index in only) or
                (only is None and not (s.index in done and (self.work / "segments" / fmt / f"shot_{s.index:03d}.mp4").exists()))]
        if not todo:
            return
        workers = max(1, min(len(todo), int(os.environ.get("STUDIO_RENDER_PROCS", os.cpu_count() or 2))))
        # longest shots first for better packing
        todo.sort(key=lambda i: -(shots[i].end - shots[i].start))
        t0 = time.time()
        if workers == 1:
            futures_iter = ((i, self.render_shots(fmt, [i])) for i in todo)
            results = futures_iter
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
            self.log(f"  {fmt} shot {i + 1}/{total} ({shots[i].kind}) done, {time.time() - t0:.0f}s elapsed")
            self._progress("render", len(done) / total / len(self.formats) +
                           (list(self.formats).index(fmt) / len(self.formats)))
        if workers > 1:
            ex.shutdown()

    def stage_render(self):
        for fmt in self.formats:
            self._render_format(fmt)

    def _assemble_format(self, fmt: str) -> Path:
        shots = self._shots()
        lst = self.work / "segments" / fmt / "list.txt"
        lst.write_text("".join(f"file 'shot_{s.index:03d}.mp4'\n" for s in shots))
        out = self.work / "out" / f"{self.episode_id}_{fmt}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([config.ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-i", str(self.work / "mix.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
        return out

    def stage_assemble(self):
        for fmt in self.formats:
            out = self._assemble_format(fmt)
            self._artifact(out)

    def _qc(self) -> dict:
        shots = self._shots()
        report = {"formats": {}, "failed_shots": {}}
        for fmt in self.formats:
            w, h, _ = FORMATS[fmt]
            failed = []
            for sh in shots:
                seg = self.work / "segments" / fmt / f"shot_{sh.index:03d}.mp4"
                exp = (round(sh.end * config.FPS) - round(sh.start * config.FPS)) / config.FPS
                r = check_segment(seg, w, h, exp)
                if not r["ok"]:
                    failed.append({"shot": sh.index, "issues": r["issues"]})
            master = self.work / "out" / f"{self.episode_id}_{fmt}.mp4"
            report["formats"][fmt] = check_master(master, w, h)
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
                self._assemble_format(fmt)
            rep = self._qc()
            self._json_w("qc.json", rep)
        if not rep["ok"]:
            raise PipelineError("kalite kontrol başarısız: " + json.dumps(rep, ensure_ascii=False)[:500])

    def stage_upload(self):
        ep, series, chars, locs = self._world()
        script = self._json_r("script.json")
        outs: dict[str, str] = {}
        timed = self._timed()
        # subtitles
        tr = [(tb.start, tb.end + 0.15, tb.data["text"]) for tb in timed if tb.type == "line"]
        en = [(tb.start, tb.end + 0.15, tb.data.get("text_en", "")) for tb in timed if tb.type == "line"]
        files = {
            "srt_tr": write_srt(tr, self.work / "out" / f"{self.episode_id}.tr.srt"),
            "srt_en": write_srt(en, self.work / "out" / f"{self.episode_id}.en.srt"),
        }
        # thumbnail from the most expressive close-up
        shots = self._shots()
        pick = next((s for s in shots if s.kind in ("cu", "mcu") and any(
            script["beats"][b].get("emotion") in ("surprised", "happy", "curious") for b in s.beat_ids)), shots[len(shots) // 2])
        ctx, _, _ = self._context(timed, shots=shots)
        ctx.title = None
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
        ctx, perf, _ = self._context(timed, shots=self._shots())
        end_t = ctx.duration
        end_blocking = {}
        for cid, ct in perf.chars.items():
            b = dict(perf.blocking[cid])
            b["x"] = perf.char_x(cid, end_t)[0]
            b["prop"] = ct.prop.at(end_t)[1]
            b["glow"] = ct.glow.at(end_t)[1] or 0.0
            b["pose"] = ct.pose.at(end_t)[1] or "idle"
            b["expression"] = "neutral"
            end_blocking[cid] = b
        env_end = {k: tr.keys[-1][1] for k, tr in perf.env.items() if tr.keys}
        new_series = apply_episode(series, script, {"blocking": end_blocking, "env": env_end,
                                                     "lighting": script.get("lighting")})
        self.store.put("series", series["id"], new_series)
        ep["status"] = "ready"
        ep["duration"] = ctx.duration
        ep["character_hashes"] = {cid: {"design": chars[cid]["design_hash"], "voice": chars[cid]["voice_hash"]}
                                  for cid in chars}
        ep["end_state"] = {"blocking": end_blocking, "env": env_end}
        ep["start_state"] = {"blocking": {cid: {"x": perf.char_x(cid, 0.0)[0], "prop": ct.prop.at(0.0)[1]}
                                          for cid, ct in perf.chars.items()}}
        ep["pipeline"] = {**(ep.get("pipeline") or {}), "percent": 100, "stage": "publish", "stage_label": "Hazır"}
        self.store.put("episodes", self.episode_id, ep)
        self.log(f"✔ {self.episode_id} hazır")


def _render_job(work_root: str, episode_id: str, fmt: str, indices: list[int], quality: str) -> list[int]:
    from .store import get_store
    p = Pipeline(get_store(), episode_id, work_root=Path(work_root), quality=quality)
    return p.render_shots(fmt, indices)


def cleanup(work: Path):
    shutil.rmtree(work, ignore_errors=True)
