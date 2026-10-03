"""Perforation layout: where each row of holes goes and what it looks like.
Pure math, shared by the validator and the Fusion builder."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from .model import VaseModel, TAU

MIN_WEB = 1.2   # mm of material that must remain between holes (~3 nozzle lines)


@dataclass
class Row:
    z: float            # hole centre height, mm
    theta: float        # angle of the first hole in this row, rad
    r_mid: float        # mid-wall radius at that angle, mm
    wall_h: float       # horizontal wall thickness there, mm
    pitch: float        # arc distance between holes, mm
    size: float         # hole width (tangential), mm
    height: float       # hole height (vertical), mm


def effective_stagger(pp) -> bool:
    """Staggered rows need >= 6 holes per row; with fewer, the half-pitch shift is too large
    for the straight (non-radial) cutters used in the parametric build."""
    return bool(pp.stagger and pp.count >= 6)


def hole_height(shape: str, size: float, aspect: float) -> float:
    if shape == "slot":
        return size * max(aspect, 1.0)
    if shape == "hexagon":
        return size * 2.0 / math.sqrt(3.0)
    return size


def layout(model: VaseModel, p) -> List[Row]:
    pp = p.perf
    H = p.height
    rows = max(pp.rows, 1)
    z0, z1 = pp.z_start * H, pp.z_end * H
    out = []
    for j in range(rows):
        z = 0.5 * (z0 + z1) if rows == 1 else z0 + (z1 - z0) * j / (rows - 1)
        u = z / H
        th = (math.pi / pp.count) if (effective_stagger(pp) and j % 2 == 1) else 0.0
        r = model.rho(th, u)
        dr = model.drho(th, u)
        g, _, _ = model.tilt(th, u, r, dr)
        d = p.wall * g
        r_mid = r - d / 2.0
        pitch = TAU * r_mid / pp.count
        size = pp.fill * pitch
        out.append(Row(z, th, r_mid, d, pitch, size, hole_height(pp.shape, size, pp.slot_aspect)))
    return out


def hole_outline(shape: str, size: float, aspect: float = 2.0):
    """Local 2-D outline (a = tangential, b = vertical). Returns ('circle', radius)
    or ('poly', [(a, b), ...]) in counter-clockwise order."""
    if shape == "circle":
        return "circle", size / 2.0
    if shape == "hexagon":
        R = size / math.sqrt(3.0)
        return "poly", [(R * math.cos(math.radians(90 + 60 * k)),
                         R * math.sin(math.radians(90 + 60 * k))) for k in range(6)]
    if shape == "diamond":
        h = size / 2.0
        return "poly", [(h, 0.0), (0.0, h), (-h, 0.0), (0.0, -h)]
    if shape == "slot":
        w = size / 2.0
        h = size * max(aspect, 1.0) / 2.0
        cy = max(h - w, 0.0)
        pts: List[Tuple[float, float]] = []
        for k in range(0, 9):                      # top semicircle
            a = math.radians(k * 180.0 / 8)
            pts.append((w * math.cos(a), cy + w * math.sin(a)))
        for k in range(0, 9):                      # bottom semicircle
            a = math.radians(180 + k * 180.0 / 8)
            pts.append((w * math.cos(a), -cy + w * math.sin(a)))
        return "poly", pts
    raise ValueError(shape)
