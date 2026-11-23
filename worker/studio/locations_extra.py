"""Additional persistent procedural sets.

* ``lighthouse_room`` - keeper's room inside the lighthouse (interior, warm oil lamp,
  portholes showing the outside lighting, map table, Leyla's photo, spiral stairs).
* ``harbor``          - Martı village harbor: stone pier, moored fishing boats, the red-sailed
  boat "Yakamoz", white houses with blue shutters, the lighthouse on the far headland.

Geometry is seeded from the location id so every episode draws the identical set.
"""
from __future__ import annotations

import math
import random
from typing import Any

import skia

from .location import (GROUND_Y, HORIZON_Y, LIGHTING, LOCATION_KINDS, STAGE_H, STAGE_W, EnvState,
                       LighthouseCliff)
from .rig import col, fill, lerp, shade, stroke

INTERIOR_TINT = {
    "day": dict(ambient="#ffe2b8", amb_k=0.06, grade=(1.04, 1.0, 0.95), rim="#ffe6b0"),
    "sunset": dict(ambient="#ffad6a", amb_k=0.14, grade=(1.07, 0.98, 0.9), rim="#ffc27a"),
    "dusk": dict(ambient="#d9925a", amb_k=0.2, grade=(0.97, 0.88, 0.8), rim="#ffb07a"),
    "night": dict(ambient="#c27a40", amb_k=0.3, grade=(0.9, 0.78, 0.66), rim="#ffb860"),
}


