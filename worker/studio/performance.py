"""Turns timed beats into per-frame character performance + environment state."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from .lipsync import viseme_at
from .rig import EXPRESSIONS, POSES, RigState, blend_dict
from .storyboard import TimedBeat

BLEND = 0.35


@dataclass
class Track:
    keys: list[tuple[float, Any]] = field(default_factory=list)

    def add(self, t: float, v: Any):
        self.keys.append((t, v))
        self.keys.sort(key=lambda k: k[0])

    def at(self, t: float):
        """Return (prev_value, cur_value, blend 0..1)."""
        if not self.keys:
            return None, None, 1.0
        prev, cur, t0 = self.keys[0][1], self.keys[0][1], self.keys[0][0]
        for kt, v in self.keys:
            if kt <= t:
                prev, cur, t0 = cur, v, kt
            else:
                break
        return prev, cur, min(1.0, max(0.0, (t - t0) / BLEND))


@dataclass
class CharTracks:
    pose: Track = field(default_factory=Track)
    expr: Track = field(default_factory=Track)
    look: Track = field(default_factory=Track)    # target char id / object / None
    prop: Track = field(default_factory=Track)
    glow: Track = field(default_factory=Track)
    moves: list[tuple[float, float, float, float]] = field(default_factory=list)  # t0,t1,x0,x1
    turns: Track = field(default_factory=Track)
    lines: list[tuple[float, float, list[dict], str]] = field(default_factory=list)  # start,end,cues,text


class Performance:
    def __init__(self, timed: list[TimedBeat], blocking: dict[str, dict], spots: dict[str, float],
                 objects: dict[str, tuple[float, float, float]], seed: str = "perf", env0: dict | None = None):
        self.blocking = {k: dict(v) for k, v in blocking.items()}
        self.objects = objects
        self.spots = spots
        self.rng = random.Random(seed)
        self.chars = {cid: CharTracks() for cid in blocking}
        self.env: dict[str, Track] = {"lamp": Track(), "boat_signal": Track(), "rain": Track(), "fireflies": Track(),
                                      "room_lamp": Track()}
        env0 = env0 or {}
        for k in self.env:
            self.env[k].add(0.0, env0.get(k, 1.0 if k == "room_lamp" else 0.0))
        for cid, ct in self.chars.items():
            b = blocking[cid]
            ct.pose.add(0.0, b.get("pose", "idle"))
            ct.expr.add(0.0, b.get("expression", "neutral"))
            ct.look.add(0.0, b.get("look"))
            ct.prop.add(0.0, b.get("prop"))
            ct.glow.add(0.0, b.get("glow", 0.0))
            ct.turns.add(0.0, b.get("turn", 0.45 * b.get("dir", 1)))
        self.blinks = {cid: self._blink_times(cid) for cid in blocking}
        self._init_x = {cid: float(blocking[cid]["x"]) for cid in blocking}
        self._build(timed)
        self._final_x = {cid: self.blocking[cid]["x"] for cid in self.blocking}
        self._auto_facing(timed)

    def _blink_times(self, cid: str) -> list[float]:
        r = random.Random(cid)
        t, out = r.uniform(0.3, 2.0), []
        while t < 600:
            out.append(t)
            t += r.uniform(1.8, 4.8)
            if r.random() < 0.15:
                out.append(t + 0.25)  # double blink
        return out

    def _x_of(self, target) -> float:
        if isinstance(target, (int, float)):
            return float(target)
        if target in self.spots:
            return float(self.spots[target])
        if target in self.blocking:
            return float(self.blocking[target]["x"])
        if target in self.objects:
            return float(self.objects[target][0])
        return 1600.0

    def _build(self, timed: list[TimedBeat]):
        for tb in timed:
            b = tb.data
            t0, t1 = tb.start, tb.end
            for cid, pose in (b.get("poses") or {}).items():
                self.chars[cid].pose.add(t0, pose)
            for cid, ex in (b.get("expressions") or {}).items():
                self.chars[cid].expr.add(t0, ex)
            for cid, tgt in (b.get("looks") or {}).items():
                self.chars[cid].look.add(t0, tgt)
            for cid, prop in (b.get("props") or {}).items():
                self.chars[cid].prop.add(t0, prop)
            for cid, g in (b.get("glow") or {}).items():
                self.chars[cid].glow.add(t0, g)
            for cid, mv in (b.get("moves") or {}).items():
                x0 = self.blocking[cid]["x"]
                x1 = self._x_of(mv)
                dur = max(0.6, min(t1 - t0, abs(x1 - x0) / 260.0))
                self.chars[cid].moves.append((t0, t0 + dur, x0, x1))
                d = 1 if x1 > x0 else -1
                self.chars[cid].turns.add(t0, 0.85 * d)
                self.chars[cid].turns.add(t0 + dur, self.blocking[cid].get("turn", 0.45 * self.blocking[cid]["dir"]))
                self.blocking[cid]["x"] = x1
            for k, v in (b.get("events") or {}).items():
                if k in self.env:
                    self.env[k].add(t0, v)
            if tb.type == "line":
                spk = b["speaker"]
                ct = self.chars[spk]
                ct.lines.append((t0, t1, tb.cues, b.get("text", "")))
                ct.expr.add(t0, b.get("emotion", "neutral"))
                if b.get("look_at"):
                    ct.look.add(t0, b["look_at"])
                else:
                    other = next((c for c in self.chars if c != spk), None)
                    ct.look.add(t0, other)
                act = b.get("action")
                # gesture schedule
                t = t0
                if act:
                    ct.pose.add(t, act)
                    t += min(1.8, (t1 - t0) * 0.6)
                cycle = ["talk_a", "talk_b", "talk_open", "talk_a"]
                i = self.rng.randrange(4)
                while t < t1 - 0.6:
                    ct.pose.add(t, cycle[i % 4])
                    t += self.rng.uniform(1.1, 1.7)
                    i += 1
                ct.pose.add(t1, b.get("end_pose", "idle"))
                for lid, ld in self.chars.items():
                    if lid == spk:
                        continue
                    ld.look.add(t0 + 0.15, spk)
                    if b.get("reaction"):
                        ld.expr.add(t0 + 0.3, b["reaction"])
                    if b.get("reaction_pose"):
                        ld.pose.add(t0 + 0.3, b["reaction_pose"])

    def _auto_facing(self, timed: list[TimedBeat]):
        """Characters face what they look at (default: the other character)."""
        moving = lambda cid, t: any(t0 <= t <= t1 for (t0, t1, _, _) in self.chars[cid].moves)  # noqa: E731
        for tb in timed:
            for cid, ct in self.chars.items():
                t = tb.start + 0.05
                if moving(cid, t):
                    continue
                _, tgt, _ = ct.look.at(t + 0.2)
                x = self.char_x(cid, t)[0]
                if tgt in self.chars and tgt != cid:
                    tx = self.char_x(tgt, t)[0]
                elif tgt in self.objects:
                    tx = self.objects[tgt][0]
                else:
                    others = [c for c in self.chars if c != cid]
                    tx = self.char_x(others[0], t)[0] if others else x + 1
                d = 1 if tx >= x else -1
                ct.turns.add(t, 0.45 * d)
                self.blocking[cid]["dir"] = d

    # ---------------------------------------------------------------- query
    def char_x(self, cid: str, t: float) -> tuple[float, float | None]:
        ct = self.chars[cid]
        x = None
        for (t0, t1, x0, x1) in ct.moves:
            if t < t0:
                if x is None:
                    x = x0
                break
            if t0 <= t <= t1:
                u = (t - t0) / (t1 - t0)
                return x0 + (x1 - x0) * u, ((t - t0) * 1.6) % 1.0
            x = x1
        if x is None:
            x = ct.moves[0][2] if ct.moves else self._initial_x(cid)
        return x, None

    def _initial_x(self, cid):
        return self._init_x[cid]

    def state(self, cid: str, t: float, anchors: dict[str, tuple[float, float]], beam: float = 0.0,
              rim_color: str = "#ffd28a") -> tuple[RigState, float, int, bool]:
        ct = self.chars[cid]
        x, walk = self.char_x(cid, t)
        p0, p1, k = ct.pose.at(t)
        pose = blend_dict(POSES.get(p0, POSES["idle"]), POSES.get(p1, POSES["idle"]), k)
        e0, e1, ke = ct.expr.at(t)
        expr = blend_dict(EXPRESSIONS.get(e0, EXPRESSIONS["neutral"]), EXPRESSIONS.get(e1, EXPRESSIONS["neutral"]), ke)
        tp, tc, kt = ct.turns.at(t)
        turn_v = float(tp) * (1 - kt) + float(tc) * kt
        # speaking
        vis = "X"
        speaking = False
        energy = 0.0
        for (s, e, cues, _text) in ct.lines:
            if s <= t < e:
                vis = viseme_at(cues, t - s)
                speaking = True
                energy = {"D": 1.0, "C": 0.7, "E": 0.6, "H": 0.6, "B": 0.4, "F": 0.4, "G": 0.3}.get(vis, 0.0)
                break
        # look target -> pupils + head turn
        _, tgt, _ = ct.look.at(t)
        look = (0.0, 0.0)
        head_turn = 0.0
        if tgt and tgt in anchors and tgt != cid:
            hx, hy = anchors[tgt]
            mx = anchors.get(cid, (x, 0))[0]
            dx = hx - mx
            look = (max(-1, min(1, dx / 500.0)) * 0.8, max(-1, min(1, (hy - anchors.get(cid, (0, hy))[1]) / 600.0)))
            want = 1 if dx > 0 else -1
            if (turn_v > 0) != (want > 0):
                head_turn = want * 0.25
        elif tgt in self.objects:
            ox, oy, _ = self.objects[tgt]
            dx = ox - x
            look = (max(-1, min(1, dx / 600.0)), -0.6 if oy < 900 else 0.2)
        # micro saccades
        look = (look[0] + 0.08 * math.sin(t * 1.7 + hash(cid) % 7), look[1] + 0.05 * math.sin(t * 1.3))
        blink = 0.0
        for bt in self.blinks[cid]:
            if bt <= t < bt + 0.16:
                blink = math.sin((t - bt) / 0.16 * math.pi)
                break
            if bt > t:
                break
        _, prop, _ = ct.prop.at(t)
        g0, g1, kg = ct.glow.at(t)
        glow = (g0 or 0.0) * (1 - kg) + (g1 or 0.0) * kg
        glow *= 0.85 + 0.15 * math.sin(t * 6)
        breathe = math.sin(t * 2 * math.pi / 3.6 + hash(cid) % 5)
        nod = energy * 2.5 * math.sin(t * 9) if speaking else 0.0
        st = RigState(pose=pose, expr=expr, viseme=vis, turn=max(-1, min(1, turn_v)), head_turn=head_turn,
                      look=look, blink=blink, breathe=breathe, head_tilt=nod, walk_phase=walk, prop=prop,
                      prop_glow=glow, light=beam, rim_color=rim_color)
        d = 1 if turn_v >= 0 else -1
        return st, x, d, speaking

    def env_at(self, key: str, t: float) -> float:
        a, b, k = self.env[key].at(t)

        def val(v, tt):
            if v == "flicker":
                r = math.sin(tt * 37) * math.sin(tt * 13.3) + math.sin(tt * 5.1)
                return 1.0 if r > 0.3 else 0.08
            if v == "blink":   # morse-ish pattern
                ph = (tt * 2.2) % 4.0
                return 1.0 if (ph < 0.3 or 0.6 < ph < 0.9 or 1.2 < ph < 2.0) else 0.0
            return float(v or 0.0)
        va, vb = val(a, t), val(b, t)
        if b in ("flicker", "blink"):
            return vb
        return va * (1 - k) + vb * k
