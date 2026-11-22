"""Virtual camera with parallax, framing presets, moves and handheld noise."""
from __future__ import annotations

import math
from dataclasses import dataclass

import skia

from .location import STAGE_W, STAGE_H


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


@dataclass
class CamKey:
    cx: float
    cy: float
    view_w: float   # stage units visible horizontally (for the 16:9 frame)


class Camera:
    def __init__(self, out_w: int, out_h: int):
        self.out_w = out_w
        self.out_h = out_h
        self.cx = STAGE_W / 2
        self.cy = STAGE_H / 2
        self.view_w = STAGE_W
        self.shake = (0.0, 0.0)
        self.flat = False

    @property
    def scale(self) -> float:
        # For vertical outputs keep the same *height* coverage as the 16:9 framing so
        # characters stay the same size; the frame is simply narrower.
        ref_h = self.view_w * 9 / 16
        return self.out_h / ref_h

    def set(self, key: CamKey, shake=(0.0, 0.0)):
        self.cx, self.cy, self.view_w = key.cx, key.cy, key.view_w
        self.shake = shake

    def _layer(self, p: float):
        anchor_x, anchor_y = STAGE_W / 2, STAGE_H / 2
        ex = anchor_x + (self.cx - anchor_x) * p + self.shake[0] * p
        ey = anchor_y + (self.cy - anchor_y) * p + self.shake[1] * p
        wide = self.out_h / (STAGE_W * 9 / 16) * 0.92
        s = wide + (self.scale - wide) * min(1.0, p)
        if self.flat and p <= 1.0:
            s = self.scale
        if p > 1.0:
            s = self.scale * (1 + (p - 1) * 0.5)
        return ex, ey, s

    def apply(self, c: skia.Canvas, p: float = 1.0):
        ex, ey, s = self._layer(p)
        c.translate(self.out_w / 2, self.out_h / 2)
        c.scale(s, s)
        c.translate(-ex, -ey)

    def world_to_screen_y(self, y: float, p: float = 1.0) -> float:
        ex, ey, s = self._layer(p)
        return (y - ey) * s + self.out_h / 2

    def world_to_screen(self, x: float, y: float, p: float = 1.0) -> tuple[float, float]:
        ex, ey, s = self._layer(p)
        return (x - ex) * s + self.out_w / 2, (y - ey) * s + self.out_h / 2


def handheld(t: float, amount: float, seed: float = 0.0) -> tuple[float, float]:
    if amount <= 0:
        return (0.0, 0.0)
    x = (math.sin(t * 0.9 + seed) + 0.5 * math.sin(t * 2.3 + seed * 2) + 0.25 * math.sin(t * 5.1 + seed)) * amount
    y = (math.sin(t * 1.1 + seed * 3) + 0.5 * math.sin(t * 2.9 + seed) + 0.2 * math.sin(t * 4.7)) * amount * 0.6
    return (x, y)


def lerp_key(a: CamKey, b: CamKey, t: float) -> CamKey:
    e = ease(t)
    return CamKey(a.cx + (b.cx - a.cx) * e, a.cy + (b.cy - a.cy) * e, a.view_w + (b.view_w - a.view_w) * e)