class LighthouseRoom:
    def __init__(self, loc: dict[str, Any], lighting: str = "day"):
        self.loc = loc
        self.rng = random.Random(loc.get("id", "room"))
        self._pictures: dict[str, skia.Picture] = {}
        self._dust = [(self.rng.uniform(300, 2700), self.rng.uniform(300, 1400), self.rng.uniform(0, 6.28))
                      for _ in range(70)]
        self.windows = [(700.0, 640.0), (2050.0, 640.0)]
        self.lamp_xy = (1450.0, 330.0)
        self.set_lighting(lighting)

    # same interface as LighthouseCliff -------------------------------------------------
    def set_lighting(self, name: str):
        self.lighting_name = name
        self.outside = LIGHTING[name]
        self.L = {**LIGHTING[name], **INTERIOR_TINT[name], "lamp_k": 0.0, "stars": 0.0}
        self._pictures = {}

    def objects(self, view_w: float = 900.0):
        return {
            "lamp": (self.lamp_xy[0], self.lamp_xy[1] + 60, 1.0, 800.0),
            "window": (self.windows[0][0], self.windows[0][1], 0.9, 900.0),
            "sea": (self.windows[1][0], self.windows[1][1], 0.9, 900.0),
            "photo": (1080.0, 560.0, 0.9, 600.0),
            "table": (1450.0, GROUND_Y - 170, 1.0, 1000.0),
            "map": (1450.0, GROUND_Y - 250, 1.0, 700.0),
            "letter": (1600.0, GROUND_Y - 250, 1.0, 600.0),
            "stairs": (2850.0, 800.0, 1.0, 1400.0),
            "chest": (2350.0, GROUND_Y - 80, 1.0, 900.0),
            "ground": (1450.0, GROUND_Y + 20, 1.0, 900.0),
        }

    def beam_intensity_at(self, env: EnvState, x: float) -> float:
        # warm flicker from the oil lamp acts like a soft key-light pulse on faces
        return 0.0

    def _record(self, name, fn):
        if name not in self._pictures:
            rec = skia.PictureRecorder()
            c = rec.beginRecording(skia.Rect.MakeLTRB(-1600, -900, STAGE_W + 1600, STAGE_H + 900))
            fn(c)
            self._pictures[name] = rec.finishRecordingAsPicture()
        return self._pictures[name]

    # static layers ----------------------------------------------------------------------
    def _draw_wall(self, c: skia.Canvas):
        wall = "#efe4d0"
        sh = skia.GradientShader.MakeRadial((STAGE_W / 2, 700), 2600, [col(shade(wall, 1.05)), col(wall),
                                                                      col(shade(wall, 0.72))], [0, 0.5, 1])
        c.drawRect(skia.Rect.MakeLTRB(-1600, -900, STAGE_W + 1600, GROUND_Y - 150), skia.Paint(Shader=sh))
        # whitewashed stone blocks (curved wall)
        rng = random.Random(11)
        line = stroke(col(shade(wall, 0.82)), 3)
        for row in range(-6, 14):
            y = row * 110
            off = (row % 2) * 120
            c.drawLine(-1600, y, STAGE_W + 1600, y + 0, line)
            x = -1600 + off
            while x < STAGE_W + 1600:
                c.drawLine(x, y, x, y + 110, line)
                x += 240 + rng.uniform(-30, 30)
        # wooden beam ceiling
        for x in range(-1400, int(STAGE_W) + 1600, 420):
            c.drawRect(skia.Rect.MakeXYWH(x, -900, 70, 520), fill(col("#6b4a33")))
            c.drawRect(skia.Rect.MakeXYWH(x, -900, 70, 520), stroke(col("#3d2a1d"), 4))
        c.drawRect(skia.Rect.MakeLTRB(-1600, -420, STAGE_W + 1600, -360), fill(col("#5a3d2a")))
        # framed photo of Leyla (story prop)
        self._photo(c, 1080, 560)
        # ship's wheel
        self._wheel(c, 2480, 520, 120)
        # bookshelf
        bx, by = 120, 380
        c.drawRect(skia.Rect.MakeXYWH(bx, by, 420, 950), fill(col("#5c3d28")))
        for k in range(4):
            yy = by + 40 + k * 230
            c.drawRect(skia.Rect.MakeXYWH(bx + 20, yy + 170, 380, 22), fill(col("#3d281a")))
            x = bx + 30
            r2 = random.Random(k)
            while x < bx + 380:
                w = r2.uniform(26, 48)
                hgt = r2.uniform(120, 165)
                bc = r2.choice(["#a63d32", "#2f5d8a", "#c9a227", "#3f7a4a", "#7a4a8a", "#d9cbb0"])
                c.drawRect(skia.Rect.MakeXYWH(x, yy + 170 - hgt, w, hgt), fill(col(bc)))
                c.drawRect(skia.Rect.MakeXYWH(x, yy + 170 - hgt, w, hgt), stroke(col("#2a1d1a"), 2))
                x += w + 3
        c.drawRect(skia.Rect.MakeXYWH(bx, by, 420, 950), stroke(col("#2a1d1a"), 6))
        # skirting / floor
        floor_top = GROUND_Y - 150
        sh2 = skia.GradientShader.MakeLinear([(0, floor_top), (0, STAGE_H + 400)], [col("#8a5d3b"), col("#4a2f1e")])
        c.drawRect(skia.Rect.MakeLTRB(-1600, floor_top, STAGE_W + 1600, STAGE_H + 900), skia.Paint(Shader=sh2))
        vx = STAGE_W / 2
        for i in range(-14, 15):
            c.drawLine(vx + i * 60, floor_top, vx + i * 330, STAGE_H + 900, stroke(col("#3a2416", 0.7), 4))
        for k in range(6):
            y = floor_top + (k ** 1.6) * 30
            c.drawLine(-1600, y, STAGE_W + 1600, y, stroke(col("#3a2416", 0.5), 3))
        c.drawRect(skia.Rect.MakeLTRB(-1600, floor_top - 24, STAGE_W + 1600, floor_top), fill(col("#5a3d2a")))

    def _draw_furniture(self, c: skia.Canvas):
        # table with map, teapot, letter
        tx, ty = 1450.0, GROUND_Y - 190
        c.drawRect(skia.Rect.MakeXYWH(tx - 360, ty - 30, 720, 44), fill(col("#7a4f30")))
        c.drawRect(skia.Rect.MakeXYWH(tx - 360, ty - 30, 720, 44), stroke(col("#2a1d1a"), 5))
        for lx in (tx - 320, tx + 300):
            c.drawRect(skia.Rect.MakeXYWH(lx, ty + 14, 30, 190), fill(col("#5c3a22")))
            c.drawRect(skia.Rect.MakeXYWH(lx, ty + 14, 30, 190), stroke(col("#2a1d1a"), 4))
        mp = skia.Path()
        mp.moveTo(tx - 260, ty - 32)
        mp.lineTo(tx + 60, ty - 38)
        mp.lineTo(tx + 80, ty - 60)
        mp.lineTo(tx - 240, ty - 58)
        mp.close()
        c.drawPath(mp, fill(col("#e8d6a8")))
        c.drawPath(mp, stroke(col("#8a6a3a"), 3))
        c.drawLine(tx - 200, ty - 46, tx - 40, ty - 50, stroke(col("#b5482f"), 3))
        c.drawCircle(tx - 40, ty - 50, 6, fill(col("#b5482f")))
        # teapot
        px = tx + 200
        c.drawOval(skia.Rect.MakeXYWH(px - 50, ty - 110, 100, 80), fill(col("#3f6f8a")))
        c.drawOval(skia.Rect.MakeXYWH(px - 50, ty - 110, 100, 80), stroke(col("#2a1d1a"), 4))
        c.drawLine(px + 45, ty - 80, px + 85, ty - 105, stroke(col("#2a1d1a"), 10))
        c.drawLine(px + 45, ty - 80, px + 85, ty - 105, stroke(col("#3f6f8a"), 6))
        # chest
        cx = 2350.0
        c.drawRoundRect(skia.Rect.MakeXYWH(cx - 150, GROUND_Y - 150, 300, 150), 16, 16, fill(col("#6b4226")))
        c.drawRoundRect(skia.Rect.MakeXYWH(cx - 150, GROUND_Y - 150, 300, 150), 16, 16, stroke(col("#2a1d1a"), 5))
        for bx in (cx - 100, cx + 90):
            c.drawRect(skia.Rect.MakeXYWH(bx, GROUND_Y - 150, 14, 150), fill(col("#c9a227")))
        # spiral stairs (iron)
        sx = 2850.0
        c.drawRect(skia.Rect.MakeXYWH(sx - 12, -900, 24, GROUND_Y + 900), fill(col("#2f2a2a")))
        for k in range(14):
            y = GROUND_Y - 60 - k * 140
            dirn = 1 if k % 2 == 0 else -1
            st = skia.Path()
            st.moveTo(sx, y)
            st.lineTo(sx + dirn * 260, y - 30)
            st.lineTo(sx + dirn * 260, y - 4)
            st.lineTo(sx, y + 24)
            st.close()
            c.drawPath(st, fill(col("#4a4040")))
            c.drawPath(st, stroke(col("#1d1818"), 4))
        # rug
        c.drawOval(skia.Rect.MakeXYWH(900, GROUND_Y - 60, 1200, 140), fill(col("#8a2f2f", 0.85)))
        c.drawOval(skia.Rect.MakeXYWH(960, GROUND_Y - 45, 1080, 110), stroke(col("#e0b04a", 0.8), 6))

    def _photo(self, c, x, y):
        c.drawRect(skia.Rect.MakeXYWH(x - 95, y - 120, 190, 240), fill(col("#7a5230")))
        c.drawRect(skia.Rect.MakeXYWH(x - 78, y - 103, 156, 206), fill(col("#e8dcc0")))
        # sepia portrait of a smiling woman with a scarf
        c.drawOval(skia.Rect.MakeXYWH(x - 38, y - 70, 76, 92), fill(col("#c9a27a")))
        hair = skia.Path()
        hair.addArc(skia.Rect.MakeXYWH(x - 46, y - 82, 92, 80), 180, 180)
        c.drawPath(hair, fill(col("#6b4a33")))
        c.drawCircle(x - 14, y - 30, 4, fill(col("#3a2a1d")))
        c.drawCircle(x + 14, y - 30, 4, fill(col("#3a2a1d")))
        c.drawArc(skia.Rect.MakeXYWH(x - 16, y - 18, 32, 18), 20, 140, False, stroke(col("#3a2a1d"), 3))
        c.drawRect(skia.Rect.MakeXYWH(x - 60, y + 26, 120, 70), fill(col("#8a6a4a")))
        c.drawRect(skia.Rect.MakeXYWH(x - 95, y - 120, 190, 240), stroke(col("#2a1d1a"), 5))

    def _wheel(self, c, x, y, r):
        p = stroke(col("#6b4226"), 18)
        c.drawCircle(x, y, r, p)
        c.drawCircle(x, y, r * 0.3, fill(col("#6b4226")))
        for k in range(8):
            a = k * math.pi / 4
            c.drawLine(x, y, x + math.cos(a) * r * 1.35, y + math.sin(a) * r * 1.35, stroke(col("#6b4226"), 14))
            c.drawCircle(x + math.cos(a) * r * 1.38, y + math.sin(a) * r * 1.38, 14, fill(col("#6b4226")))
        c.drawCircle(x, y, r, stroke(col("#2a1d1a"), 3))

    def _porthole_view(self, c, x, y, r, env: EnvState):
        O = self.outside
        c.save()
        clip = skia.Path()
        clip.addCircle(x, y, r)
        c.clipPath(clip, doAntiAlias=True)
        sh = skia.GradientShader.MakeLinear([(0, y - r), (0, y + r * 0.2)], [col(cc) for cc in O["sky"]])
        c.drawRect(skia.Rect.MakeXYWH(x - r, y - r, 2 * r, 2 * r), skia.Paint(Shader=sh))
        c.drawRect(skia.Rect.MakeXYWH(x - r, y + r * 0.2, 2 * r, r), fill(col(O["sea"])))
        for k in range(4):
            yy = y + r * 0.3 + k * 22
            c.drawLine(x - r, yy + math.sin(env.t + k) * 3, x + r, yy, stroke(col("#ffffff", 0.15), 3))
        if O.get("moon"):
            c.drawCircle(x + r * 0.35, y - r * 0.4, 18, fill(col("#eef2ff")))
        elif self.lighting_name in ("sunset", "dusk"):
            c.drawCircle(x - r * 0.2, y + r * 0.15, 30, fill(col(O["sun"][0])))
        c.restore()
        c.drawCircle(x, y, r, stroke(col("#b08a3a"), 30))
        c.drawCircle(x, y, r + 15, stroke(col("#5a4420"), 4))
        for k in range(8):
            a = k * math.pi / 4
            c.drawCircle(x + math.cos(a) * (r + 2), y + math.sin(a) * (r + 2), 7, fill(col("#e0c070")))
        c.drawLine(x - r, y, x + r, y, stroke(col("#5a4420"), 8))
        c.drawLine(x, y - r, x, y + r, stroke(col("#5a4420"), 8))

    # frame ------------------------------------------------------------------------------
    def draw(self, c: skia.Canvas, cam, env: EnvState, dof: float = 0.0):
        w, h = cam.out_w, cam.out_h
        c.drawRect(skia.Rect.MakeWH(w, h), fill(col("#2a1d14")))
        blur = dof > 0.01
        if blur:
            c.saveLayer(None, skia.Paint(ImageFilter=skia.ImageFilters.Blur(dof, dof)))
        c.save()
        cam.apply(c, 0.9)
        c.drawPicture(self._record("wall", self._draw_wall))
        for (x, y) in self.windows:
            self._porthole_view(c, x, y, 170, env)
            if self.lighting_name in ("day", "sunset"):
                ray = skia.Path()
                ray.moveTo(x - 120, y - 100)
                ray.lineTo(x + 120, y + 100)
                ray.lineTo(x + 520, GROUND_Y - 100)
                ray.lineTo(x - 80, GROUND_Y - 60)
                ray.close()
                k = 0.12 if self.lighting_name == "day" else 0.09
                c.drawPath(ray, skia.Paint(AntiAlias=True, Color=col(self.outside["sun"][0], k),
                                           BlendMode=skia.BlendMode.kPlus))
        c.restore()
        c.save()
        cam.apply(c, 1.0)
        c.drawPicture(self._record("furniture", self._draw_furniture))
        self._oil_lamp(c, env)
        c.restore()
        if blur:
            c.restore()

    def _oil_lamp(self, c, env: EnvState):
        x, y = self.lamp_xy
        c.drawLine(x, -900, x, y - 60, stroke(col("#2f2a2a"), 6))
        flick = env.room_lamp * (0.9 + 0.1 * math.sin(env.t * 11.0) * math.sin(env.t * 3.7))
        if flick > 0.02:
            g = skia.GradientShader.MakeRadial((x, y), 1300, [col("#ffcf7a", 0.38 * flick), col("#ffb050", 0.12 * flick),
                                                              col("#ffb050", 0.0)], [0, 0.4, 1])
            c.drawCircle(x, y, 1300, skia.Paint(AntiAlias=True, Shader=g, BlendMode=skia.BlendMode.kPlus))
        body = skia.Path()
        body.moveTo(x - 50, y - 60)
        body.lineTo(x + 50, y - 60)
        body.lineTo(x + 40, y + 50)
        body.lineTo(x - 40, y + 50)
        body.close()
        c.drawPath(body, fill(col("#fff1b8", 0.4 + 0.5 * flick)))
        c.drawPath(body, stroke(col("#2f2a2a"), 6))
        c.drawCircle(x, y, 16, fill(col("#ffe08a", min(1.0, 0.3 + flick))))
        c.drawRect(skia.Rect.MakeXYWH(x - 60, y + 50, 120, 22), fill(col("#8a6a2a")))

    def draw_foreground(self, c: skia.Canvas, cam, env: EnvState):
        c.save()
        cam.apply(c, 1.0)
        for (x, y, ph) in self._dust:
            xx = x + math.sin(env.t * 0.3 + ph) * 40
            yy = y + math.cos(env.t * 0.25 + ph) * 30
            a = 0.25 + 0.2 * math.sin(env.t * 1.3 + ph)
            c.drawCircle(xx, yy, 3, fill(col("#fff3d0", a)))
        c.restore()


