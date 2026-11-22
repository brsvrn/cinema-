"""Frame renderer + per-shot encoder (economic 2D engine)."""
from __future__ import annotations

import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import skia

from . import config
from .camera import Camera, CamKey, handheld, lerp_key
from .location import EnvState, GROUND_Y
from .performance import Performance
from .rig import CharacterRig, col, fill, stroke, shade
from .storyboard import Shot


@dataclass
class RenderContext:
    location: Any                        # LighthouseCliff
    rigs: dict[str, CharacterRig]
    perf: Performance
    shots: list[Shot]
    duration: float
    captions: list[tuple[float, float, str]]
    title: tuple[str, str] | None = None  # (series, episode title)
    quality: str = "economic"             # economic | advanced


def _grade_filter(L: dict) -> skia.ColorFilter:
    gr, gg, gb = L["grade"]
    return skia.ColorFilters.Matrix([gr, 0, 0, 0, 0, 0, gg, 0, 0, 0, 0, 0, gb, 0, 0, 0, 0, 0, 1, 0])


def _char_filter(L: dict) -> skia.ColorFilter | None:
    k = L["amb_k"]
    if k <= 0:
        return None
    h = L["ambient"].lstrip("#")
    a = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    m = [1 - k + k * a[0], 1 - k + k * a[1], 1 - k + k * a[2]]
    return skia.ColorFilters.Matrix([m[0], 0, 0, 0, 0, 0, m[1], 0, 0, 0, 0, 0, m[2], 0, 0, 0, 0, 0, 1, 0])


