"""Geometric safety checks.

Everything the add-in refuses (or warns about) is derived from the surface
model, not from magic numbers: radius of curvature of the sections and of the
meridian bound the wall thickness; the helix chord error bounds the number of
loft sections (and therefore the maximum twist); the wall tilt gives the
overhang angle.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .model import VaseModel, discretization, TAU, SAFETY
from .perforation import layout, effective_stagger, MIN_WEB


@dataclass
class Issue:
    level: str                       # "error" | "warn"
    code: str
    args: dict = field(default_factory=dict)


@dataclass
class Report:
    issues: List[Issue]
    metrics: Dict[str, float]

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------- scan
def scan(model: VaseModel, nu: int = 12, nth: int = 90) -> dict:
    p = model.p
    h = 2e-3
    rho_min, rho_min_u = float("inf"), 0.0
    wall_sec, ov_tan, top_open = float("inf"), 0.0, float("inf")
    for iu in range(nu + 1):
        u = iu / nu
        th0 = model.phi1(u)
        for k in range(nth):
            th = th0 + TAU * k / nth
            r = model.rho(th, u)
            r1, r0 = model.rho(th + h, u), model.rho(th - h, u)
            dr = (r1 - r0) / (2 * h)
            d2 = (r1 - 2 * r + r0) / (h * h)
            if r < rho_min:
                rho_min, rho_min_u = r, u
            kappa = (r * r + 2 * dr * dr - r * d2) / (r * r + dr * dr) ** 1.5
            g, fz, nh2 = model.tilt(th, u, r, dr)
            if kappa > 1e-9:
                wall_sec = min(wall_sec, SAFETY / (kappa * g))
            if fz > 0:
                ov_tan = max(ov_tan, fz / math.sqrt(nh2))
            if iu == nu:
                top_open = min(top_open, r - p.wall * g)

    # meridian curvature along the pattern-following rails
    wall_mer = float("inf")
    nz = 60
    dz = p.height / nz
    for j in range(6):
        thc = TAU * j / 6.0
        rc = [model.rho(thc + model.phi1(i / nz), i / nz) for i in range(nz + 1)]
        for i in range(1, nz):
            r1 = (rc[i + 1] - rc[i - 1]) / (2 * dz)
            r2 = (rc[i + 1] - 2 * rc[i] + rc[i - 1]) / (dz * dz)
            if r2 < -1e-9:
                wall_mer = min(wall_mer, SAFETY * (1 + r1 * r1) ** 1.5 / (-r2))
    return dict(rho_min=rho_min, rho_min_z=rho_min_u * p.height, wall_sec=wall_sec,
                wall_mer=wall_mer, overhang_deg=math.degrees(math.atan(ov_tan)),
                top_open=top_open)


# ------------------------------------------------------------------- inner check
def _poly_area(pts) -> float:
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return 0.5 * a


def _dist_pt_poly(pt, poly) -> float:
    best = float("inf")
    px, py = pt
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
        best = min(best, d)
    return best


def check_inner(model: VaseModel, m: int, n: int = 16) -> Optional[float]:
    """Explicitly build inner sections and look for folds. Returns the height (mm)
    of the first failing section, or None if the wall offset is clean."""
    p = model.p
    u0 = 0.0 if p.open_bottom else min(p.floor / p.height, 0.95)
    for i in range(n + 1):
        u = u0 + (1.0 - u0) * i / n
        out = model.section_outer(u, m)
        inn = model.section_inner(u, m, p.wall)
        for k in range(m):
            k2 = (k + 1) % m
            dox, doy = out[k2][0] - out[k][0], out[k2][1] - out[k][1]
            dix, diy = inn[k2][0] - inn[k][0], inn[k2][1] - inn[k][1]
            if dox * dix + doy * diy <= 0.0:
                return model.z(u)
        a_in, a_out = _poly_area(inn), _poly_area(out)
        if a_in <= 0.0 or a_in >= a_out:
            return model.z(u)
        for k in range(0, m, 3):                       # sampled distance test
            if _dist_pt_poly(inn[k], out) < 0.5 * p.wall:
                return model.z(u)
    return None


# --------------------------------------------------------------------- validation
def validate(p, fine: bool = False) -> Report:
    issues: List[Issue] = []
    metrics: Dict[str, float] = {}

    def add(level, code, **a):
        issues.append(Issue(level, code, a))

    if p.height < 20:
        add("error", "height_small")
    if min(p.base_radius, p.top_radius) < 8:
        add("error", "radius_small")
    if p.wall < 0.4:
        add("error", "wall_thin")
    if not p.open_bottom and p.floor < 0.4:
        add("error", "floor_thin")
    if p.floor > 0.5 * p.height:
        add("error", "floor_thick")
    if not (0.0 <= p.lobe_amp <= 0.9) or not (0.0 <= p.lobe2_amp <= 0.9):
        add("error", "amp_range")
    if abs(p.wave_amp) > 0.5:
        add("error", "amp_range")
    if p.shape == "polygon" and p.sides < 3:
        add("error", "sides_small")
    if any(i.level == "error" for i in issues):
        return Report(issues, metrics)

    model = VaseModel(p)
    s = scan(model, 24 if fine else 12, 240 if fine else 90)
    disc = discretization(p, model)
    metrics.update(s)
    metrics.update(disc)
    wall_max = min(s["wall_sec"], s["wall_mer"])
    metrics["wall_max"] = wall_max
    metrics["twist_max"] = math.degrees(math.radians(disc["dphi_max_deg"]) * (max(8, p.max_sections) - 1))

    if s["rho_min"] < p.wall + 3.0:
        add("error", "radius_collapse", rmin=s["rho_min"], z=s["rho_min_z"])
    if p.wall > wall_max:
        add("error", "wall_curv", wall=p.wall, wmax=wall_max)
    if s["top_open"] < 3.0:
        add("error", "closed_top", open=2 * s["top_open"])
    if p.base_hole_d > 0 and not p.open_bottom:
        if p.base_hole_d / 2.0 > 0.8 * (s["rho_min"] - p.wall):
            add("error", "base_hole")
    if s["overhang_deg"] > p.max_overhang:
        add("warn", "overhang", ang=s["overhang_deg"], lim=p.max_overhang)
    if disc["capped"]:
        add("warn", "sections_capped", need=disc["n_needed"], tol=p.chord_tol,
            cap=max(8, p.max_sections), tw=metrics["twist_max"])
    if p.n_sections > 0 and p.n_sections < disc["n_needed"]:
        add("warn", "sections_low", need=disc["n_needed"], have=p.n_sections)

    _check_perf(p, model, issues, metrics)

    if fine and p.wall <= wall_max and not any(i.level == "error" for i in issues):
        z_bad = check_inner(model, disc["n_points"])
        if z_bad is not None:
            add("error", "inner_fold", z=z_bad)
    return Report(issues, metrics)


def _check_perf(p, model, issues, metrics):
    pp = p.perf
    if not pp.enabled:
        return

    def add(level, code, **a):
        issues.append(Issue(level, code, a))

    if pp.z_end <= pp.z_start + 0.02 or pp.z_start < 0 or pp.z_end > 1:
        add("error", "perf_range")
        return
    if not (0.1 <= pp.fill <= 0.9) or pp.count < 3 or pp.rows < 1:
        add("error", "perf_fill")
        return
    rows = layout(model, p)
    pitch = min(r.pitch for r in rows)
    size = min(r.size for r in rows)
    hh = max(r.height for r in rows)
    metrics["perf_pitch"] = pitch
    metrics["perf_size"] = size
    web = min(r.pitch - r.size for r in rows)
    if web < MIN_WEB:
        add("error", "perf_web", web=web)
    if pp.rows > 1:
        sp = (pp.z_end - pp.z_start) * p.height / (pp.rows - 1)
        need = hh + MIN_WEB
        stg = effective_stagger(pp)
        ok = (2 * sp >= need) if stg else (sp >= need)
        if stg:
            ok = ok and math.hypot(pitch / 2.0, sp) >= 0.5 * (size + hh) + MIN_WEB
        if not ok:
            add("error", "perf_rows", sp=sp, h=hh)
    z_bottom = rows[0].z - rows[0].height / 2.0
    floor = 0.0 if p.open_bottom else p.floor
    if z_bottom < floor + 1.0:
        add("error", "perf_floor")
    if rows[-1].z + rows[-1].height / 2.0 > p.height - 2.0:
        add("error", "perf_range")


# ------------------------------------------------------------------------ limits
def _is_valid(p) -> bool:
    return validate(p).ok


def max_lobe_amp(p, iters: int = 7) -> Optional[float]:
    """Largest lobe amplitude (layer 1) that still passes validation, by bisection."""
    if p.lobes <= 0:
        return None
    lo, hi = 0.0, 0.9
    if _is_valid(p.copy(lobe_amp=hi)):
        return hi
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if _is_valid(p.copy(lobe_amp=mid)):
            lo = mid
        else:
            hi = mid
    return lo


def compute_limits(p) -> dict:
    model = VaseModel(p)
    s = scan(model, 10, 80)
    disc = discretization(p, model)
    cap = max(8, p.max_sections)
    return dict(
        wall=min(s["wall_sec"], s["wall_mer"]),
        twist=math.degrees(math.radians(disc["dphi_max_deg"]) * (cap - 1)),
        lobe_amp=max_lobe_amp(p),
        n_sections=disc["n_sections"], n_points=disc["n_points"],
    )
