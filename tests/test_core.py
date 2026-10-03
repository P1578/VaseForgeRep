import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from vaseforge_lib.core.params import VaseParams
from vaseforge_lib.core.model import VaseModel, discretization, TAU
from vaseforge_lib.core import presets
from vaseforge_lib.core.validate import validate, compute_limits, check_inner, scan
from vaseforge_lib.core.perforation import layout, hole_outline


def codes(rep, level=None):
    return {i.code for i in rep.issues if level is None or i.level == level}


def test_params_roundtrip():
    p = presets.make("perforated_hex")
    q = VaseParams.from_json(p.to_json())
    assert q == p and q.perf.enabled


def test_polygon_circumradius_is_one():
    p = VaseParams(shape="polygon", sides=6, corner_round=0.2)
    m = VaseModel(p)
    vals = [m.shape(TAU * k / 720) for k in range(720)]
    assert max(vals) == pytest.approx(1.0, abs=1e-3)
    assert min(vals) > 0.8          # hexagon apothem = cos(30deg) = 0.866


def test_profile_hits_exact_end_radii():
    p = VaseParams(base_radius=30, top_radius=50, belly_amount=0.4, neck_amount=-0.3)
    m = VaseModel(p)
    assert m.radius(0.0) == pytest.approx(30)
    assert m.radius(1.0) == pytest.approx(50)


def test_lobe_curvature_matches_closed_form():
    # rho = R(1 + A cos(N theta)) -> at a lobe tip: k = (1 + A(1+N^2)) / (R (1+A)^2)
    R, A, N = 40.0, 0.06, 8
    m = VaseModel(VaseParams(base_radius=R, top_radius=R, lobes=N, lobe_amp=A))
    k_num = m.curvature(0.0, 0.5)
    k_ref = (1 + A * (1 + N * N)) / (R * (1 + A) ** 2)
    assert k_num == pytest.approx(k_ref, rel=1e-3)


def test_wall_limit_matches_lobe_tip_radius():
    R, A, N = 40.0, 0.06, 8
    p = VaseParams(base_radius=R, top_radius=R, lobes=N, lobe_amp=A)
    wmax = compute_limits(p)["wall"]
    ref = 0.9 * R * (1 + A) ** 2 / (1 + A * (1 + N * N))
    assert wmax == pytest.approx(ref, rel=0.02)


def test_cylinder_is_valid_and_simple():
    rep = validate(presets.make("cylinder"), fine=True)
    assert rep.ok and not rep.issues
    d = discretization(presets.make("cylinder"))
    assert d["n_sections"] <= 4


@pytest.mark.parametrize("key", presets.ORDER)
def test_all_presets_pass_fine_validation(key):
    rep = validate(presets.make(key), fine=True)
    assert rep.ok, [(i.code, i.args) for i in rep.errors]


def test_thick_wall_is_rejected_with_numeric_limit():
    p = VaseParams(lobes=10, lobe_amp=0.1, wall=6.0)
    rep = validate(p)
    assert "wall_curv" in codes(rep, "error")
    wmax = [i for i in rep.issues if i.code == "wall_curv"][0].args["wmax"]
    assert validate(p.copy(wall=wmax * 0.98)).ok


def test_lobe_amp_limit_is_tight():
    p = VaseParams(lobes=12, lobe_amp=0.02, wall=2.0)
    a = compute_limits(p)["lobe_amp"]
    assert 0.0 < a < 0.9
    assert validate(p.copy(lobe_amp=a)).ok
    assert not validate(p.copy(lobe_amp=min(0.9, a + 0.05))).ok


def test_sections_grow_with_twist_and_cap_warns():
    base = VaseParams(base_radius=40, top_radius=40)
    n0 = discretization(base.copy(twist=45))["n_needed"]
    n1 = discretization(base.copy(twist=360))["n_needed"]
    assert n1 > n0
    rep = validate(base.copy(twist=3000, shape="polygon", sides=5))
    assert "sections_capped" in codes(rep, "warn")