class Harbor(LighthouseCliff):
    """Martı village harbor. Reuses the coastal sky/sea backdrop of the cliff set."""

    def __init__(self, loc: dict[str, Any], lighting: str = "day"):
        super().__init__(loc, lighting)
        r = random.Random(loc.get("id", "harbor") + "h")
        self._houses = [(x, r.uniform(0.75, 1.2), r.choice(["#2f6fa8", "#3f8fb0", "#2a5d8a"]), r.random())
                        for x in range(-1200, int(STAGE_W) + 1400, 260)]

    def objects(self, view_w: float = 900.0):
        return {
            "yakamoz": (2350.0, GROUND_Y - 420, 0.85, 1500.0),
            "boat": (2350.0, GROUND_Y - 420, 0.85, 1500.0),
            "fishing_boats": (700.0, GROUND_Y - 330, 0.8, 1500.0),
            "village": (1600.0, HORIZON_Y - 300, 0.55, 2200.0),
            "lighthouse_far": (3000.0, HORIZON_Y - 160, 0.3, 900.0),
            "sea": (1600.0, HORIZON_Y + 60, 0.25, 2600.0),
            "nets": (1100.0, GROUND_Y - 60, 1.0, 900.0),
            "ground": (1500.0, GROUND_Y + 20, 1.0, 900.0),
        }

    def beam_intensity_at(self, env: EnvState, x: float) -> float:
        return 0.0

    def draw_foreground(self, c: skia.Canvas, cam, env: EnvState):
        import dataclasses
        super().draw_foreground(c, cam, dataclasses.replace(env, lamp=0.0))   # no lighthouse beam here

    def draw_set(self, c: skia.Canvas, cam, env: EnvState):
        t = env.t
        # far headland with the (tiny) lighthouse - visual continuity with the cliff set
        c.save()
        cam.apply(c, 0.3)
        hp = skia.Path()
        hp.moveTo(2500, HORIZON_Y + 4)
        hp.cubicTo(2700, HORIZON_Y - 120, 3200, HORIZON_Y - 150, 3700, HORIZON_Y + 4)
        hp.close()
        c.drawPath(hp, fill(col(shade(self.pal["grass"], 0.7))))
        lx, ly = 3000, HORIZON_Y - 125
        c.drawRect(skia.Rect.MakeXYWH(lx - 14, ly - 110, 28, 110), fill(col("#f4f1ea")))
        for k in range(2):
            c.drawRect(skia.Rect.MakeXYWH(lx - 14, ly - 100 + k * 50, 28, 22), fill(col("#c8382f")))
        if env.lamp > 0.05:
            g = skia.GradientShader.MakeRadial((lx, ly - 118), 60, [col("#fff3b0", 0.8 * env.lamp), col("#fff3b0", 0)])
            c.drawCircle(lx, ly - 118, 60, skia.Paint(AntiAlias=True, Shader=g))
        c.restore()
        # village on the hill
        c.save()
        cam.apply(c, 0.55)
        c.drawPicture(self._record("village", self._draw_village))
        c.restore()
        # moored boats (bobbing)
        c.save()
        cam.apply(c, 0.8)
        for k, bx in enumerate((300.0, 950.0)):
            self._fishing_boat(c, bx, GROUND_Y - 250 + math.sin(t * 1.1 + k) * 6, ["#d8423a", "#2f6fa8"][k], math.sin(t * 0.9 + k) * 1.5)
        c.restore()
        c.save()
        cam.apply(c, 0.85)
        self._yakamoz(c, 2350.0, GROUND_Y - 260 + math.sin(t * 0.8) * 7, math.sin(t * 0.7) * 1.2, env)
        c.restore()
        # pier
        c.save()
        cam.apply(c, 1.0)
        c.drawPicture(self._record("pier", self._draw_pier))
        c.restore()

    def _draw_village(self, c: skia.Canvas):
        hill = skia.Path()
        hill.moveTo(-1600, HORIZON_Y + 20)
        hill.cubicTo(0, HORIZON_Y - 330, 2400, HORIZON_Y - 360, STAGE_W + 1600, HORIZON_Y - 40)
        hill.lineTo(STAGE_W + 1600, HORIZON_Y + 200)
        hill.lineTo(-1600, HORIZON_Y + 200)
        hill.close()
        c.drawPath(hill, fill(col(shade(self.pal["grass"], 0.85))))
        for (x, s, shutter, r) in self._houses:
            u = (x + 1600) / (STAGE_W + 3200)
            base = HORIZON_Y + 30 - math.sin(u * math.pi) * 250 * (0.9 + 0.2 * r)
            w, h = 150 * s, 120 * s
            c.drawRect(skia.Rect.MakeXYWH(x - w / 2, base - h, w, h), fill(col("#f6f2ea")))
            c.drawRect(skia.Rect.MakeXYWH(x - w / 2, base - h, w, h), stroke(col("#9a8f80"), 3))
            roof = skia.Path()
            roof.moveTo(x - w / 2 - 10, base - h)
            roof.lineTo(x, base - h - 55 * s)
            roof.lineTo(x + w / 2 + 10, base - h)
            roof.close()
            c.drawPath(roof, fill(col("#c4623a")))
            for wx in (x - w * 0.25, x + w * 0.25):
                c.drawRect(skia.Rect.MakeXYWH(wx - 14 * s, base - h * 0.7, 28 * s, 34 * s), fill(col(shutter)))
            c.drawRect(skia.Rect.MakeXYWH(x - 12 * s, base - 50 * s, 24 * s, 50 * s), fill(col("#5c3a22")))
        # church/mosque dome landmark
        c.drawCircle(1700, HORIZON_Y - 300, 60, fill(col("#e9e3d6")))
        c.drawRect(skia.Rect.MakeXYWH(1640, HORIZON_Y - 300, 120, 90), fill(col("#e9e3d6")))

    def _draw_pier(self, c: skia.Canvas):
        top = GROUND_Y - 110
        stone = "#9a9086"
        sh = skia.GradientShader.MakeLinear([(0, top), (0, STAGE_H + 400)], [col(shade(stone, 1.1)), col(shade(stone, 0.6))])
        c.drawRect(skia.Rect.MakeLTRB(-1600, top, STAGE_W + 1600, STAGE_H + 900), skia.Paint(Shader=sh))
        rng = random.Random(5)
        for row in range(6):
            y = top + 30 + row * 70
            x = -1600 + (row % 2) * 90
            while x < STAGE_W + 1600:
                w = rng.uniform(140, 220)
                c.drawRoundRect(skia.Rect.MakeXYWH(x, y, w - 8, 62), 10, 10, stroke(col(shade(stone, 0.7)), 4))
                x += w
        c.drawRect(skia.Rect.MakeLTRB(-1600, top - 14, STAGE_W + 1600, top + 6), fill(col(shade(stone, 1.25))))
        # bollards + rope
        for bx in (420.0, 1850.0, 2700.0):
            c.drawRoundRect(skia.Rect.MakeXYWH(bx - 34, top - 90, 68, 100), 22, 22, fill(col("#2f2a2a")))
            c.drawRect(skia.Rect.MakeXYWH(bx - 46, top - 98, 92, 22), fill(col("#3d3636")))
        rope = skia.Path()
        rope.moveTo(2700, top - 60)
        rope.quadTo(2550, top - 150, 2420, top - 260)
        c.drawPath(rope, stroke(col("#c9a46a"), 9))
        # nets + crates + fish basket
        nx = 1100.0
        net = skia.Path()
        net.moveTo(nx - 180, top)
        net.cubicTo(nx - 120, top - 120, nx + 140, top - 130, nx + 200, top)
        net.close()
        c.drawPath(net, fill(col("#3f7a6a", 0.9)))
        for k in range(10):
            c.drawLine(nx - 170 + k * 38, top, nx - 120 + k * 30, top - 110, stroke(col("#2a4f45"), 3))
        for (ox, s) in ((-360, 1.0), (-250, 0.8)):
            w = 110 * s
            r = skia.Rect.MakeXYWH(nx + ox - w / 2, top - w, w, w)
            c.drawRect(r, fill(col("#a87445")))
            c.drawRect(r, stroke(col("#5a3a22"), 5))
        c.drawOval(skia.Rect.MakeXYWH(nx + 260, top - 70, 140, 80), fill(col("#c9a46a")))
        c.drawOval(skia.Rect.MakeXYWH(nx + 260, top - 70, 140, 80), stroke(col("#7a5a30"), 5))

    def _fishing_boat(self, c, x, y, color, tilt):
        c.save()
        c.rotate(tilt, x, y)
        hull = skia.Path()
        hull.moveTo(x - 230, y - 40)
        hull.lineTo(x + 230, y - 40)
        hull.quadTo(x + 210, y + 50, x + 150, y + 60)
        hull.lineTo(x - 160, y + 60)
        hull.quadTo(x - 220, y + 40, x - 230, y - 40)
        hull.close()
        c.drawPath(hull, fill(col("#f2ede2")))
        c.drawRect(skia.Rect.MakeXYWH(x - 230, y - 40, 460, 22), fill(col(color)))
        c.drawPath(hull, stroke(col("#2a1d1a"), 5))
        c.drawRect(skia.Rect.MakeXYWH(x - 60, y - 120, 120, 80), fill(col("#e8e0d0")))
        c.drawRect(skia.Rect.MakeXYWH(x - 60, y - 120, 120, 80), stroke(col("#2a1d1a"), 4))
        c.drawLine(x + 100, y - 40, x + 100, y - 260, stroke(col("#4a3226"), 7))
        c.restore()

    def _yakamoz(self, c, x, y, tilt, env: EnvState):
        """The mysterious red-sailed boat from episodes 1-2 (story object)."""
        c.save()
        c.rotate(tilt, x, y)
        hull = skia.Path()
        hull.moveTo(x - 330, y - 50)
        hull.lineTo(x + 360, y - 50)
        hull.quadTo(x + 330, y + 70, x + 240, y + 80)
        hull.lineTo(x - 240, y + 80)
        hull.quadTo(x - 320, y + 50, x - 330, y - 50)
        hull.close()
        c.drawPath(hull, fill(col("#2b3a55")))
        c.drawRect(skia.Rect.MakeXYWH(x - 330, y - 50, 690, 18), fill(col("#c9a227")))
        c.drawPath(hull, stroke(col("#14182a"), 6))
        font = skia.Font(skia.Typeface.MakeFromFile(_font()), 42)
        c.drawString("YAKAMOZ", x - 110, y + 30, font, fill(col("#f2e6c0")))
        c.drawLine(x, y - 50, x, y - 560, stroke(col("#4a3226"), 10))
        sail = skia.Path()
        sail.moveTo(x + 6, y - 550)
        sail.quadTo(x + 260, y - 330, x + 300, y - 80)
        sail.lineTo(x + 6, y - 80)
        sail.close()
        c.drawPath(sail, fill(col("#b8322a")))
        c.drawPath(sail, stroke(col("#5a1814"), 5))
        jib = skia.Path()
        jib.moveTo(x - 6, y - 520)
        jib.lineTo(x - 260, y - 70)
        jib.lineTo(x - 6, y - 70)
        jib.close()
        c.drawPath(jib, fill(col("#d24a3a")))
        c.drawPath(jib, stroke(col("#5a1814"), 5))
        # signal lantern on the mast (the light from episode 1)
        lg = 0.35 + 0.65 * env.boat_signal
        g = skia.GradientShader.MakeRadial((x, y - 575), 70, [col("#fff3b0", lg), col("#fff3b0", 0)])
        c.drawCircle(x, y - 575, 70, skia.Paint(AntiAlias=True, Shader=g))
        c.drawCircle(x, y - 575, 12, fill(col("#ffe08a")))
        c.restore()


def _font() -> str:
    from .config import font_path
    return font_path(True)


LOCATION_KINDS["lighthouse_room"] = LighthouseRoom
LOCATION_KINDS["harbor"] = Harbor
