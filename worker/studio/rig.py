"""Procedural 2D cartoon character rig rendered with Skia.

A character is fully described by its persistent *design* (stored in the
Character record) and is drawn from a *RigState* each frame:

* skeleton: hip -> spine -> neck -> head, shoulders -> upper arm -> forearm -> hand,
  hips -> thigh -> shin -> foot.  Angles are in degrees, "forward positive"
  (positive rotates a limb toward the direction the character faces).
* turn:  -1 (profile facing left) .. 0 (front) .. +1 (profile facing right)
* back:  draw from behind (no face) - used for over-the-shoulder shots
* expression: brows / lids / smile / look direction
* viseme: Rhubarb mouth shape A-H or X

Because the design never changes between episodes, the same Character ID always
renders identically (face, hair, proportions, outfit) - this is the core of the
continuity system for the economic engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import skia

# --------------------------------------------------------------------------- utils


def col(hex_str: str, alpha: float = 1.0) -> int:
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return skia.Color(r, g, b, int(max(0, min(1, alpha)) * 255))


def shade(hex_str: str, k: float) -> str:
    """k<1 darker, k>1 lighter."""
    h = hex_str.lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    if k <= 1:
        rgb = [int(c * k) for c in rgb]
    else:
        rgb = [int(c + (255 - c) * (k - 1)) for c in rgb]
    return "#" + "".join(f"{max(0, min(255, c)):02x}" for c in rgb)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def fill(c: int) -> skia.Paint:
    return skia.Paint(AntiAlias=True, Color=c, Style=skia.Paint.kFill_Style)


def stroke(c: int, w: float, cap=skia.Paint.kRound_Cap) -> skia.Paint:
    return skia.Paint(AntiAlias=True, Color=c, Style=skia.Paint.kStroke_Style,
                      StrokeWidth=w, StrokeCap=cap, StrokeJoin=skia.Paint.kRound_Join)


def vec(angle_deg: float, length: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return math.sin(a) * length, math.cos(a) * length


# --------------------------------------------------------------------------- poses
# forward-positive angles.  *_u = upper limb absolute (0 = down), *_l = lower limb
# relative to upper.  near = arm/leg on the camera side when turned.
POSES: dict[str, dict[str, float]] = {
    "idle":      dict(lean=0, nu=-6, nl=8, fu=6, fl=10, nt=0, ns=0, ft=0, fs=0, head=0),
    "talk_a":    dict(lean=2, nu=18, nl=55, fu=4, fl=12, nt=0, ns=0, ft=0, fs=0, head=3),
    "talk_b":    dict(lean=1, nu=-4, nl=14, fu=30, fl=70, nt=0, ns=0, ft=0, fs=0, head=-2),
    "talk_open": dict(lean=0, nu=28, nl=40, fu=26, fl=45, nt=0, ns=0, ft=0, fs=0, head=0),
    "point":     dict(lean=4, nu=82, nl=4, fu=4, fl=10, nt=0, ns=0, ft=0, fs=0, head=4),
    "point_up":  dict(lean=-4, nu=118, nl=22, fu=4, fl=10, nt=0, ns=0, ft=0, fs=0, head=-14),
    "surprised": dict(lean=-6, nu=35, nl=70, fu=35, fl=70, nt=0, ns=0, ft=0, fs=0, head=-6),
    "think":     dict(lean=2, nu=20, nl=135, fu=12, fl=95, nt=0, ns=0, ft=0, fs=0, head=8),
    "wave":      dict(lean=0, nu=140, nl=-30, fu=5, fl=10, nt=0, ns=0, ft=0, fs=0, head=-4),
    "shrug":     dict(lean=0, nu=40, nl=-80, fu=40, fl=-80, nt=0, ns=0, ft=0, fs=0, head=6),
    "hold":      dict(lean=6, nu=30, nl=70, fu=24, fl=80, nt=0, ns=0, ft=0, fs=0, head=10),
    "crouch":    dict(lean=18, nu=30, nl=50, fu=20, fl=60, nt=50, ns=-80, ft=40, fs=-70, head=10, drop=0.12),
    "hands_hips": dict(lean=0, nu=-35, nl=-95, fu=35, fl=95, nt=0, ns=0, ft=0, fs=0, head=0),
    "excited":   dict(lean=-2, nu=120, nl=30, fu=120, fl=30, nt=0, ns=0, ft=0, fs=0, head=-8),
    "lookout":   dict(lean=3, nu=125, nl=100, fu=4, fl=10, nt=0, ns=0, ft=0, fs=0, head=-6),
}

EXPRESSIONS: dict[str, dict[str, float]] = {
    # brow_y (+up), brow_tilt (+ = inner up/worried, - = angry), lid (1 open), smile (-1..1)
    "neutral":    dict(brow_y=0.0, brow_tilt=0.0, lid=1.0, smile=0.15, blush=0.0, pupil=1.0),
    "happy":      dict(brow_y=0.15, brow_tilt=0.1, lid=0.85, smile=0.9, blush=0.5, pupil=1.0),
    "laugh":      dict(brow_y=0.25, brow_tilt=0.2, lid=0.35, smile=1.0, blush=0.7, pupil=1.0),
    "sad":        dict(brow_y=0.05, brow_tilt=0.8, lid=0.7, smile=-0.7, blush=0.0, pupil=1.0),
    "surprised":  dict(brow_y=0.6, brow_tilt=0.1, lid=1.25, smile=0.0, blush=0.0, pupil=0.75),
    "angry":      dict(brow_y=-0.25, brow_tilt=-0.9, lid=0.8, smile=-0.5, blush=0.2, pupil=1.0),
    "worried":    dict(brow_y=0.2, brow_tilt=0.9, lid=0.95, smile=-0.35, blush=0.0, pupil=1.0),
    "thinking":   dict(brow_y=0.1, brow_tilt=-0.3, lid=0.75, smile=-0.1, blush=0.0, pupil=1.0),
    "determined": dict(brow_y=-0.1, brow_tilt=-0.5, lid=0.85, smile=0.35, blush=0.0, pupil=1.0),
    "scared":     dict(brow_y=0.5, brow_tilt=1.0, lid=1.2, smile=-0.6, blush=0.0, pupil=0.6),
    "curious":    dict(brow_y=0.35, brow_tilt=-0.2, lid=1.05, smile=0.3, blush=0.1, pupil=1.1),
}

VISEMES = ["A", "B", "C", "D", "E", "F", "G", "H", "X"]


def blend_dict(a: dict[str, float], b: dict[str, float], t: float) -> dict[str, float]:
    keys = set(a) | set(b)
    return {k: lerp(a.get(k, 0.0), b.get(k, 0.0), t) for k in keys}


@dataclass
class RigState:
    pose: dict[str, float] = field(default_factory=lambda: dict(POSES["idle"]))
    expr: dict[str, float] = field(default_factory=lambda: dict(EXPRESSIONS["neutral"]))
    viseme: str = "X"
    turn: float = 0.4          # -1..1
    head_turn: float = 0.0     # added to turn for the head only
    back: bool = False
    look: tuple[float, float] = (0.0, 0.0)  # pupil offset -1..1
    blink: float = 0.0         # 0 open .. 1 closed
    breathe: float = 0.0       # -1..1
    head_tilt: float = 0.0     # extra degrees
    walk_phase: float | None = None
    prop: str | None = None    # e.g. "shell"
    prop_glow: float = 0.0
    light: float = 0.0         # extra flash from lighthouse beam (0..1)
    rim_color: str = "#ffd28a"
    rim: float = 0.35


# --------------------------------------------------------------------------- rig


class CharacterRig:
    """Draws one character design.  Local origin = between the feet, y down."""

    def __init__(self, design: dict[str, Any]):
        self.d = design
        self.H = 900.0 * float(design.get("height", 1.0))
        hr = float(design.get("head_ratio", 0.22))
        self.head_h = self.H * hr
        self.head_ry = self.head_h / 2
        self.head_rx = self.head_ry * float(design.get("head_width", 0.92))
        self.neck = self.H * 0.025
        self.torso = self.H * float(design.get("torso_ratio", 0.30))
        self.leg = self.H - self.head_h - self.neck - self.torso
        build = float(design.get("build", 1.0))
        self.sw = self.H * 0.19 * build          # shoulder width
        self.hw = self.H * 0.12 * build          # hip width
        self.arm_u = self.H * 0.165
        self.arm_l = self.H * 0.15
        self.arm_w = self.H * 0.058 * build
        self.leg_w = self.H * 0.072 * build
        self.hand_r = self.H * 0.036
        self.outline = col(design.get("outline", "#2a1d1a"))
        self.ow = max(3.0, self.H * 0.0085)

    # -- public ---------------------------------------------------------------
    def draw(self, c: skia.Canvas, st: RigState, x: float, y: float, scale: float = 1.0,
             dir_: int = 1) -> dict[str, tuple[float, float]]:
        """Draw at stage position (x, y=feet).  Returns anchor points (stage coords)."""
        c.save()
        c.translate(x, y)
        c.scale(scale, scale)
        anchors = self._draw_local(c, st, dir_)
        c.restore()
        return {k: (x + v[0] * scale, y + v[1] * scale) for k, v in anchors.items()}

    # -- internals ------------------------------------------------------------
    def _draw_local(self, c: skia.Canvas, st: RigState, dir_: int):
        d = self.d
        p = dict(st.pose)
        t = max(-1.0, min(1.0, st.turn))
        at = abs(t)
        f = 1 if t >= 0 else -1          # facing sign on screen
        if at < 0.05:
            f = dir_
        self._facing_hint = f
        comp = math.cos(at * math.pi / 2) * 0.85 + 0.15   # width compression in profile
        splay = 10 * (1 - at)

        # walk cycle overrides legs/arms
        bob = 0.0
        if st.walk_phase is not None:
            ph = st.walk_phase * 2 * math.pi
            p["nt"] = 26 * math.sin(ph)
            p["ft"] = -26 * math.sin(ph)
            p["ns"] = -30 * max(0.0, math.sin(ph + math.pi / 2))
            p["fs"] = -30 * max(0.0, math.sin(ph - math.pi / 2))
            p["nu"] = -20 * math.sin(ph)
            p["fu"] = 20 * math.sin(ph)
            p["nl"], p["fl"] = 20, 20
            bob = abs(math.sin(ph)) * self.H * 0.015

        drop = p.get("drop", 0.0) * self.H
        breathe = st.breathe * self.H * 0.004
        hip = (0.0, -self.leg + drop + bob * -1)
        lean = p.get("lean", 0.0) * f
        thigh = self.leg * 0.5
        shin = self.leg * 0.5 - self.H * 0.022

        # torso frame: rotate around hip
        def torso_pt(lx: float, ly: float) -> tuple[float, float]:
            a = math.radians(lean)
            ca, sa = math.cos(a), math.sin(a)
            # ly negative = up
            return hip[0] + lx * ca - ly * sa, hip[1] + lx * sa + ly * ca

        chest_top = -self.torso - breathe
        sh_y = chest_top + self.torso * 0.06
        near_x = -f * self.sw / 2 * comp
        far_x = f * self.sw / 2 * comp
        if at < 0.05:
            near_x, far_x = -self.sw / 2, self.sw / 2
        sh_near = torso_pt(near_x, sh_y)
        sh_far = torso_pt(far_x, sh_y)
        neck_base = torso_pt(0, chest_top)

        # legs
        hip_near = (hip[0] - f * self.hw / 2 * comp * 0.8, hip[1])
        hip_far = (hip[0] + f * self.hw / 2 * comp * 0.8, hip[1])
        legs = []
        for hp, tk, sk, side in ((hip_far, "ft", "fs", "far"), (hip_near, "nt", "ns", "near")):
            sp = (-splay * 0.25 if side == "near" else splay * 0.25) if at < 0.6 else 0
            a1 = p.get(tk, 0.0) * f + (sp if f > 0 else -sp)
            kv = vec(a1, thigh)
            knee = (hp[0] + kv[0], hp[1] + kv[1])
            a2 = a1 + p.get(sk, 0.0) * f
            av = vec(a2, shin)
            ankle = (knee[0] + av[0], knee[1] + av[1])
            legs.append((side, hp, knee, ankle))

        # arms (angles screen space)
        arms = []
        for spt, uk, lk, side in ((sh_far, "fu", "fl", "far"), (sh_near, "nu", "nl", "near")):
            base_splay = -splay if side == "near" else splay
            if at < 0.05:
                # front view: near arm on screen-left, mirrored angles
                sign = -1 if side == "near" else 1
                a1 = p.get(uk, 0.0) * sign + (splay if side == "far" else -splay)
                a2 = a1 + p.get(lk, 0.0) * sign
            else:
                a1 = p.get(uk, 0.0) * f + base_splay * (1 if f > 0 else -1) * 0.5 + lean
                a2 = a1 + p.get(lk, 0.0) * f
            ev = vec(a1, self.arm_u)
            elbow = (spt[0] + ev[0], spt[1] + ev[1])
            hv = vec(a2, self.arm_l)
            hand = (elbow[0] + hv[0], elbow[1] + hv[1])
            arms.append((side, spt, elbow, hand))

        head_c_local = (0.0, chest_top - self.neck - self.head_ry * 0.92)
        head_c = torso_pt(*head_c_local)
        head_angle = lean + (p.get("head", 0.0) + st.head_tilt) * f

        back = st.back
        # ---- draw order
        if not back:
            self._draw_arm(c, arms[0], far=True)
            self._draw_leg(c, legs[0], far=True)
            self._draw_leg(c, legs[1], far=False)
            self._draw_torso(c, torso_pt, chest_top, comp, f, at, st)
            self._draw_neck(c, neck_base, head_c)
            self._draw_head(c, head_c, head_angle, t + st.head_turn, st)
            self._draw_arm(c, arms[1], far=False, st=st)
        else:
            self._draw_leg(c, legs[0], far=True)
            self._draw_leg(c, legs[1], far=False)
            self._draw_arm(c, arms[1], far=True)
            self._draw_torso(c, torso_pt, chest_top, comp, f, at, st, back=True)
            self._draw_neck(c, neck_base, head_c)
            self._draw_head_back(c, head_c, head_angle)
            self._draw_arm(c, arms[0], far=False)

        hand_near = arms[1][3]
        return {"head": head_c, "hand": hand_near, "hip": hip,
                "mouth": (head_c[0] + (t + st.head_turn) * self.head_rx * 0.45,
                          head_c[1] + self.head_ry * 0.45),
                "top": (head_c[0], head_c[1] - self.head_ry * 1.2)}

    # ------------------------------------------------------------- body parts
    def _limb(self, c, pts, w, color, far: bool):
        path = skia.Path()
        path.moveTo(*pts[0])
        for q in pts[1:]:
            path.lineTo(*q)
        c.drawPath(path, stroke(self.outline, w + self.ow * 2))
        c.drawPath(path, stroke(col(shade(color, 0.8 if far else 1.0)), w))

    def _draw_leg(self, c, leg, far: bool):
        _, hp, knee, ankle = leg
        o = self.d["outfit"]
        pants = o.get("bottom_color", "#2e4a7a")
        skin = self.d["skin"]
        btype = o.get("bottom", "pants")
        if btype == "shorts":
            mid = (lerp(hp[0], knee[0], 0.75), lerp(hp[1], knee[1], 0.75))
            self._limb(c, [hp, knee, ankle], self.leg_w * 0.8, skin, far)
            self._limb(c, [hp, mid], self.leg_w * 1.12, pants, far)
        else:
            self._limb(c, [hp, knee, ankle], self.leg_w, pants, far)
        # boot
        shoe = o.get("shoes", "#4a3226")
        boot_h = self.H * 0.06
        f = 1 if self._facing_hint >= 0 else -1
        r = skia.RRect.MakeRectXY(
            skia.Rect.MakeXYWH(ankle[0] - self.leg_w * 0.62 - (self.leg_w * 0.25 if f < 0 else 0),
                               ankle[1] - boot_h * 0.62,
                               self.leg_w * 1.5, boot_h * 1.05), boot_h * 0.4, boot_h * 0.4)
        c.drawRRect(r, stroke(self.outline, self.ow * 2))
        c.drawRRect(r, fill(col(shade(shoe, 0.8 if far else 1.0))))

    _facing_hint = 1.0

    def _draw_arm(self, c, arm, far: bool, st: RigState | None = None):
        _, sh, el, hd = arm
        o = self.d["outfit"]
        sleeve = o.get("top_color", "#f2c230")
        skin = self.d["skin"]
        long_sleeve = o.get("sleeves", "long") == "long"
        if long_sleeve:
            wrist = (lerp(el[0], hd[0], 0.82), lerp(el[1], hd[1], 0.82))
            self._limb(c, [sh, el, wrist], self.arm_w, sleeve, far)
        else:
            self._limb(c, [el, hd], self.arm_w * 0.8, skin, far)
            self._limb(c, [sh, el], self.arm_w, sleeve, far)
        # hand
        sk = col(shade(skin, 0.85 if far else 1.0))
        c.drawCircle(hd[0], hd[1], self.hand_r + self.ow, fill(self.outline))
        c.drawCircle(hd[0], hd[1], self.hand_r, fill(sk))
        if st is not None and st.prop and not far:
            self._draw_prop(c, st.prop, hd, st)

    def _draw_prop(self, c, prop: str, at: tuple[float, float], st: RigState):
        x, y = at
        if prop == "shell":
            g = st.prop_glow
            if g > 0:
                rad = self.H * (0.09 + 0.05 * g)
                shader = skia.GradientShader.MakeRadial(
                    (x, y - self.hand_r), rad,
                    [col("#9ff6ff", 0.75 * g), col("#56c8ff", 0.25 * g), col("#56c8ff", 0.0)],
                    [0.0, 0.45, 1.0])
                c.drawCircle(x, y - self.hand_r, rad, skia.Paint(AntiAlias=True, Shader=shader))
            s = self.H * 0.045
            path = skia.Path()
            path.moveTo(x - s, y)
            path.cubicTo(x - s, y - s * 1.6, x + s, y - s * 1.6, x + s, y)
            path.close()
            c.drawPath(path, stroke(self.outline, self.ow * 2))
            c.drawPath(path, fill(col("#f5d9e8") if g < 0.5 else col("#c9fbff")))
            for i in range(-2, 3):
                c.drawLine(x, y - s * 0.1, x + i * s * 0.38, y - s * 1.05,
                           stroke(col("#c98fae"), self.ow * 0.6))
        elif prop == "lantern":
            s = self.H * 0.05
            c.drawLine(x, y, x, y + s * 0.6, stroke(self.outline, self.ow))
            r = skia.Rect.MakeXYWH(x - s * 0.5, y + s * 0.6, s, s * 1.3)
            if st.prop_glow > 0:
                sh = skia.GradientShader.MakeRadial((x, y + s * 1.2), s * 4,
                                                    [col("#ffcc66", 0.5 * st.prop_glow), col("#ffcc66", 0)])
                c.drawCircle(x, y + s * 1.2, s * 4, skia.Paint(AntiAlias=True, Shader=sh))
            c.drawRect(r, fill(col("#ffe8a0")))
            c.drawRect(r, stroke(self.outline, self.ow))

    def _draw_neck(self, c, base, head_c):
        top = (lerp(base[0], head_c[0], 0.6), lerp(base[1], head_c[1], 0.6))
        w = self.head_rx * 0.42
        c.drawLine(base[0], base[1] + w * 0.3, top[0], top[1], stroke(self.outline, w + self.ow * 2))
        c.drawLine(base[0], base[1] + w * 0.3, top[0], top[1], stroke(col(shade(self.d["skin"], 0.85)), w))

    def _draw_torso(self, c, tp, chest_top, comp, f, at, st: RigState, back=False):
        o = self.d["outfit"]
        top_c = o.get("top_color", "#f2c230")
        sw = self.sw * comp * 0.5 + self.sw * 0.08
        hw = self.hw * comp * 0.5 + self.hw * 0.25
        hem = self.torso * float(o.get("hem", 0.12))
        flare = float(o.get("flare", 1.15))
        pts = [tp(-sw, chest_top + self.torso * 0.04), tp(sw, chest_top + self.torso * 0.04),
               tp(hw * flare, hem), tp(-hw * flare, hem)]
        path = skia.Path()
        r = self.torso * 0.12
        path.moveTo(*tp(-sw + r, chest_top))
        path.lineTo(*tp(sw - r, chest_top))
        path.quadTo(*tp(sw, chest_top), *pts[1])
        path.lineTo(*pts[2])
        path.quadTo(*tp(0, hem + self.torso * 0.03), *pts[3])
        path.lineTo(*pts[0])
        path.quadTo(*tp(-sw, chest_top), *tp(-sw + r, chest_top))
        path.close()
        c.drawPath(path, stroke(self.outline, self.ow * 2))
        # gradient shading - light from the key side
        a = tp(-sw, 0)
        b = tp(sw, 0)
        shader = skia.GradientShader.MakeLinear(
            [a, b], [col(shade(top_c, 1.12)), col(top_c), col(shade(top_c, 0.78))], [0.0, 0.5, 1.0])
        c.drawPath(path, skia.Paint(AntiAlias=True, Shader=shader))
        # details
        typ = o.get("top", "raincoat")
        lw = self.ow * 0.8
        if not back:
            cx_off = f * at * sw * 0.35
            if typ == "raincoat":
                # zipper + pockets + collar
                c.drawLine(*tp(cx_off, chest_top + self.torso * 0.08), *tp(cx_off * 1.2, hem),
                           stroke(col(shade(top_c, 0.6)), lw))
                for side in (-1, 1):
                    px = cx_off + side * sw * 0.5
                    pr = skia.Rect.MakeLTRB(*tp(px - sw * 0.22, -self.torso * 0.28),
                                            *tp(px + sw * 0.22, -self.torso * 0.16))
                    c.drawRect(pr, stroke(col(shade(top_c, 0.6)), lw))
                for k in (0.25, 0.45, 0.65):
                    bx, by = tp(cx_off + sw * 0.12, chest_top + self.torso * k)
                    c.drawCircle(bx, by, self.ow * 0.9, fill(col(shade(top_c, 0.55))))
                collar = o.get("collar_color", shade(top_c, 0.85))
                cl = skia.Path()
                cl.moveTo(*tp(-sw * 0.7, chest_top + 2))
                cl.lineTo(*tp(cx_off, chest_top + self.torso * 0.16))
                cl.lineTo(*tp(sw * 0.7, chest_top + 2))
                c.drawPath(cl, stroke(self.outline, lw * 2))
                c.drawPath(cl, stroke(col(collar), lw * 1.4))
            elif typ == "sweater":
                # knit ribs + emblem
                for i in range(7):
                    k = i / 6
                    x0 = lerp(-sw * 0.9, sw * 0.9, k)
                    c.drawLine(*tp(x0, hem - self.torso * 0.08), *tp(x0, hem),
                               stroke(col(shade(top_c, 0.7)), lw * 0.8))
                neck_w = sw * 0.45
                nk = skia.Path()
                nk.moveTo(*tp(-neck_w + cx_off, chest_top + 1))
                nk.quadTo(*tp(cx_off, chest_top + self.torso * 0.12), *tp(neck_w + cx_off, chest_top + 1))
                c.drawPath(nk, stroke(col(shade(top_c, 0.65)), lw * 1.6))
                if o.get("emblem"):
                    ex, ey = tp(cx_off - f * sw * 0.45, chest_top + self.torso * 0.3)
                    self._anchor_emblem(c, ex, ey, self.torso * 0.07, o["emblem"])
            scarf = o.get("scarf")
            if scarf:
                sc = skia.Path()
                sc.moveTo(*tp(-sw * 0.75, chest_top + 3))
                sc.quadTo(*tp(cx_off, chest_top + self.torso * 0.2), *tp(sw * 0.75, chest_top + 3))
                c.drawPath(sc, stroke(self.outline, self.torso * 0.11 + self.ow * 2))
                c.drawPath(sc, stroke(col(scarf), self.torso * 0.11))
                tx, ty = tp(cx_off - f * sw * 0.3, chest_top + self.torso * 0.12)
                c.drawLine(tx, ty, tx - f * 6, ty + self.torso * 0.32, stroke(self.outline, self.torso * 0.09 + self.ow * 2))
                c.drawLine(tx, ty, tx - f * 6, ty + self.torso * 0.32, stroke(col(scarf), self.torso * 0.09))
        # rim light on the back side
        if st.rim > 0:
            rim = skia.Path()
            side = -f
            rim.moveTo(*tp(side * sw * 0.95, chest_top + self.torso * 0.1))
            rim.lineTo(*tp(side * hw * flare * 0.95, hem - 4))
            c.drawPath(rim, stroke(col(st.rim_color, st.rim * 0.8), self.ow * 1.6))

    def _anchor_emblem(self, c, x, y, s, color):
        p = stroke(col(color), s * 0.28)
        c.drawLine(x, y - s, x, y + s, p)
        c.drawLine(x - s * 0.6, y - s * 0.5, x + s * 0.6, y - s * 0.5, p)
        path = skia.Path()
        path.addArc(skia.Rect.MakeXYWH(x - s, y - s * 0.2, s * 2, s * 1.3), 10, 160)
        c.drawPath(path, p)

    # ----------------------------------------------------------------- head
    def _head_path(self, cx, cy):
        rx, ry = self.head_rx, self.head_ry
        p = skia.Path()
        jaw = float(self.d.get("jaw", 0.9))
        p.moveTo(cx, cy - ry)
        p.cubicTo(cx + rx * 1.1, cy - ry, cx + rx * 1.05, cy + ry * 0.35, cx + rx * 0.7 * jaw, cy + ry * 0.78)
        p.quadTo(cx, cy + ry * 1.12, cx - rx * 0.7 * jaw, cy + ry * 0.78)
        p.cubicTo(cx - rx * 1.05, cy + ry * 0.35, cx - rx * 1.1, cy - ry, cx, cy - ry)
        p.close()
        return p

    def _draw_head(self, c, hc, angle, turn, st: RigState):
        d = self.d
        t = max(-1.0, min(1.0, turn))
        at = abs(t)
        f = 1 if t >= 0 else -1
        cx, cy = hc
        rx, ry = self.head_rx, self.head_ry
        c.save()
        c.rotate(angle, cx, cy)
        hair = d.get("hair", {})
        hair_c = hair.get("color", "#c4472b")
        skin = d["skin"]
        # back hair
        self._draw_hair_back(c, cx, cy, hair, t)
        # ears (visible on the side opposite facing)
        ear_x = cx - f * rx * (0.98 - 0.55 * at) if at > 0.08 else None
        ears = [cx - rx * 0.98, cx + rx * 0.98] if ear_x is None else [ear_x]
        for ex in ears:
            r = skia.Rect.MakeXYWH(ex - rx * 0.16, cy - ry * 0.08, rx * 0.32, ry * 0.4)
            c.drawOval(r, fill(self.outline))
            c.drawOval(r.makeInset(self.ow * 0.8, self.ow * 0.8), fill(col(shade(skin, 0.9))))
        hp = self._head_path(cx, cy)
        c.drawPath(hp, stroke(self.outline, self.ow * 2))
        shader = skia.GradientShader.MakeRadial((cx + f * rx * 0.3, cy - ry * 0.25), rx * 1.6,
                                                [col(shade(skin, 1.06)), col(skin), col(shade(skin, 0.86))],
                                                [0.0, 0.6, 1.0])
        c.drawPath(hp, skia.Paint(AntiAlias=True, Shader=shader))
        # profile nose bump
        fx = cx + t * rx * 0.48
        fy = cy + ry * 0.05
        e = st.expr
        # cheeks / blush
        blush = e.get("blush", 0.0) + float(d.get("blush", 0.15))
        if blush > 0.02:
            for side in (-1, 1):
                if at > 0.8 and side == -f:
                    continue
                bx = fx + side * rx * 0.5 * (1 - 0.4 * at)
                c.drawOval(skia.Rect.MakeXYWH(bx - rx * 0.17, fy + ry * 0.22, rx * 0.34, ry * 0.16),
                           fill(col("#ff7a7a", min(0.45, blush * 0.4))))
        if d.get("freckles"):
            for side in (-1, 1):
                if at > 0.8 and side == -f:
                    continue
                bx = fx + side * rx * 0.45 * (1 - 0.4 * at)
                for i, (ox, oy) in enumerate(((-0.08, 0.2), (0.02, 0.26), (0.1, 0.2), (0.0, 0.16))):
                    c.drawCircle(bx + ox * rx, fy + oy * ry, rx * 0.022, fill(col(shade(skin, 0.62))))
        # eyes
        self._draw_eyes(c, fx, cy - ry * 0.05, t, st)
        # nose
        nose_c = col(shade(skin, 0.75))
        nx = cx + t * rx * 0.62
        ny = cy + ry * 0.2
        if at > 0.6:
            path = skia.Path()
            tip = nx + f * rx * 0.28 * at
            path.moveTo(nx, ny - ry * 0.18)
            path.quadTo(tip + f * rx * 0.05, ny + ry * 0.02, nx, ny + ry * 0.07)
            c.drawPath(path, fill(col(skin)))
            c.drawPath(path, stroke(self.outline, self.ow * 0.9))
        else:
            ns = float(d.get("nose", 1.0))
            c.drawOval(skia.Rect.MakeXYWH(nx - rx * 0.09 * ns, ny - ry * 0.04, rx * 0.18 * ns, ry * 0.12 * ns), fill(nose_c))
        # beard behind mouth
        if d.get("beard"):
            self._draw_beard(c, cx, cy, t, d["beard"])
        # mouth
        self._draw_mouth(c, cx + t * rx * 0.45, cy + ry * 0.47, t, st)
        if d.get("mustache"):
            mx = cx + t * rx * 0.5
            my = cy + ry * 0.34
            m = skia.Path()
            w = rx * 0.42 * (1 - 0.3 * at)
            m.moveTo(mx - w, my + ry * 0.06)
            m.quadTo(mx - w * 0.5, my - ry * 0.1, mx, my)
            m.quadTo(mx + w * 0.5, my - ry * 0.1, mx + w, my + ry * 0.06)
            m.quadTo(mx, my + ry * 0.1, mx - w, my + ry * 0.06)
            c.drawPath(m, fill(col(d["mustache"])))
            c.drawPath(m, stroke(self.outline, self.ow * 0.7))
        # brows
        self._draw_brows(c, fx, cy - ry * 0.32, t, st)
        # front hair
        self._draw_hair_front(c, cx, cy, hair, t)
        # glasses
        if d.get("glasses"):
            self._draw_glasses(c, fx, cy - ry * 0.05, t)
        # hat
        if d.get("hat"):
            self._draw_hat(c, cx, cy, t, d["hat"])
        # lighthouse beam flash
        if st.light > 0.01:
            c.drawPath(hp, fill(col("#fff4c8", st.light * 0.35)))
        c.restore()

    def _draw_head_back(self, c, hc, angle):
        d = self.d
        cx, cy = hc
        c.save()
        c.rotate(angle, cx, cy)
        hp = self._head_path(cx, cy)
        c.drawPath(hp, stroke(self.outline, self.ow * 2))
        c.drawPath(hp, fill(col(d["skin"])))
        hair = d.get("hair", {})
        style = hair.get("style", "curly_bob")
        hc_ = col(hair.get("color", "#c4472b"))
        rx, ry = self.head_rx, self.head_ry
        if style == "curly_bob":
            r = skia.Rect.MakeXYWH(cx - rx * 1.2, cy - ry * 1.12, rx * 2.4, ry * 1.95)
            c.drawOval(r, stroke(self.outline, self.ow * 2))
            c.drawOval(r, fill(hc_))
            for i in range(9):
                a = math.pi * (0.1 + 0.8 * i / 8)
                c.drawCircle(cx + math.cos(a) * rx * 1.1, cy + ry * 0.55 + math.sin(a) * ry * 0.25,
                             rx * 0.22, fill(hc_))
        else:
            c.save()
            c.clipPath(hp, doAntiAlias=True)
            r = skia.Rect.MakeXYWH(cx - rx * 1.3, cy - ry * 0.15, rx * 2.6, ry * 1.6)
            c.drawOval(r, fill(hc_))
            c.restore()
            c.drawPath(hp, stroke(self.outline, self.ow * 2))
        if d.get("hat"):
            self._draw_hat(c, cx, cy, 0.0, d["hat"])
        c.restore()

    def _draw_eyes(self, c, fx, ey, t, st: RigState):
        d = self.d
        at = abs(t)
        f = 1 if t >= 0 else -1
        rx, ry = self.head_rx, self.head_ry
        e = st.expr
        size = float(d.get("eye_size", 1.0))
        spacing = rx * 0.42 * (1 - 0.38 * at)
        ew = rx * 0.25 * size
        eh = ry * 0.24 * size * max(0.2, min(1.3, e.get("lid", 1.0)))
        openness = max(0.0, 1 - st.blink)
        iris_c = col(d.get("eye_color", "#3a8f5c"))
        for side in (-1, 1):
            far = side == -f and at > 0.05
            k = 1 - 0.45 * at if far else 1.0
            if far and at > 0.85:
                continue
            x = fx + side * spacing
            w = ew * k
            h = eh * openness
            if openness < 0.12:
                c.drawLine(x - w, ey + eh * 0.2, x + w, ey + eh * 0.2, stroke(self.outline, self.ow * 1.2))
                continue
            r = skia.Rect.MakeXYWH(x - w, ey - h, w * 2, h * 2)
            c.drawOval(r, fill(col("#ffffff")))
            c.save()
            c.clipRRect(skia.RRect.MakeOval(r), doAntiAlias=True)
            ix = x + (st.look[0] * 0.45 + t * 0.25) * w
            iy = ey + st.look[1] * 0.35 * h
            ir = min(w, eh) * 0.72 * e.get("pupil", 1.0) ** 0.3
            c.drawCircle(ix, iy, ir, fill(iris_c))
            c.drawCircle(ix, iy, ir * 0.55 * e.get("pupil", 1.0), fill(col("#1a1210")))
            c.drawCircle(ix - ir * 0.35, iy - ir * 0.38, ir * 0.28, fill(col("#ffffff", 0.95)))
            # upper lid (skin) for expressions like happy / determined
            lid = e.get("lid", 1.0)
            if lid < 0.95:
                lr = skia.Rect.MakeXYWH(x - w * 1.2, ey - h * 2.2, w * 2.4, h * (1.2 + (0.95 - lid) * 1.3))
                c.drawRect(lr, fill(col(d["skin"])))
            c.restore()
            c.drawOval(r, stroke(self.outline, self.ow * 1.05))
            # lashes
            if d.get("lashes"):
                c.drawLine(x + side * w * 0.8, ey - h * 0.6, x + side * w * 1.25, ey - h * 0.95,
                           stroke(self.outline, self.ow * 0.9))

    def _draw_brows(self, c, fx, by, t, st: RigState):
        d = self.d
        at = abs(t)
        f = 1 if t >= 0 else -1
        rx, ry = self.head_rx, self.head_ry
        e = st.expr
        spacing = rx * 0.42 * (1 - 0.38 * at)
        thick = ry * 0.07 * float(d.get("brow_thickness", 1.0))
        bc = col(d.get("brow_color", "#5a2a18"))
        lift = e.get("brow_y", 0.0) * ry * 0.18
        tilt = e.get("brow_tilt", 0.0)
        for side in (-1, 1):
            far = side == -f and at > 0.05
            if far and at > 0.85:
                continue
            k = 1 - 0.45 * at if far else 1.0
            x = fx + side * spacing
            w = rx * 0.24 * k
            inner = (x - side * w, by - lift - tilt * ry * 0.06)
            outer = (x + side * w, by - lift + tilt * ry * 0.04)
            mid = (x, by - lift - ry * 0.05)
            path = skia.Path()
            path.moveTo(*inner)
            path.quadTo(*mid, *outer)
            c.drawPath(path, stroke(bc, thick))

    def _draw_mouth(self, c, mx, my, t, st: RigState):
        d = self.d
        at = abs(t)
        rx, ry = self.head_rx, self.head_ry
        w0 = rx * 0.3 * (1 - 0.35 * at) * float(d.get("mouth_width", 1.0))
        e = st.expr
        smile = e.get("smile", 0.0)
        v = st.viseme
        # (half width factor, open height factor, roundness, teeth, tongue)
        table = {
            "A": (0.85, 0.0, 0.0, False, False),
            "B": (0.95, 0.12, 0.2, True, False),
            "C": (1.0, 0.32, 0.3, True, False),
            "D": (1.05, 0.55, 0.5, True, True),
            "E": (0.7, 0.38, 0.9, False, False),
            "F": (0.45, 0.22, 1.0, False, False),
            "G": (0.85, 0.12, 0.2, True, False),
            "H": (0.9, 0.35, 0.4, True, True),
            "X": (0.85, 0.0, 0.0, False, False),
        }
        wf, hf, rnd, teeth, tongue = table.get(v, table["X"])
        w = w0 * wf
        h = ry * hf * 0.5
        oc = self.outline
        if h < 1.0:
            path = skia.Path()
            curve = smile * ry * 0.12
            path.moveTo(mx - w, my - curve * 0.4)
            path.quadTo(mx, my + curve, mx + w, my - curve * 0.4)
            c.drawPath(path, stroke(oc, self.ow * 1.1))
            if smile > 0.6:
                for s in (-1, 1):
                    c.drawLine(mx + s * w, my - curve * 0.4, mx + s * w * 1.12, my - curve * 0.6,
                               stroke(oc, self.ow * 0.8))
            return
        path = skia.Path()
        top_curve = -smile * ry * 0.05
        bottom = h * (1 + 0.6 * rnd)
        path.moveTo(mx - w, my)
        path.cubicTo(mx - w * (1 - rnd * 0.4), my - h + top_curve, mx + w * (1 - rnd * 0.4), my - h + top_curve, mx + w, my)
        path.cubicTo(mx + w * (1 - rnd * 0.3), my + bottom, mx - w * (1 - rnd * 0.3), my + bottom, mx - w, my)
        path.close()
        c.drawPath(path, fill(col("#5a1e22")))
        c.save()
        c.clipPath(path, doAntiAlias=True)
        if teeth:
            c.drawRect(skia.Rect.MakeXYWH(mx - w, my - h * 1.2, w * 2, h * 0.65), fill(col("#fbf6ee")))
        if tongue:
            c.drawOval(skia.Rect.MakeXYWH(mx - w * 0.55, my + bottom * 0.25, w * 1.1, bottom), fill(col("#e86a73")))
        c.restore()
        c.drawPath(path, stroke(oc, self.ow * 1.0))
        if v == "G":  # F/V - upper teeth on lower lip
            c.drawLine(mx - w * 0.6, my + h * 0.4, mx + w * 0.6, my + h * 0.4, stroke(col(shade(d["skin"], 0.75)), self.ow * 1.4))

    # ---------------------------------------------------------------- hair etc
    def _draw_hair_back(self, c, cx, cy, hair, t):
        style = hair.get("style", "curly_bob")
        hc = col(hair.get("color", "#c4472b"))
        rx, ry = self.head_rx, self.head_ry
        f = 1 if t >= 0 else -1
        at = abs(t)
        if style == "curly_bob":
            off = -f * at * rx * 0.25
            r = skia.Rect.MakeXYWH(cx - rx * 1.22 + off, cy - ry * 1.15, rx * 2.44, ry * 2.0)
            path = skia.Path()
            path.addOval(r)
            for i in range(11):
                a = math.pi * (0.0 + 1.0 * i / 10)
                path.addCircle(cx + off + math.cos(a) * rx * 1.12, cy + ry * 0.62 + math.sin(a) * ry * 0.18, rx * 0.24)
            c.drawPath(path, stroke(self.outline, self.ow * 2))
            c.drawPath(path, fill(col(shade(hair.get("color", "#c4472b"), 0.82))))
        elif style == "short_white":
            pass

    def _draw_hair_front(self, c, cx, cy, hair, t):
        style = hair.get("style", "curly_bob")
        base = hair.get("color", "#c4472b")
        hc = col(base)
        rx, ry = self.head_rx, self.head_ry
        at = abs(t)
        f = 1 if t >= 0 else -1
        if style == "curly_bob":
            # top cap + curls across forehead, parted toward facing side
            cap = skia.Path()
            cap.moveTo(cx - rx * 1.08, cy - ry * 0.05)
            cap.cubicTo(cx - rx * 1.15, cy - ry * 1.35, cx + rx * 1.15, cy - ry * 1.35, cx + rx * 1.08, cy - ry * 0.05)
            cap.quadTo(cx + t * rx * 0.3, cy - ry * 0.75, cx - rx * 1.08, cy - ry * 0.05)
            curls = skia.Path()
            for i in range(7):
                k = i / 6
                x = lerp(cx - rx * 0.95, cx + rx * 0.95, k) + t * rx * 0.15
                y = cy - ry * 0.62 + math.sin(k * math.pi) * -ry * 0.12
                curls.addCircle(x, y, rx * (0.2 + 0.05 * math.sin(i * 2.1)))
            for side in (-1, 1):
                if at > 0.7 and side == f:
                    continue
                curls.addCircle(cx + side * rx * 1.02, cy - ry * 0.2, rx * 0.22)
                curls.addCircle(cx + side * rx * 1.05, cy + ry * 0.12, rx * 0.2)
            both = skia.Op(cap, curls, skia.PathOp.kUnion_PathOp) or cap
            c.drawPath(both, stroke(self.outline, self.ow * 2))
            c.drawPath(both, fill(hc))
            # highlights
            for i in range(3):
                x = cx - rx * 0.4 + i * rx * 0.35 + t * rx * 0.15
                c.drawArc(skia.Rect.MakeXYWH(x - rx * 0.12, cy - ry * 0.9, rx * 0.24, ry * 0.2), 200, 120, False,
                          stroke(col(shade(base, 1.35)), self.ow * 0.9))
        elif style == "short_white":
            for side in (-1, 1):
                if at > 0.75 and side == f:
                    continue
                path = skia.Path()
                x = cx + side * rx * (0.95 - (0.35 * at if side == f else 0))
                path.addOval(skia.Rect.MakeXYWH(x - rx * 0.2, cy - ry * 0.5, rx * 0.36, ry * 0.5))
                c.drawPath(path, stroke(self.outline, self.ow * 1.6))
                c.drawPath(path, fill(hc))

    def _draw_beard(self, c, cx, cy, t, color):
        rx, ry = self.head_rx, self.head_ry
        at = abs(t)
        off = t * rx * 0.3
        path = skia.Path()
        path.moveTo(cx - rx * 0.98 + off * 0.3, cy + ry * 0.05)
        path.cubicTo(cx - rx * 1.0 + off, cy + ry * 1.05, cx + rx * 1.0 + off, cy + ry * 1.05,
                     cx + rx * 0.98 + off * 0.3, cy + ry * 0.05)
        path.quadTo(cx + off, cy + ry * 0.35, cx - rx * 0.98 + off * 0.3, cy + ry * 0.05)
        for i in range(6):
            k = i / 5
            path.addCircle(lerp(cx - rx * 0.6, cx + rx * 0.6, k) + off, cy + ry * 0.78 + math.sin(k * math.pi) * ry * 0.12,
                           rx * 0.17)
        c.drawPath(path, stroke(self.outline, self.ow * 2))
        c.drawPath(path, fill(col(color)))
        c.drawPath(path, stroke(col(shade(color, 0.8)), self.ow * 0.6))

    def _draw_glasses(self, c, fx, ey, t):
        rx, ry = self.head_rx, self.head_ry
        at = abs(t)
        f = 1 if t >= 0 else -1
        spacing = rx * 0.42 * (1 - 0.38 * at)
        gc = col(self.d.get("glasses_color", "#3b2a20"))
        pts = []
        for side in (-1, 1):
            far = side == -f and at > 0.05
            if far and at > 0.85:
                continue
            k = 1 - 0.45 * at if far else 1.0
            x = fx + side * spacing
            r = rx * 0.3
            c.drawOval(skia.Rect.MakeXYWH(x - r * k, ey - r * 0.85, 2 * r * k, r * 1.7), fill(col("#bfe6ff", 0.18)))
            c.drawOval(skia.Rect.MakeXYWH(x - r * k, ey - r * 0.85, 2 * r * k, r * 1.7), stroke(gc, self.ow * 0.9))
            pts.append((x, side, k, r))
        if len(pts) == 2:
            c.drawLine(pts[0][0] + pts[0][3] * pts[0][2], ey, pts[1][0] - pts[1][3] * pts[1][2], ey, stroke(gc, self.ow * 0.9))

    def _draw_hat(self, c, cx, cy, t, hat):
        rx, ry = self.head_rx, self.head_ry
        f = 1 if t >= 0 else -1
        at = abs(t)
        color = hat.get("color", "#1f3554")
        band = hat.get("band", "#121e30")
        crown = skia.Path()
        crown.moveTo(cx - rx * 1.05, cy - ry * 0.55)
        crown.cubicTo(cx - rx * 1.15, cy - ry * 1.45, cx + rx * 1.15, cy - ry * 1.45, cx + rx * 1.05, cy - ry * 0.55)
        crown.close()
        c.drawPath(crown, stroke(self.outline, self.ow * 2))
        c.drawPath(crown, fill(col(color)))
        br = skia.Rect.MakeXYWH(cx - rx * 1.08, cy - ry * 0.72, rx * 2.16, ry * 0.22)
        c.drawRect(br, fill(col(band)))
        c.drawRect(br, stroke(self.outline, self.ow))
        # visor toward facing side
        vis = skia.Path()
        vx = cx + t * rx * 0.55
        vw = rx * (0.95 - 0.25 * at)
        vis.moveTo(vx - vw, cy - ry * 0.52)
        vis.quadTo(vx + f * rx * 0.25 * at, cy - ry * 0.28, vx + vw + f * at * rx * 0.35, cy - ry * 0.52)
        vis.close()
        c.drawPath(vis, stroke(self.outline, self.ow * 1.6))
        c.drawPath(vis, fill(col(shade(band, 0.8))))
        ec = hat.get("emblem")
        if ec:
            self._anchor_emblem(c, cx + t * rx * 0.55, cy - ry * 0.98, ry * 0.12, ec)


# --------------------------------------------------------------- turnarounds


def render_turnaround(design: dict[str, Any], out_png: str, width: int = 2400, height: int = 1200,
                      bg: str = "#f4efe6") -> None:
    """Model sheet: front, 3/4, side, back + expression and mouth-shape strips."""
    surf = skia.Surface(width, height)
    c = surf.getCanvas()
    c.clear(col(bg))
    rig = CharacterRig(design)
    scale = (height * 0.62) / rig.H
    views = [("front", 0.0, False), ("3/4", 0.5, False), ("side", 1.0, False), ("back", 0.0, True)]
    font = skia.Font(skia.Typeface.MakeFromFile(_font()), 30)
    for i, (name, turn, back) in enumerate(views):
        x = width * (0.12 + i * 0.13)
        st = RigState(turn=turn, back=back)
        rig.draw(c, st, x, height * 0.72, scale)
        c.drawString(name, x - 30, height * 0.78, font, fill(col("#333333")))
    # expressions
    small = scale * 0.42
    exprs = list(EXPRESSIONS.keys())
    for j, ex in enumerate(exprs[:8]):
        x = width * (0.62 + (j % 4) * 0.095)
        y = height * (0.38 if j < 4 else 0.75)
        st = RigState(turn=0.25, expr=dict(EXPRESSIONS[ex]))
        c.save()
        c.clipRect(skia.Rect.MakeXYWH(x - 110, y - rig.H * small - 10, 220, rig.H * small * 0.42))
        rig.draw(c, st, x, y, small)
        c.restore()
        c.drawString(ex, x - 50, y - rig.H * small * 0.55, skia.Font(skia.Typeface.MakeFromFile(_font()), 22),
                     fill(col("#333333")))
    title = skia.Font(skia.Typeface.MakeFromFile(_font()), 44)
    c.drawString(f"{design.get('name', '')}  -  model sheet", 40, 64, title, fill(col("#222222")))
    surf.makeImageSnapshot().save(out_png, skia.kPNG)


def render_mouth_chart(design: dict[str, Any], out_png: str) -> None:
    surf = skia.Surface(1800, 300)
    c = surf.getCanvas()
    c.clear(col("#f4efe6"))
    rig = CharacterRig(design)
    s = 0.9
    font = skia.Font(skia.Typeface.MakeFromFile(_font()), 26)
    for i, v in enumerate(VISEMES):
        x = 100 + i * 190
        st = RigState(turn=0.2, viseme=v)
        c.save()
        c.clipRect(skia.Rect.MakeXYWH(x - 95, 0, 190, 260))
        # position so the head is in view
        head_y = rig.H - rig.head_ry
        rig.draw(c, st, x, 140 + head_y * s - rig.head_ry * 0.1 + rig.H * 0.0, s)
        c.restore()
        c.drawString(v, x - 8, 290, font, fill(col("#222222")))
    surf.makeImageSnapshot().save(out_png, skia.kPNG)


def _font() -> str:
    from .config import font_path
    return font_path(True)
