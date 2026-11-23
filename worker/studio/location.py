"""Procedural, persistent locations rendered with Skia.

A location is a fixed *set* in stage coordinates (STAGE_W x STAGE_H).  The same
location id always produces the same geometry (seeded RNG); only lighting
(time of day / weather) and animated props (sea, clouds, lighthouse beam,
particles) change.  Layers carry a parallax factor so camera moves produce depth.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import skia

from .rig import col, fill, shade, stroke, lerp

STAGE_W = 3200.0
STAGE_H = 1800.0
GROUND_Y = 1480.0
HORIZON_Y = 960.0

LIGHTING: dict[str, dict[str, Any]] = {
    "day": dict(sky=["#5aa9e6", "#a7d8f5", "#e8f6ff"], sea="#2f86b8", sea2="#1d5f8f", sun=("#fff6c8", 0.75, 0.2),
                ambient="#ffffff", amb_k=0.0, key="#fff1d0", stars=0.0, rim="#fff1c8", grade=(1.0, 1.0, 1.0), lamp_k=0.2),
    "sunset": dict(sky=["#3b4f8f", "#e0748a", "#ffb35c", "#ffd9a0"], sea="#4a5d96", sea2="#2c3a6d",
                   sun=("#ffe2a0", 0.32, 0.53), ambient="#ff9a5c", amb_k=0.16, key="#ffc27a", stars=0.0,
                   rim="#ffb860", grade=(1.06, 0.97, 0.9), lamp_k=0.6),
    "dusk": dict(sky=["#1d2550", "#56427a", "#c76a7a", "#f2a77a"], sea="#33406e", sea2="#1c2448",
                 sun=("#ffc890", 0.3, 0.6), ambient="#7a5fa0", amb_k=0.25, key="#ffb08a", stars=0.25,
                 rim="#ff9f7a", grade=(0.95, 0.9, 1.0), lamp_k=0.8),
    "night": dict(sky=["#070b1f", "#121c42", "#22305e", "#2f3f70"], sea="#16224a", sea2="#0b1230",
                  sun=("#eef2ff", 0.72, 0.18), ambient="#3a4f9a", amb_k=0.42, key="#a9c0ff", stars=1.0,
                  rim="#9fc4ff", grade=(0.82, 0.88, 1.08), lamp_k=1.0, moon=True),
}


@dataclass
class EnvState:
    t: float = 0.0
    lamp: float = 1.0          # 0 off .. 1 on (lighthouse lamp)
    beam_speed: float = 0.35   # revolutions / second
    wind: float = 0.4
    rain: float = 0.0
    boat_signal: float = 0.0   # distant boat flashing light (0..1)
    boat_x: float = 0.35       # 0..1 across horizon
    fireflies: float = 0.0
    room_lamp: float = 1.0     # interior oil lamp (lighthouse room)
    extra: dict = field(default_factory=dict)


class LighthouseCliff:
    """'lighthouse_cliff' set: sea, islands, striped lighthouse, grassy cliff."""

    def __init__(self, loc: dict[str, Any], lighting: str = "sunset"):
        self.loc = loc
        self.pal = {"tower_a": "#f4f1ea", "tower_b": "#c8382f", "grass": "#5f9a4a", "rock": "#7d7468",
                    **loc.get("palette", {})}
        self.set_lighting(lighting)
        self.rng = random.Random(loc.get("id", "loc"))
        self.tower_x = 2600.0
        self.tower_base = GROUND_Y - 40
        self.tower_top = 220.0
        self._stars = [(self.rng.uniform(-800, STAGE_W + 800), self.rng.uniform(-400, HORIZON_Y - 120),
                        self.rng.uniform(1.0, 3.2), self.rng.uniform(0, 6.28)) for _ in range(260)]
        self._clouds = [(self.rng.uniform(-1000, STAGE_W + 1000), self.rng.uniform(100, 620),
                         self.rng.uniform(0.6, 1.5), self.rng.uniform(0.3, 1.0)) for _ in range(9)]
        self._grass = [(self.rng.uniform(-600, STAGE_W + 600), self.rng.uniform(0, 1)) for _ in range(380)]
        self._rain = [(self.rng.uniform(-400, STAGE_W + 400), self.rng.uniform(-200, STAGE_H)) for _ in range(500)]
        self._flies = [(self.rng.uniform(0, STAGE_W), self.rng.uniform(900, 1450), self.rng.uniform(0, 6.28))
                       for _ in range(40)]
        self._pictures: dict[str, skia.Picture] = {}

    def objects(self, view_w: float = 900.0) -> dict[str, tuple[float, float, float, float]]:
        """name -> (x, y, parallax, view width for an insert shot)."""
        return {
            "lamp": (self.tower_x, self.tower_top + 140, 0.7, view_w),
            "tower": (self.tower_x, (self.tower_top + self.tower_base) / 2, 0.7, 2200.0),
            "door": (self.tower_x - 20, self.tower_base - 260, 0.7, 1300.0),
            "boat": (lerp(-200, STAGE_W + 200, 0.35), HORIZON_Y - 40, 0.25, 1000.0),
            "sea": (STAGE_W * 0.3, HORIZON_Y + 60, 0.25, 2600.0),
            "bench": (self.loc.get("spots", {}).get("bench", 1100), GROUND_Y - 160, 1.0, 1100.0),
            "ground": (900, GROUND_Y + 20, 1.0, 900.0),
        }

    def set_lighting(self, name: str):
        self.lighting_name = name
        self.L = LIGHTING[name]
        self._pictures = {}

    # ---------------------------------------------------------------- static
    def _record(self, name: str, fn) -> skia.Picture:
        if name not in self._pictures:
            rec = skia.PictureRecorder()
            c = rec.beginRecording(skia.Rect.MakeLTRB(-1600, -800, STAGE_W + 1600, STAGE_H + 800))
            fn(c)
            self._pictures[name] = rec.finishRecordingAsPicture()
        return self._pictures[name]

    def _draw_islands(self, c: skia.Canvas):
        L = self.L
        base = shade(L["sea2"], 0.9)
        rng = random.Random(7)
        for k, (x0, w, h) in enumerate(((-900, 1500, 120), (500, 900, 70), (1900, 1300, 150), (3400, 1200, 90))):
            p = skia.Path()
            p.moveTo(x0, HORIZON_Y + 2)
            steps = 14
            for i in range(steps + 1):
                u = i / steps
                yy = HORIZON_Y - math.sin(u * math.pi) ** 1.4 * h * (0.8 + 0.3 * rng.random())
                p.lineTo(x0 + u * w, yy)
            p.lineTo(x0 + w, HORIZON_Y + 2)
            p.close()
            c.drawPath(p, fill(col(shade(base, 1.0 + 0.12 * k), 0.9)))

    def _draw_cliff(self, c: skia.Canvas):
        L = self.L
        grass = self.pal["grass"]
        rock = self.pal["rock"]
        # rock face dropping to the sea on the left
        p = skia.Path()
        p.moveTo(-1600, GROUND_Y - 120)
        p.cubicTo(-400, GROUND_Y - 170, 500, GROUND_Y - 120, 1200, GROUND_Y - 60)
        p.cubicTo(2000, GROUND_Y - 10, 2800, GROUND_Y - 90, STAGE_W + 1600, GROUND_Y - 140)
        p.lineTo(STAGE_W + 1600, STAGE_H + 800)
        p.lineTo(-1600, STAGE_H + 800)
        p.close()
        shader = skia.GradientShader.MakeLinear([(0, GROUND_Y - 160), (0, STAGE_H + 200)],
                                                [col(shade(grass, 1.1)), col(grass), col(shade(grass, 0.62))])
        c.drawPath(p, skia.Paint(AntiAlias=True, Shader=shader))
        c.drawPath(p, stroke(col(shade(grass, 0.55)), 6))
        # path of stones toward lighthouse door
        rng = random.Random(3)
        for i in range(16):
            u = i / 15
            x = lerp(900, self.tower_x - 60, u) + rng.uniform(-30, 30)
            y = GROUND_Y + 60 + math.sin(u * 3) * 20 + rng.uniform(-6, 6)
            w = 90 + rng.uniform(-20, 30)
            r = skia.Rect.MakeXYWH(x - w / 2, y - 16, w, 34)
            c.drawOval(r, fill(col(shade(rock, 1.25))))
            c.drawOval(r, stroke(col(shade(rock, 0.7)), 4))
        # rocks
        for (x, y, s) in ((-300, GROUND_Y + 40, 1.3), (180, GROUND_Y + 110, 0.8), (3050, GROUND_Y + 80, 1.1)):
            rp = skia.Path()
            rp.moveTo(x - 120 * s, y + 40 * s)
            rp.cubicTo(x - 110 * s, y - 70 * s, x + 90 * s, y - 90 * s, x + 130 * s, y + 40 * s)
            rp.close()
            c.drawPath(rp, fill(col(rock)))
            c.drawPath(rp, stroke(col(shade(rock, 0.6)), 6))
            c.drawLine(x - 40 * s, y - 30 * s, x + 30 * s, y - 50 * s, stroke(col(shade(rock, 1.3)), 6))
        # wooden fence along cliff edge (left)
        wood = "#8a5a3a"
        for i in range(9):
            x = -500 + i * 150
            y = GROUND_Y - 150 + i * 6
            c.drawRect(skia.Rect.MakeXYWH(x - 12, y - 120, 24, 140), fill(col(wood)))
            c.drawRect(skia.Rect.MakeXYWH(x - 12, y - 120, 24, 140), stroke(col(shade(wood, 0.5)), 4))
        for yy in (-95, -45):
            c.drawLine(-520, GROUND_Y - 150 + yy, 700, GROUND_Y - 100 + yy, stroke(col(shade(wood, 0.5)), 26))
            c.drawLine(-520, GROUND_Y - 150 + yy, 700, GROUND_Y - 100 + yy, stroke(col(wood), 18))
        # bench
        bx = self.loc.get("spots", {}).get("bench", 1100)
        by = GROUND_Y - 30
        for lx in (bx - 150, bx + 150):
            c.drawRect(skia.Rect.MakeXYWH(lx - 12, by - 90, 24, 95), fill(col(shade(wood, 0.6))))
        c.drawRoundRect(skia.Rect.MakeXYWH(bx - 200, by - 110, 400, 30), 8, 8, fill(col(wood)))
        c.drawRoundRect(skia.Rect.MakeXYWH(bx - 200, by - 110, 400, 30), 8, 8, stroke(col(shade(wood, 0.5)), 4))
        c.drawRoundRect(skia.Rect.MakeXYWH(bx - 200, by - 200, 400, 26), 8, 8, fill(col(wood)))
        c.drawRoundRect(skia.Rect.MakeXYWH(bx - 200, by - 200, 400, 26), 8, 8, stroke(col(shade(wood, 0.5)), 4))
        # crates + rope near door
        cx = self.tower_x - 420
        for (ox, oy, s) in ((0, 0, 1.0), (110, 0, 0.8), (40, -105, 0.75)):
            w = 120 * s
            r = skia.Rect.MakeXYWH(cx + ox - w / 2, GROUND_Y - 10 + oy - w, w, w)
            c.drawRect(r, fill(col("#a87445")))
            c.drawRect(r, stroke(col("#5a3a22"), 5))
            c.drawLine(r.left(), r.top(), r.right(), r.bottom(), stroke(col("#7a5030"), 5))
        # mooring rope coil
        for k in range(4):
            c.drawOval(skia.Rect.MakeXYWH(cx + 230 - k * 6, GROUND_Y - 40 - k * 12, 120 - k * 6, 36),
                       stroke(col("#c9a46a"), 9))

    def _draw_tower(self, c: skia.Canvas):
        a, b = self.pal["tower_a"], self.pal["tower_b"]
        x = self.tower_x
        base_w, top_w = 330.0, 210.0
        top = self.tower_top + 210
        bottom = self.tower_base
        p = skia.Path()
        p.moveTo(x - top_w / 2, top)
        p.lineTo(x + top_w / 2, top)
        p.lineTo(x + base_w / 2, bottom)
        p.lineTo(x - base_w / 2, bottom)
        p.close()
        c.drawPath(p, fill(col(a)))
        c.save()
        c.clipPath(p, doAntiAlias=True)
        n = 5
        for i in range(n):
            if i % 2 == 0:
                y0 = lerp(top, bottom, i / n)
                y1 = lerp(top, bottom, (i + 1) / n)
                c.drawRect(skia.Rect.MakeLTRB(x - base_w, y0, x + base_w, y1), fill(col(b)))
        sh = skia.GradientShader.MakeLinear([(x - base_w / 2, 0), (x + base_w / 2, 0)],
                                            [col("#ffffff", 0.18), col("#000000", 0.0), col("#000000", 0.35)],
                                            [0.0, 0.45, 1.0])
        c.drawRect(skia.Rect.MakeLTRB(x - base_w, top, x + base_w, bottom), skia.Paint(Shader=sh))
        c.restore()
        c.drawPath(p, stroke(col("#3a2522"), 7))
        # door + windows
        dw = 110
        door = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x - dw / 2 - 20, bottom - 210, dw, 210), 50, 50)
        c.drawRRect(door, fill(col("#4c3324")))
        c.drawRRect(door, stroke(col("#24160f"), 6))
        c.drawCircle(x - 20 + dw * 0.28, bottom - 105, 7, fill(col("#e2b341")))
        for wy in (top + 260, top + 560):
            r = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x - 26, wy, 52, 80), 26, 26)
            c.drawRRect(r, fill(col("#203048")))
            c.drawRRect(r, stroke(col("#24160f"), 5))
        # gallery / railing
        gy = top - 20
        c.drawRect(skia.Rect.MakeXYWH(x - top_w / 2 - 40, gy, top_w + 80, 26), fill(col("#2f2a2a")))
        for i in range(9):
            rx_ = x - top_w / 2 - 30 + i * (top_w + 60) / 8
            c.drawLine(rx_, gy, rx_, gy - 60, stroke(col("#2f2a2a"), 6))
        c.drawLine(x - top_w / 2 - 40, gy - 60, x + top_w / 2 + 40, gy - 60, stroke(col("#2f2a2a"), 8))
        # roof
        roof = skia.Path()
        roof.moveTo(x - top_w / 2 - 10, self.tower_top + 70)
        roof.lineTo(x, self.tower_top - 30)
        roof.lineTo(x + top_w / 2 + 10, self.tower_top + 70)
        roof.close()
        c.drawPath(roof, fill(col(b)))
        c.drawPath(roof, stroke(col("#3a2522"), 7))
        c.drawCircle(x, self.tower_top - 40, 16, fill(col("#2f2a2a")))

    # ---------------------------------------------------------------- frame
    def draw(self, c: skia.Canvas, cam, env: EnvState, dof: float = 0.0):
        """cam: Camera with .apply(canvas, parallax)."""
        L = self.L
        t = env.t
        # sky (screen-space gradient so it always fills)
        w, h = cam.out_w, cam.out_h
        sky_cols = [col(cc) for cc in L["sky"]]
        top_y, bot_y = cam.world_to_screen_y(-300, 0.05), cam.world_to_screen_y(HORIZON_Y, 0.05)
        sh = skia.GradientShader.MakeLinear([(0, top_y), (0, bot_y)], sky_cols)
        c.drawRect(skia.Rect.MakeWH(w, h), skia.Paint(Shader=sh))

        blur = dof > 0.01
        if blur:
            c.saveLayer(None, skia.Paint(ImageFilter=skia.ImageFilters.Blur(dof * 1.0, dof * 1.0)))

        # sun / moon + stars (parallax 0.05)
        c.save()
        cam.apply(c, 0.05)
        sc, sx, sy = L["sun"]
        sun_pos = (sx * STAGE_W, sy * STAGE_H)
        glow = skia.GradientShader.MakeRadial(sun_pos, 520, [col(sc, 0.55), col(sc, 0.0)])
        c.drawCircle(*sun_pos, 520, skia.Paint(AntiAlias=True, Shader=glow))
        if L.get("moon"):
            disc = skia.Path()
            disc.addCircle(sun_pos[0], sun_pos[1], 60)
            bite = skia.Path()
            bite.addCircle(sun_pos[0] + 26, sun_pos[1] - 12, 54)
            moon = skia.Op(disc, bite, skia.PathOp.kDifference_PathOp) or disc
            c.drawPath(moon, fill(col(sc)))
        else:
            c.drawCircle(*sun_pos, 85, fill(col(sc)))
        if L["stars"] > 0:
            for (x, y, r, ph) in self._stars:
                a = L["stars"] * (0.55 + 0.45 * math.sin(t * 2.0 + ph))
                c.drawCircle(x, y, r, fill(col("#ffffff", a)))
        c.restore()

        # clouds (parallax 0.12)
        c.save()
        cam.apply(c, 0.12)
        cloud_c = shade(L["sky"][-1], 1.05) if self.lighting_name != "night" else "#3a4a7a"
        for (x, y, s, a) in self._clouds:
            xx = ((x + t * 18 * env.wind * s) + 1000) % (STAGE_W + 2000) - 1000
            self._cloud(c, xx, y, s, col(cloud_c, 0.55 * a + 0.2))
        c.restore()

        # sea + islands (parallax 0.25)
        c.save()
        cam.apply(c, 0.25)
        c.drawPicture(self._record("islands", self._draw_islands))
        sea_sh = skia.GradientShader.MakeLinear([(0, HORIZON_Y), (0, STAGE_H)], [col(L["sea"]), col(L["sea2"])])
        c.drawRect(skia.Rect.MakeLTRB(-2000, HORIZON_Y, STAGE_W + 2000, STAGE_H + 900), skia.Paint(Shader=sea_sh))
        # sun reflection
        for i in range(14):
            yy = HORIZON_Y + 10 + i * 26
            wv = 120 - i * 5 + 30 * math.sin(t * 1.5 + i)
            c.drawLine(sun_pos[0] - wv, yy, sun_pos[0] + wv, yy, stroke(col(sc, 0.35 - i * 0.02), 5))
        # wave lines
        for row in range(10):
            yy = HORIZON_Y + 25 + row * row * 9
            amp = 2 + row * 1.6
            p = skia.Path()
            for i in range(0, 61):
                xx = -1800 + i * (STAGE_W + 3600) / 60
                y2 = yy + math.sin(xx * 0.006 + t * (0.8 + row * 0.1) + row) * amp
                if i == 0:
                    p.moveTo(xx, y2)
                else:
                    p.lineTo(xx, y2)
            c.drawPath(p, stroke(col("#ffffff", 0.08 + row * 0.012), 2 + row * 0.5))
        # distant boat
        bx = lerp(-200, STAGE_W + 200, env.boat_x)
        by = HORIZON_Y + 8 + math.sin(t * 1.3) * 4
        self._boat(c, bx, by, env)
        c.restore()

        self.draw_set(c, cam, env)

        if blur:
            c.restore()

    def draw_set(self, c: skia.Canvas, cam, env: EnvState):
        """Mid/foreground set pieces (overridden by other outdoor sets)."""
        # lighthouse (parallax 0.7)
        c.save()
        cam.apply(c, 0.7)
        c.drawPicture(self._record("tower", self._draw_tower))
        self._draw_lamp(c, env)
        c.restore()
        # cliff/ground (parallax 1.0)
        c.save()
        cam.apply(c, 1.0)
        c.drawPicture(self._record("cliff", self._draw_cliff))
        self._draw_grass(c, env.t, env)
        c.restore()

    def draw_foreground(self, c: skia.Canvas, cam, env: EnvState):
        """Atmosphere drawn in front of characters: lamp beam, rain, fireflies."""
        L = self.L
        t = env.t
        c.save()
        cam.apply(c, 0.7)
        if env.lamp > 0.05 and L["lamp_k"] > 0.3:
            self._draw_beam(c, env)
        c.restore()
        c.save()
        cam.apply(c, 1.0)
        if env.fireflies > 0:
            for (x, y, ph) in self._flies:
                xx = x + math.sin(t * 0.7 + ph) * 60
                yy = y + math.cos(t * 0.9 + ph * 2) * 40
                a = env.fireflies * (0.5 + 0.5 * math.sin(t * 3 + ph))
                g = skia.GradientShader.MakeRadial((xx, yy), 22, [col("#fff3a0", a), col("#fff3a0", 0)])
                c.drawCircle(xx, yy, 22, skia.Paint(AntiAlias=True, Shader=g))
        if env.rain > 0:
            p = stroke(col("#cfe0ff", 0.35 * env.rain), 3)
            for (x, y) in self._rain:
                yy = (y + t * 1400) % (STAGE_H + 400) - 200
                xx = x + (yy * 0.15)
                c.drawLine(xx, yy, xx + 10, yy + 46, p)
        c.restore()

    def beam_intensity_at(self, env: EnvState, x: float) -> float:
        """How strongly the rotating beam lights a point at stage x (for character flashes)."""
        if env.lamp < 0.05:
            return 0.0
        ang = (env.t * env.beam_speed * 360.0) % 360.0
        # beam pointing toward viewer/left when angle ~ 180
        face = math.cos(math.radians(ang))
        toward_left = 1 if math.sin(math.radians(ang)) < 0 else 0
        k = max(0.0, -face) ** 8 * toward_left
        return k * env.lamp * self.L["lamp_k"]

    # ------------------------------------------------------------- helpers
    def _draw_lamp(self, c, env: EnvState):
        x = self.tower_x
        y = self.tower_top + 140
        on = env.lamp
        glass = skia.Rect.MakeXYWH(x - 80, y - 60, 160, 120)
        c.drawRect(glass, fill(col("#1c2430")))
        if on > 0.02:
            g = skia.GradientShader.MakeRadial((x, y), 360 * (0.5 + on * 0.5),
                                               [col("#fff6c0", 0.9 * on), col("#ffd860", 0.35 * on), col("#ffd860", 0)])
            c.drawCircle(x, y, 360, skia.Paint(AntiAlias=True, Shader=g))
            c.drawRect(glass, fill(col("#fff1a8", 0.95 * on)))
        for i in range(5):
            xx = x - 80 + i * 40
            c.drawLine(xx, y - 60, xx, y + 60, stroke(col("#2f2a2a"), 6))
        c.drawRect(glass, stroke(col("#2f2a2a"), 8))

    def _draw_beam(self, c, env: EnvState):
        x = self.tower_x
        y = self.tower_top + 140
        ang = (env.t * env.beam_speed * 360.0) % 360.0
        # project the 3D rotation into a 2D sweeping cone
        s = math.sin(math.radians(ang))
        cz = math.cos(math.radians(ang))
        length = 3600 * (0.35 + 0.65 * abs(s))
        width = 220 + 900 * max(0.0, -cz)
        alpha = (0.22 + 0.25 * max(0.0, -cz)) * env.lamp * self.L["lamp_k"]
        dx = s * length
        p = skia.Path()
        p.moveTo(x, y - 30)
        p.lineTo(x + dx, y - width / 2)
        p.lineTo(x + dx, y + width / 2)
        p.lineTo(x, y + 30)
        p.close()
        g = skia.GradientShader.MakeLinear([(x, y), (x + dx, y)], [col("#fff6c8", alpha), col("#fff6c8", 0.0)])
        c.drawPath(p, skia.Paint(AntiAlias=True, Shader=g, BlendMode=skia.BlendMode.kPlus))

    def _cloud(self, c, x, y, s, color):
        p = skia.Path()
        for (ox, oy, r) in ((0, 0, 90), (90, -30, 110), (200, 0, 85), (110, 30, 95), (-80, 20, 70)):
            p.addCircle(x + ox * s, y + oy * s, r * s)
        c.drawPath(p, fill(color))

    def _boat(self, c, x, y, env: EnvState):
        hull = skia.Path()
        hull.moveTo(x - 60, y - 14)
        hull.lineTo(x + 60, y - 14)
        hull.lineTo(x + 42, y + 6)
        hull.lineTo(x - 42, y + 6)
        hull.close()
        c.drawPath(hull, fill(col("#2a2230")))
        c.drawLine(x, y - 14, x, y - 80, stroke(col("#2a2230"), 4))
        sail = skia.Path()
        sail.moveTo(x + 3, y - 78)
        sail.lineTo(x + 46, y - 20)
        sail.lineTo(x + 3, y - 20)
        sail.close()
        c.drawPath(sail, fill(col("#e9e2d0", 0.85)))
        if env.boat_signal > 0.01:
            g = skia.GradientShader.MakeRadial((x - 20, y - 30), 90, [col("#fffbe0", env.boat_signal), col("#fff2a0", 0)])
            c.drawCircle(x - 20, y - 30, 90, skia.Paint(AntiAlias=True, Shader=g))
            c.drawCircle(x - 20, y - 30, 8, fill(col("#ffffff", env.boat_signal)))

    def _draw_grass(self, c, t, env: EnvState):
        g = self.pal["grass"]
        dark = col(shade(g, 0.7))
        light = col(shade(g, 1.25))
        for (x, k) in self._grass:
            y = GROUND_Y - 40 + k * 300
            if x < 1300:
                y = GROUND_Y - 120 + (x / 1300) * 60 + k * 300
            sway = math.sin(t * 2.2 + x * 0.01) * 8 * env.wind
            hgt = 26 + k * 30
            c.drawLine(x, y, x + sway, y - hgt, stroke(dark if k > 0.5 else light, 4))


LOCATION_KINDS: dict[str, type] = {"lighthouse_cliff": LighthouseCliff}


def make_location(loc: dict[str, Any], lighting: str):
    from . import locations_extra  # noqa: F401  (registers more set kinds)
    kind = loc.get("kind", "lighthouse_cliff")
    return LOCATION_KINDS[kind](loc, lighting)


def object_camera(loc_obj, name: str, view_w: float = 900.0) -> tuple[float, float, float]:
    """Camera key (cx, cy, view_w) that centres a named set object, compensating parallax."""
    ax, ay = STAGE_W / 2, STAGE_H / 2
    table = loc_obj.objects(view_w) if hasattr(loc_obj, "objects") else {}
    x, y, p, vw = table.get(name, (ax, ay, 1.0, view_w))
    return ax + (x - ax) / p, ay + (y - ay) / p, vw


def world_objects(loc_obj) -> dict[str, tuple[float, float, float]]:
    """Object positions in stage space (for look-at targets and facing)."""
    ax, ay = STAGE_W / 2, STAGE_H / 2
    out = {}
    for name, (x, y, p, _vw) in (loc_obj.objects() if hasattr(loc_obj, "objects") else {}).items():
        # project layer position into the character layer (p=1) so look-at directions are right
        out[name] = (ax + (x - ax) / p if p < 1 else x, y, 0.0)
    return out
