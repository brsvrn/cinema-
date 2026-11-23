"""Script beats -> timed storyboard (shots, blocking, camera, performance).

Shot grammar (automatic, deterministic):
  * episode opens on an establishing wide/crane shot
  * dialogue alternates speaker singles (MCU / CU / OTS) with reaction cut-ins
  * action beats that reference an object get an insert shot
  * the final beat pulls back to a wide two-shot
Every shot gets a camera move (push-in, pan, drift, crane) so nothing is a static still.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Any

from .camera import CamKey
from .location import GROUND_Y, STAGE_W

TARGET_DEFAULT = 30.0
FLAT_OBJECTS = {"boat", "sea", "lamp", "tower"}


@dataclass
class Shot:
    index: int
    start: float
    end: float
    kind: str                     # wide|two|mcu|cu|ots|insert|crane
    subject: str | None           # character id or object name
    other: str | None
    cam_from: CamKey
    cam_to: CamKey
    handheld: float = 1.5
    dof: float = 0.0
    beat_ids: list[int] = field(default_factory=list)
    description: str = ""
    flat: bool = False            # telephoto: no parallax zoom (inserts of far objects)
    scene: int = 0                # index into script scenes (own location/lighting)

    def to_json(self) -> dict:
        d = asdict(self)
        d["cam_from"] = asdict(self.cam_from)
        d["cam_to"] = asdict(self.cam_to)
        return d


@dataclass
class TimedBeat:
    id: int
    type: str
    start: float
    end: float
    data: dict[str, Any]
    audio: str | None = None
    cues: list[dict] = field(default_factory=list)


def time_beats(beats: list[dict], line_durations: dict[int, float], target: float = TARGET_DEFAULT,
               lead_in: float = 1.2, tail: float = 1.4) -> list[TimedBeat]:
    """Lay beats on a timeline and stretch pauses/action so the episode hits `target` seconds."""
    raw = []
    for i, b in enumerate(beats):
        if b["type"] == "line":
            raw.append(line_durations[i])
        else:
            raw.append(float(b.get("duration", 2.0)))
    gaps = [0.28] * (len(beats) - 1) + [0.0]
    fixed = sum(raw) + lead_in + tail
    total = fixed + sum(gaps)
    slack = target - total
    action_idx = [i for i, b in enumerate(beats) if b["type"] != "line"]
    if slack > 0:
        # distribute: 50% to action beats, 50% to gaps
        if action_idx:
            for i in action_idx:
                raw[i] += slack * 0.5 / len(action_idx)
            for i in range(len(gaps) - 1):
                gaps[i] += slack * 0.5 / max(1, len(gaps) - 1)
        else:
            for i in range(len(gaps) - 1):
                gaps[i] += slack / max(1, len(gaps) - 1)
    elif slack < 0:
        # shrink gaps & action first; dialogue is never time-stretched
        shrinkable = sum(gaps) - 0.08 * (len(gaps) - 1) + sum(max(0, raw[i] - 0.8) for i in action_idx)
        k = min(1.0, -slack / max(1e-6, shrinkable))
        gaps = [g - (g - 0.08) * k for g in gaps[:-1]] + [0.0]
        for i in action_idx:
            raw[i] -= max(0, raw[i] - 0.8) * k
    t = lead_in
    out = []
    for i, b in enumerate(beats):
        start = t
        end = t + raw[i]
        out.append(TimedBeat(i, b["type"], round(start, 3), round(end, 3), b))
        t = end + gaps[i]
    return out


def episode_duration(timed: list[TimedBeat], target: float, tail: float = 1.4) -> float:
    return max(target, timed[-1].end + tail) if timed else target


def time_scenes(beats: list[dict], line_durations: dict[int, float], lead_in: float = 2.4,
                gap: float = 0.4, scene_tail: float = 1.6, end_card: float = 4.5,
                min_seconds: float | None = None) -> tuple[list[TimedBeat], list[tuple[float, float]], float]:
    """See _time_scenes; if `min_seconds` is set, pauses and action beats are lengthened (never dialogue,
    pauses capped at 1.2 s) so the episode reaches e.g. the 8-minute YouTube mid-roll threshold."""
    timed, ranges, total = _time_scenes(beats, line_durations, lead_in, gap, scene_tail, end_card, 1.0)
    if not min_seconds or total >= min_seconds:
        return timed, ranges, total
    n_gaps = max(1, len(beats) - 1)
    action_total = sum(float(b.get("duration", 2.0)) for b in beats if b["type"] != "line")
    need = min_seconds - total
    extra_gap = min(1.2 - gap, need * 0.5 / n_gaps)
    rest = need - extra_gap * n_gaps
    k = 1.0 + max(0.0, rest) / max(1.0, action_total)
    return _time_scenes(beats, line_durations, lead_in, gap + extra_gap, scene_tail, end_card, min(k, 2.0))


def _time_scenes(beats: list[dict], line_durations: dict[int, float], lead_in: float,
                 gap: float, scene_tail: float, end_card: float, action_k: float) -> tuple[list[TimedBeat], list[tuple[float, float]], float]:
    """Natural-pace layout for long, multi-scene episodes (no stretching to a fixed length).

    Returns (timed beats, [(scene_start, scene_end)], total_duration).  Each scene gets an
    establishing lead-in; the last scene is followed by an end card.
    """
    out: list[TimedBeat] = []
    ranges: list[tuple[float, float]] = []
    t = 0.0
    n_scenes = max(b.get("_scene", 0) for b in beats) + 1 if beats else 1
    for sc in range(n_scenes):
        idx = [i for i, b in enumerate(beats) if b.get("_scene", 0) == sc]
        start = t
        t += lead_in
        for k, i in enumerate(idx):
            b = beats[i]
            d = line_durations[i] if b["type"] == "line" else float(b.get("duration", 2.0)) * action_k
            out.append(TimedBeat(i, b["type"], round(t, 3), round(t + d, 3), b))
            t += d + (gap if k < len(idx) - 1 else 0.0)
        t += scene_tail + (end_card if sc == n_scenes - 1 else 0.0)
        ranges.append((round(start, 3), round(t, 3)))
    return out, ranges, round(t, 3)


# ----------------------------------------------------------------- framing

def _char_frame(x: float, height: float, kind: str, dir_: int) -> CamKey:
    """Return a camera key framing a character standing at x with given pixel height."""
    head_y = GROUND_Y - height * 0.88
    if kind == "cu":
        vw = height * 1.12
        return CamKey(x + dir_ * vw * 0.12, head_y + height * 0.08, vw)
    if kind == "mcu":
        vw = height * 1.75
        return CamKey(x + dir_ * vw * 0.14, head_y + height * 0.27, vw)
    if kind == "ms":
        vw = height * 2.3
        return CamKey(x + dir_ * vw * 0.12, GROUND_Y - height * 0.55, vw)
    raise ValueError(kind)


def build_shots(timed: list[TimedBeat], blocking: dict[str, dict], heights: dict[str, float],
                duration: float, objects: dict[str, tuple[float, float, float]], seed: str = "ep",
                xpos=None, t0: float = 0.0, scene: int = 0, index_offset: int = 0) -> list[Shot]:
    """xpos(cid, t) -> stage x of a character at time t (accounts for walking)."""
    rng = random.Random(seed)
    shots: list[Shot] = []
    tallest = max(heights.values())
    base_blocking = blocking
    if xpos is None:
        xpos = lambda cid, t: base_blocking[cid]["x"]  # noqa: E731

    def two_at(t: float) -> CamKey:
        xs = [xpos(c, t) for c in base_blocking]
        mid_ = sum(xs) / len(xs)
        span_ = max(xs) - min(xs) if len(xs) > 1 else 600
        return CamKey(mid_, GROUND_Y - tallest * 0.55, max(span_ + tallest * 2.2, 1500))

    two = two_at(0.0)
    mid = two.cx
    wide = CamKey(STAGE_W * 0.55, GROUND_Y - 520, STAGE_W * 0.95)

    def add(kind, start, end, subject, other, a, b, hh=1.5, dof=0.0, beats=None, desc="", flat=False):
        shots.append(Shot(len(shots), round(start, 3), round(end, 3), kind, subject, other, a, b, hh, dof,
                          beats or [], desc, flat, scene))

    # establishing: crane/wide from sky down to two-shot
    first_end = timed[0].start if timed else t0 + 1.2
    est_from = CamKey(wide.cx + 250, wide.cy - 420, wide.view_w)
    if timed and timed[0].type == "action" and not timed[0].data.get("camera"):
        first_end = timed[0].end
        beats0 = [timed[0].id]
    else:
        beats0 = []
    add("crane", t0, max(first_end, t0 + 1.0), None, None, est_from, CamKey(wide.cx, wide.cy, wide.view_w * 0.8), 0.6,
        beats=beats0, desc="establishing")

    last_speaker = None
    alt = 0
    for tb in timed:
        if beats0 and tb.id == beats0[0]:
            continue
        b = tb.data
        tm = (tb.start + tb.end) / 2
        blocking = {c: {**base_blocking[c], "x": xpos(c, tm)} for c in base_blocking}
        two = two_at(tm)
        mid = two.cx
        start = shots[-1].end
        end = tb.end + (0.0 if tb.id < len(timed) - 1 else 0.0)
        cam_req = b.get("camera")
        if tb.type == "action":
            if cam_req and cam_req.startswith("insert:"):
                obj = cam_req.split(":", 1)[1]
                ox, oy, ow = objects.get(obj, (mid, GROUND_Y - 300, 700))
                add("insert", start, end, obj, None, CamKey(ox, oy, ow * 1.15), CamKey(ox, oy, ow * 0.9), 1.0,
                    beats=[tb.id], desc=b.get("description", ""), flat=obj in FLAT_OBJECTS)
            elif cam_req and cam_req.split(":")[0] in ("mcu", "cu", "ms") and ":" in cam_req:
                kind, cid = cam_req.split(":", 1)
                bx = xpos(cid, tb.end)
                k = _char_frame(bx, heights[cid], kind, blocking[cid]["dir"])
                add(kind, start, end, cid, None, CamKey(k.cx, k.cy, k.view_w * 1.05), CamKey(k.cx, k.cy, k.view_w * 0.92),
                    1.3, dof=3.0, beats=[tb.id], desc=b.get("description", ""))
            elif cam_req == "wide":
                add("wide", start, end, None, None, CamKey(wide.cx - 150, wide.cy, wide.view_w * 0.85),
                    CamKey(wide.cx + 150, wide.cy, wide.view_w * 0.8), 0.8, beats=[tb.id])
            else:
                add("two", start, end, None, None, CamKey(two.cx - 60, two.cy, two.view_w * 1.05),
                    CamKey(two.cx + 60, two.cy, two.view_w * 0.95), 1.4, beats=[tb.id], desc=b.get("description", ""))
            continue
        spk = b["speaker"]
        other = next((c for c in blocking if c != spk), None)
        sx = blocking[spk]["x"]
        sdir = blocking[spk]["dir"]
        h = heights[spk]
        if cam_req in ("cu", "mcu", "ots", "two", "wide"):
            kind = cam_req
        else:
            # vary shot sizes
            emotion = b.get("emotion", "neutral")
            if emotion in ("surprised", "scared", "worried", "sad") and rng.random() < 0.8:
                kind = "cu"
            elif other and last_speaker and last_speaker != spk and alt % 3 == 1:
                kind = "ots"
            else:
                kind = ["mcu", "cu", "mcu", "two"][alt % 4]
        alt += 1
        if kind == "two":
            a = CamKey(two.cx, two.cy, two.view_w)
            bkey = CamKey(two.cx + sdir * 40, two.cy + 10, two.view_w * 0.9)
            add("two", start, end, spk, other, a, bkey, 1.4, beats=[tb.id])
        elif kind == "wide":
            add("wide", start, end, spk, other, CamKey(wide.cx, wide.cy, wide.view_w * 0.8),
                CamKey(wide.cx, wide.cy, wide.view_w * 0.72), 0.8, beats=[tb.id])
        elif kind == "ots" and other:
            # frame the speaker past the listener's shoulder
            ox = blocking[other]["x"]
            k = _char_frame(sx, h, "mcu", sdir)
            cx = sx * 0.62 + ox * 0.38
            a = CamKey(cx, k.cy + 20, k.view_w * 1.45)
            bkey = CamKey(cx + (sx - cx) * 0.15, k.cy + 10, k.view_w * 1.3)
            add("ots", start, end, spk, other, a, bkey, 1.6, dof=2.5, beats=[tb.id])
        else:
            k = _char_frame(sx, h, kind, sdir)
            push = 0.9 if kind == "mcu" else 0.93
            a = CamKey(k.cx, k.cy, k.view_w * 1.06)
            bkey = CamKey(k.cx, k.cy, k.view_w * push)
            add(kind, start, end, spk, other, a, bkey, 1.8 if kind == "cu" else 1.5, dof=4.0 if kind == "cu" else 2.5,
                beats=[tb.id])
        last_speaker = spk

    # closing wide
    if shots[-1].end < duration:
        s = shots[-1].end
        two = two_at(duration)
        add("two", s, duration, None, None, CamKey(two.cx, two.cy, two.view_w * 0.95),
            CamKey(two.cx, two.cy - 120, two.view_w * 1.3), 0.8, desc="closing pull-back")
    # merge tiny shots into the previous one
    merged: list[Shot] = []
    for sh in shots:
        if merged and sh.end - sh.start < 0.6:
            merged[-1].end = sh.end
            merged[-1].beat_ids += sh.beat_ids
        else:
            merged.append(sh)
    for i, sh in enumerate(merged):
        sh.index = i + index_offset
    merged[-1].end = duration
    return merged