class FrameRenderer:
    def __init__(self, ctx: RenderContext, out_w: int, out_h: int, burn_captions: bool):
        self.ctx = ctx
        self.w, self.h = out_w, out_h
        self.vertical = out_h > out_w
        self.cam = Camera(out_w, out_h)
        self.surface = skia.Surface(out_w, out_h)
        self.burn = burn_captions
        self.anchors: dict[str, tuple[float, float]] = {}
        self.face = skia.Typeface.MakeFromFile(config.font_path(True))
        self.face_r = skia.Typeface.MakeFromFile(config.font_path(False))
        L = ctx.location.L
        self.grade = _grade_filter(L)
        self.cfilter = _char_filter(L)
        # initial anchors
        for cid, rig in ctx.rigs.items():
            x, _ = ctx.perf.char_x(cid, 0.0)
            self.anchors[cid] = (x, GROUND_Y - rig.H * 0.88)

    def _env(self, t: float) -> EnvState:
        p = self.ctx.perf
        return EnvState(t=t, lamp=p.env_at("lamp", t), boat_signal=p.env_at("boat_signal", t),
                        rain=p.env_at("rain", t), fireflies=p.env_at("fireflies", t))

    def _camera_for(self, shot: Shot, t: float) -> CamKey:
        u = (t - shot.start) / max(1e-6, shot.end - shot.start)
        key = lerp_key(shot.cam_from, shot.cam_to, u)
        if self.vertical:
            # reframe: follow active speaker / subject inside the narrow frame
            target = None
            speaking = [cid for cid in self.ctx.rigs if any(s <= t < e for (s, e, _, _) in self.ctx.perf.chars[cid].lines)]
            if shot.subject in self.ctx.rigs:
                target = self.anchors.get(shot.subject, (key.cx, key.cy))[0]
            elif speaking:
                target = self.anchors[speaking[0]][0]
            if target is not None:
                key = CamKey(target, key.cy, key.view_w)
            # vertical frames show the same height; zoom a touch wider for wides
            if shot.kind in ("wide", "crane", "two"):
                key = CamKey(key.cx, key.cy, key.view_w * 0.9)
        return key

    def render(self, t: float, shot: Shot) -> np.ndarray:
        ctx = self.ctx
        c = self.surface.getCanvas()
        c.clear(skia.ColorBLACK)
        key = self._camera_for(shot, t)
        self.cam.set(key, handheld(t, shot.handheld * (key.view_w / 1600.0) * 2.5, seed=shot.index * 1.7))
        self.cam.flat = getattr(shot, "flat", False)
        env = self._env(t)
        L = ctx.location.L
        c.saveLayer(None, skia.Paint(ColorFilter=self.grade))
        dof = shot.dof * (self.h / 1080.0) if ctx.quality != "draft" else 0.0
        ctx.location.draw(c, self.cam, env, dof=dof)

        # characters (back to front by depth z)
        order = sorted(ctx.rigs.keys(), key=lambda cid: (ctx.perf.blocking[cid].get("z", 0.0),
                                                         1 if cid == shot.subject else 0))
        new_anchors = {}
        for cid in order:
            rig = ctx.rigs[cid]
            beam = ctx.location.beam_intensity_at(env, self.anchors.get(cid, (0, 0))[0])
            st, x, d, _ = ctx.perf.state(cid, t, self.anchors, beam=beam, rim_color=L["rim"])
            z = ctx.perf.blocking[cid].get("z", 0.0)
            scale = 1.0 + z * 0.35
            fg_blur = shot.kind == "ots" and cid == shot.other
            c.save()
            self.cam.apply(c, 1.0 + z * 0.15)
            paint = skia.Paint()
            if self.cfilter is not None:
                paint.setColorFilter(self.cfilter)
            if fg_blur:
                paint.setImageFilter(skia.ImageFilters.Blur(3.0, 3.0))
            c.saveLayer(None, paint)
            # soft contact shadow
            c.drawOval(skia.Rect.MakeXYWH(x - rig.H * 0.17 * scale, GROUND_Y + z * 120 - 14, rig.H * 0.34 * scale, 30),
                       fill(col("#000000", 0.22)))
            anchors = rig.draw(c, st, x, GROUND_Y + z * 120, scale, d)
            c.restore()
            c.restore()
            new_anchors[cid] = anchors["head"]
        self.anchors.update(new_anchors)

        ctx.location.draw_foreground(c, self.cam, env)
        c.restore()  # grade

        # vignette
        vg = skia.GradientShader.MakeRadial((self.w / 2, self.h / 2), max(self.w, self.h) * 0.75,
                                            [col("#000000", 0.0), col("#000000", 0.0), col("#000000", 0.42)],
                                            [0.0, 0.55, 1.0])
        c.drawRect(skia.Rect.MakeWH(self.w, self.h), skia.Paint(Shader=vg))
        # title card on the establishing shot
        if ctx.title and t < 3.2:
            self._title(c, t)
        if self.burn:
            self._caption(c, t)
        return self.surface.makeImageSnapshot().toarray()

    def _title(self, c, t):
        a = min(1.0, t / 0.5) * min(1.0, (3.2 - t) / 0.5)
        series, ep = self.ctx.title
        s = self.h / 1080.0 if not self.vertical else self.w / 1080.0
        f1 = skia.Font(self.face, 64 * s)
        f2 = skia.Font(self.face_r, 40 * s)
        y = self.h * (0.2 if not self.vertical else 0.16)
        for text, font, yy in ((series, f1, y), (ep, f2, y + 70 * s)):
            wdt = font.measureText(text)
            x = (self.w - wdt) / 2
            c.drawString(text, x + 3 * s, yy + 3 * s, font, fill(col("#000000", 0.5 * a)))
            c.drawString(text, x, yy, font, fill(col("#fff6e0", a)))

    def _caption(self, c, t):
        text = next((tx for (s, e, tx) in self.ctx.captions if s <= t < e), None)
        if not text:
            return
        s = self.w / 1080.0
        font = skia.Font(self.face, 54 * s)
        lines = textwrap.wrap(text, 24)
        y = self.h * 0.74
        for ln in lines:
            wdt = font.measureText(ln)
            x = (self.w - wdt) / 2
            c.drawString(ln, x, y, font, stroke(col("#000000"), 10 * s))
            c.drawString(ln, x, y, font, fill(col("#ffffff")))
            y += 66 * s


def encode_shot(ctx: RenderContext, shot: Shot, out: Path, w: int, h: int, burn_captions: bool,
                fps: int = config.FPS, renderer: FrameRenderer | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    r = renderer or FrameRenderer(ctx, w, h, burn_captions)
    f0 = int(round(shot.start * fps))
    f1 = int(round(shot.end * fps))
    tmp = out.with_suffix(".part.mp4")
    cmd = [config.ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-g", str(fps * 2), "-movflags", "+faststart", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    sub = 3 if ctx.quality == "advanced" else 1   # motion blur sub-frames (advanced mode)
    try:
        for fi in range(f0, f1):
            if sub == 1:
                frame = r.render(fi / fps, shot)
            else:
                acc = None
                for k in range(sub):
                    fr = r.render((fi + (k / sub - 0.5) * 0.5) / fps, shot).astype(np.uint16)
                    acc = fr if acc is None else acc + fr
                frame = (acc // sub).astype(np.uint8)
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed for shot {shot.index}")
    tmp.rename(out)
    return out


def still(ctx: RenderContext, shot: Shot, t: float, w: int, h: int, out_png: Path) -> Path:
    r = FrameRenderer(ctx, w, h, False)
    # warm up anchors
    r.render(max(shot.start, t - 0.1), shot)
    arr = r.render(t, shot)
    img = skia.Image.fromarray(arr, colorType=skia.kBGRA_8888_ColorType)
    img.save(str(out_png), skia.kPNG)
    return out_png