def test_twist_limit_is_consistent_with_cap():
    p = VaseParams(base_radius=40, top_radius=40, max_sections=60)
    tmax = compute_limits(p)["twist"]
    ok = validate(p.copy(twist=tmax * 0.95))
    over = validate(p.copy(twist=tmax * 1.3))
    assert "sections_capped" not in codes(ok)
    assert "sections_capped" in codes(over)


def test_inner_sections_circle_is_exact():
    p = VaseParams(base_radius=40, top_radius=40, wall=1.5)
    m = VaseModel(p)
    inn = m.section_inner(0.5, 90, p.wall)
    assert all(math.hypot(x, y) == pytest.approx(38.5, abs=1e-6) for x, y in inn)


def test_tilt_compensation_keeps_normal_thickness():
    # A 45-degree cone: horizontal wall must be wall * sqrt(2)
    p = VaseParams(height=50, base_radius=20, top_radius=70, wall=2.0)
    m = VaseModel(p)
    out = m.section_outer(0.5, 90)
    inn = m.section_inner(0.5, 90, p.wall)
    dh = math.hypot(*out[0]) - math.hypot(*inn[0])
    assert dh == pytest.approx(2.0 * math.sqrt(2.0), rel=1e-3)


def test_overhang_reported_for_cone_not_cylinder():
    cyl = scan(VaseModel(VaseParams()))
    cone = scan(VaseModel(VaseParams(height=50, base_radius=20, top_radius=70)))
    assert cyl["overhang_deg"] < 1.0
    assert cone["overhang_deg"] == pytest.approx(45.0, abs=1.5)


def test_collapse_and_closed_top_detected():
    rep = validate(VaseParams(base_radius=20, top_radius=20, wave_count=3, wave_amp=0.5, lobes=6, lobe_amp=0.9))
    assert "radius_collapse" in codes(rep, "error") or "wall_curv" in codes(rep, "error")
    rep = validate(VaseParams(base_radius=30, top_radius=8.5, wall=5.6))
    assert "closed_top" in codes(rep, "error") or "radius_collapse" in codes(rep, "error")


def test_perforation_rules():
    p = presets.make("perforated_hex")
    assert validate(p).ok
    bad = p.copy(perf=dict(p.perf.__dict__, fill=0.9, count=40))
    assert "perf_web" in codes(validate(bad), "error")
    bad2 = p.copy(perf=dict(p.perf.__dict__, rows=40))
    assert "perf_rows" in codes(validate(bad2), "error")
    rows = layout(VaseModel(p), p)
    assert len(rows) == p.perf.rows and rows[0].z < rows[-1].z


def test_hole_outlines():
    kind, r = hole_outline("circle", 10)
    assert kind == "circle" and r == 5
    for s in ("hexagon", "diamond", "slot"):
        kind, pts = hole_outline(s, 10, 2.0)
        assert kind == "poly" and len(pts) >= 4
    kind, pts = hole_outline("hexagon", 10)
    xs = [x for x, _ in pts]
    assert max(xs) - min(xs) == pytest.approx(10.0)       # flat-to-flat == size


def test_inner_check_flags_overthick_wall_if_validation_bypassed():
    p = VaseParams(lobes=10, lobe_amp=0.1, wall=8.0)
    assert check_inner(VaseModel(p), 200) is not None


def test_frame_is_a_proper_rotation():
    from vaseforge_lib.core.frame import Frame
    f = Frame("y")
    assert f.world(1, 2, 3) == (1, 3, -2)
    # vase axis (+Z in model space) must become +Y in a Y-up document
    assert f.world(0, 0, 1) == (0, 1, 0)
    # lengths preserved
    x, y, z = f.world(3, 4, 12)
    assert math.sqrt(x * x + y * y + z * z) == pytest.approx(13.0)
    # right-handed: x cross y == z  ->  in world coordinates too
    ex, ey = f.world(1, 0, 0), f.world(0, 1, 0)
    cross = (ex[1] * ey[2] - ex[2] * ey[1], ex[2] * ey[0] - ex[0] * ey[2], ex[0] * ey[1] - ex[1] * ey[0])
    assert cross == f.world(0, 0, 1)
    assert Frame("z").world(1, 2, 3) == (1, 2, 3)
