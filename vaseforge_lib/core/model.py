"""Pure-math model of the vase surface (no Fusion dependency, stdlib only).

The outer surface is described in cylindrical coordinates:

    rho(theta, u) = R(u) * wave(u) * S(theta - phi1(u))
                    * (1 + A1(u) cos(N1 (theta - phi1(u))))
                    * (1 + A2    cos(N2 (theta - phi2(u))))

with u in [0, 1] the normalised height. Every horizontal section is a
star-shaped polar curve (rho > 0), and sections sit on strictly increasing z,
so the *outer* surface can never intersect itself. What can go wrong is
(a) the section degenerating, (b) the inward wall offset folding over itself,
(c) the loft cutting corners between sections. validate.py checks all three.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from .params import VaseParams

TAU = 2.0 * math.pi
SAFETY = 0.90        # keep wall below 90 % of the local radius of curvature
MAX_TILT = 4.0       # cap on the 1/cos(tilt) horizontal wall stretch

Point = Tuple[float, float]


def _smoothstep(u: float) -> float:
    return u * u * (3.0 - 2.0 * u)


class VaseModel:
    def __init__(self, params: VaseParams):
        self.p = params
        self._polygon = params.shape == "polygon" and params.sides >= 3
        cr = min(max(params.corner_round, 0.0), 1.0)
        self._pw = 2.0 + (1.0 - cr) ** 2 * 38.0           # p-norm exponent
        self._pn = self._poly_sum(0.0) ** (1.0 / self._pw) if self._polygon else 1.0

    # ------------------------------------------------------------------ profile
    def z(self, u: float) -> float:
        return self.p.height * u

    def _bump(self, u: float, pos: float, width: float) -> float:
        w = max(width, 1e-3)
        e = lambda x: math.exp(-((x - pos) / w) ** 2)
        return e(u) - ((1.0 - u) * e(0.0) + u * e(1.0))   # exact radii at both ends

    def radius(self, u: float) -> float:
        p = self.p
        lin = p.base_radius + (p.top_radius - p.base_radius) * u
        g = 1.0
        if p.belly_amount:
            g += p.belly_amount * self._bump(u, p.belly_pos, p.belly_width)
        if p.neck_amount:
            g += p.neck_amount * self._bump(u, p.neck_pos, p.neck_width)
        return lin * g

    def wave(self, u: float) -> float:
        p = self.p
        if p.wave_count > 0 and p.wave_amp:
            return 1.0 + p.wave_amp * math.sin(TAU * p.wave_count * u)
        return 1.0

    def amp1(self, u: float) -> float:
        p = self.p
        return p.lobe_amp * (1.0 + (p.lobe_top_factor - 1.0) * u)

    def ease(self, u: float) -> float:
        return _smoothstep(u) if self.p.twist_ease == "smooth" else u

    def phi1(self, u: float) -> float:
        return math.radians(self.p.twist) * self.ease(u)

    def phi2(self, u: float) -> float:
        return math.radians(self.p.twist2) * self.ease(u)

    # ------------------------------------------------------------------ section
    def _poly_sum(self, t: float) -> float:
        n = self.p.sides
        s = 0.0
        for i in range(n):
            c = math.cos(t - TAU * (i + 0.5) / n)
            if c > 0.0:
                s += c ** self._pw
        return s

    def shape(self, t: float) -> float:
        """Unit-circumradius smooth polygon (p-norm of face distances)."""
        if not self._polygon:
            return 1.0
        return self._pn / self._poly_sum(t) ** (1.0 / self._pw)

    def rho(self, th: float, u: float) -> float:
        p = self.p
        t1 = th - self.phi1(u)
        r = self.radius(u) * self.wave(u) * self.shape(t1)
        if p.lobes > 0 and p.lobe_amp:
            r *= 1.0 + self.amp1(u) * math.cos(p.lobes * t1)
        if p.lobes2 > 0 and p.lobe2_amp:
            r *= 1.0 + p.lobe2_amp * math.cos(p.lobes2 * (th - self.phi2(u)))
        return r

    def drho(self, th: float, u: float, h: float = 1e-3) -> float:
        return (self.rho(th + h, u) - self.rho(th - h, u)) / (2.0 * h)

    def curvature(self, th: float, u: float, h: float = 1e-3) -> float:
        """Signed curvature of the horizontal section (+ = convex)."""
        r, r1, r0 = self.rho(th, u), self.rho(th + h, u), self.rho(th - h, u)
        dr = (r1 - r0) / (2 * h)
        d2 = (r1 - 2 * r + r0) / (h * h)
        return (r * r + 2 * dr * dr - r * d2) / (r * r + dr * dr) ** 1.5

    def tilt(self, th: float, u: float, r: float, dr: float):
        """Return (g, fz, nh2): g = 1/cos(wall tilt) capped, fz = d rho/dz at fixed
        world angle, nh2 = 1 + (rho'/rho)^2 (horizontal normal magnitude^2)."""
        hu = 1e-3
        u1, u0 = min(u + hu, 1.0), max(u - hu, 0.0)
        fz = (self.rho(th, u1) - self.rho(th, u0)) / ((u1 - u0) * self.p.height)
        nh2 = 1.0 + (dr / r) ** 2
        g = math.sqrt(1.0 + fz * fz / nh2)
        return min(g, MAX_TILT), fz, nh2

    def max_radius(self) -> float:
        p = self.p
        amp = ((1 + abs(p.lobe_amp) * max(1.0, p.lobe_top_factor))
               * (1 + abs(p.lobe2_amp)) * (1 + abs(p.wave_amp)))
        return max(self.radius(i / 24.0) for i in range(25)) * amp

    # ----------------------------------------------------------------- sampling
    def section_outer(self, u: float, m: int) -> List[Point]:
        """m points, evenly spaced in angle, starting at the twist angle so that
        loft rails follow the helix of the pattern."""
        th0 = self.phi1(u)
        out = []
        for k in range(m):
            th = th0 + TAU * k / m
            r = self.rho(th, u)
            out.append((r * math.cos(th), r * math.sin(th)))
        return out

    def section_inner(self, u: float, m: int, wall: float) -> List[Point]:
        """Same angles as section_outer, offset inward so that the wall measured
        *perpendicular to the surface* equals `wall` (horizontal offset = wall/cos(tilt))."""
        th0 = self.phi1(u)
        out = []
        for k in range(m):
            th = th0 + TAU * k / m
            r = self.rho(th, u)
            dr = self.drho(th, u)
            c, s = math.cos(th), math.sin(th)
            tx, ty = dr * c - r * s, dr * s + r * c
            ln = math.hypot(tx, ty)
            nx, ny = ty / ln, -tx / ln                      # outward normal (CCW curve)
            g, _, _ = self.tilt(th, u, r, dr)
            d = wall * g
            out.append((r * c - d * nx, r * s - d * ny))
        return out


# ---------------------------------------------------------------------------
def discretization(p: VaseParams, model: VaseModel = None) -> dict:
    """Choose number of loft sections / points per section from an error budget.

    A loft chord between consecutive sections cuts the helix of radius R by
    R*dphi^2/8, so dphi <= sqrt(8*tol/R). Counter-rotating layer 2 moves relative
    to the rails: error ~ A2*R*(N2*dphi_rel)^2/8.
    """
    model = model or VaseModel(p)
    R = max(model.max_radius(), 1.0)
    tol = max(p.chord_tol, 0.01)
    dphi = math.sqrt(8.0 * tol / R)
    need = 2.0
    ease = 1.5 if p.twist_ease == "smooth" else 1.0
    need = max(need, abs(math.radians(p.twist)) * ease / dphi)
    if p.lobes2 > 0 and p.lobe2_amp > 0:
        rel = abs(math.radians(p.twist2 - p.twist)) * ease
        dphi2 = math.sqrt(8.0 * tol / (p.lobe2_amp * R)) / p.lobes2
        need = max(need, rel / dphi2)
    if p.wave_count > 0 and p.wave_amp:
        need = max(need, 12.0 * p.wave_count)
    widths = [w for a, w in ((p.belly_amount, p.belly_width), (p.neck_amount, p.neck_width)) if a]
    if widths:
        need = max(need, 2.5 / max(min(widths), 1e-3))
    n_needed = int(math.ceil(need)) + 1
    cap = max(8, p.max_sections)
    n = p.n_sections if p.n_sections > 0 else min(n_needed, cap)
    n = max(n, 2)

    m = 72
    if p.lobes > 0:
        m = max(m, 16 * p.lobes)
    if p.lobes2 > 0:
        m = max(m, 16 * p.lobes2)
    if model._polygon:
        m = max(m, 24 * p.sides)
    m = min(m, 360)
    if p.lobes > 0:
        m = int(math.ceil(m / p.lobes) * p.lobes)         # keep the lobes symmetric
    if p.n_points > 0:
        m = p.n_points
    return dict(n_sections=n, n_points=m, n_needed=n_needed,
                capped=(p.n_sections == 0 and n_needed > cap),
                dphi_max_deg=math.degrees(dphi), R=R)
