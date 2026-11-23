"""Command line entry point:  python -m studio <command>

  init-demo                 create the acceptance cast/location/series + 2 episode drafts
  produce <episode_id>      run (or resume) the full pipeline for one episode
  sheets <character_id>     render model sheet + mouth chart for a character
  estimate --mode economic  print a cost estimate
  worker [--once]           poll the job queue (Supabase) and produce episodes
  acceptance                init-demo + produce both episodes + continuity report
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import config
from .bible import new_character, new_series
from .store import get_store


def cmd_init_demo(store, args=None):
    from .demo.characters import ADA, TOMO, LIGHTHOUSE
    from .demo.episodes import SERIES, EP1, EP2
    if store.get("series", SERIES["id"]) and not getattr(args, "reset", False):
        print("demo already initialised")
        return SERIES["id"]
    store.put("series", SERIES["id"], new_series(SERIES))
    for spec in (ADA, TOMO):
        store.put("characters", spec["id"], new_character(spec, SERIES["id"]))
    store.put("locations", LIGHTHOUSE["id"], {**LIGHTHOUSE, "series_id": SERIES["id"], "approved": True})
    for ep in (EP1, EP2):
        eid = f"{SERIES['id']}_ep{ep['episode_number']:03d}"
        store.put("episodes", eid, {"series_id": SERIES["id"], "episode_number": ep["episode_number"],
                                    "title": ep["title"], "status": "draft", "mode": "economic",
                                    "topic": ep["summary"], "script": ep})
    print("demo initialised:", SERIES["id"])
    return SERIES["id"]


def cmd_seed_ep3(store) -> str:
    """Add Captain Nehir, the harbor + lighthouse-room sets and the long-form episode 3."""
    from .demo.characters import NEHIR, LIGHTHOUSE_ROOM, HARBOR
    from .demo.episode3 import EP3
    sid = EP3["series_id"]
    series = store.get("series", sid)
    if NEHIR["id"] not in series["characters"]:
        series["characters"].append(NEHIR["id"])
    for loc in (LIGHTHOUSE_ROOM, HARBOR):
        if loc["id"] not in series["locations"]:
            series["locations"].append(loc["id"])
        store.put("locations", loc["id"], {**loc, "series_id": sid, "approved": True})
    store.put("series", sid, series)
    if not store.get("characters", NEHIR["id"]):
        store.put("characters", NEHIR["id"], new_character(NEHIR, sid))
    eid = f"{sid}_ep{EP3['episode_number']:03d}"
    store.put("episodes", eid, {"series_id": sid, "episode_number": EP3["episode_number"], "title": EP3["title"],
                                "status": "draft", "mode": "economic", "topic": EP3["summary"], "script": EP3,
                                "length": "long"})
    print("episode 3 seeded:", eid)
    return eid


def cmd_sheets(store, cid: str, out_dir: Path):
    from .rig import render_mouth_chart, render_turnaround
    ch = store.get("characters", cid)
    out_dir.mkdir(parents=True, exist_ok=True)
    a = out_dir / f"{cid}_model_sheet.png"
    b = out_dir / f"{cid}_mouth_shapes.png"
    render_turnaround(ch["design"], str(a))
    render_mouth_chart(ch["design"], str(b))
    refs = {"model_sheet": store.upload(a, f"characters/{cid}/{a.name}"),
            "mouth_shapes": store.upload(b, f"characters/{cid}/{b.name}"),
            "model_sheet_key": f"characters/{cid}/{a.name}", "mouth_shapes_key": f"characters/{cid}/{b.name}"}
    ch["reference_images"] = refs
    store.put("characters", cid, ch)
    return refs


def finalize_character(store, cid: str, approve: bool = False) -> dict:
    """Recompute identity hashes + library, render references and a voice sample."""
    from .bible import new_character
    from .tts import synthesize
    ch = store.get("characters", cid)
    rec = new_character({**ch, "id": cid}, ch.get("series_id"))
    rec["approved"] = approve or (ch.get("approved") and ch.get("design_hash") == rec["design_hash"]
                                  and ch.get("voice_hash") == rec["voice_hash"])
    rec.pop("approval_pending", None)
    store.put("characters", cid, rec)
    cmd_sheets(store, cid, config.WORK_DIR / "sheets")
    wav = config.WORK_DIR / "sheets" / f"{cid}_voice.wav"
    first = rec["name"].split()[0]
    synthesize(f"Merhaba, ben {first}. Bu benim sabit ses profilim.", rec["voice"], wav)
    rec = store.get("characters", cid)
    rec.setdefault("reference_images", {})
    rec["reference_images"]["voice_sample_key"] = f"characters/{cid}/{wav.name}"
    rec["reference_images"]["voice_sample"] = store.upload(wav, f"characters/{cid}/{wav.name}")
    store.put("characters", cid, rec)
    if approve:
        for sid in {rec.get("series_id")} - {None}:
            s = store.get("series", sid)
            if s and cid not in s.get("characters", []):
                s["characters"].append(cid)
                store.put("series", sid, s)
    return rec


def cmd_produce(store, episode_id: str, formats=("youtube", "shorts"), force=False):
    from .pipeline import Pipeline
    p = Pipeline(store, episode_id, formats=tuple(formats), force_continuity=force)
    return p.run()


def cmd_worker(store, once: bool, max_jobs: int, idle_exit: int):
    from .queue import Worker
    Worker(store).loop(once=once, max_jobs=max_jobs, idle_exit_s=idle_exit)


def cmd_acceptance(store, formats):
    sid = cmd_init_demo(store)
    for cid in ("chr_ada", "chr_tomo"):
        finalize_character(store, cid, approve=True)
    results = []
    for n in (1, 2):
        eid = f"{sid}_ep{n:03d}"
        t0 = time.time()
        ep = cmd_produce(store, eid, formats)
        results.append({"episode": eid, "status": ep["status"], "seconds": round(time.time() - t0, 1),
                        "duration": ep.get("duration"), "qc": ep.get("qc", {}).get("formats")})
    from .acceptance import continuity_report
    rep = continuity_report(store, sid)
    print(json.dumps({"episodes": results, "continuity": rep}, ensure_ascii=False, indent=2))
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init-demo")
    s.add_argument("--reset", action="store_true")
    s = sub.add_parser("produce")
    s.add_argument("episode_id")
    s.add_argument("--formats", default="youtube,shorts")
    s.add_argument("--force", action="store_true")
    s = sub.add_parser("sheets")
    s.add_argument("character_id")
    s = sub.add_parser("estimate")
    s.add_argument("--mode", default="economic")
    s.add_argument("--duration", type=float, default=30)
    s = sub.add_parser("worker")
    s.add_argument("--once", action="store_true")
    s.add_argument("--max-jobs", type=int, default=5)
    s.add_argument("--idle-exit", type=int, default=60)
    sub.add_parser("seed-ep3")
    s = sub.add_parser("acceptance")
    s.add_argument("--formats", default="youtube,shorts")
    args = ap.parse_args(argv)
    store = get_store()
    if args.cmd == "init-demo":
        cmd_init_demo(store, args)
    elif args.cmd == "produce":
        ep = cmd_produce(store, args.episode_id, args.formats.split(","), args.force)
        print(json.dumps({k: ep.get(k) for k in ("status", "outputs", "duration")}, ensure_ascii=False, indent=2))
    elif args.cmd == "sheets":
        print(cmd_sheets(store, args.character_id, config.WORK_DIR / "sheets"))
    elif args.cmd == "estimate":
        from .cost import estimate
        print(json.dumps(estimate(args.mode, args.duration, use_llm=bool(config.ANTHROPIC_API_KEY)), indent=2,
                         ensure_ascii=False))
    elif args.cmd == "worker":
        cmd_worker(store, args.once, args.max_jobs, args.idle_exit)
    elif args.cmd == "seed-ep3":
        cmd_seed_ep3(store)
    elif args.cmd == "acceptance":
        rep = cmd_acceptance(store, args.formats.split(","))
        sys.exit(0 if rep["ok"] else 1)


if __name__ == "__main__":
    main()
