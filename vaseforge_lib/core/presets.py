"""Starting points. Every preset must pass validation (see tests)."""
from __future__ import annotations

from .params import VaseParams

PRESETS = {
    "cylinder": {},
    "tumbler": dict(height=110, base_radius=30, top_radius=38),
    "amphora": dict(height=200, base_radius=28, top_radius=30, belly_amount=0.55,
                    belly_pos=0.40, belly_width=0.22, neck_amount=-0.40,
                    neck_pos=0.86, neck_width=0.10),
    "bud_vase": dict(height=180, base_radius=30, top_radius=16, belly_amount=0.30,
                     belly_pos=0.30, belly_width=0.22),
    "bowl": dict(height=70, base_radius=30, top_radius=75, belly_amount=0.25,
                 belly_pos=0.35, belly_width=0.30),
    "twisted_tower": dict(height=180, base_radius=38, top_radius=38, shape="polygon",
                          sides=5, corner_round=0.35, twist=120),
    "fluted_column": dict(height=160, base_radius=40, top_radius=44, lobes=12,
                          lobe_amp=0.06),
    "diamond_lattice": dict(height=170, base_radius=40, top_radius=40, lobes=8,
                            lobe_amp=0.05, twist=90, lobes2=8, lobe2_amp=0.05,
                            twist2=-90),
    "ripple": dict(height=180, base_radius=40, top_radius=40, wave_amp=0.08,
                   wave_count=6),
    "lampshade": dict(height=160, base_radius=70, top_radius=35, lobes=6,
                      lobe_amp=0.08, twist=60, open_bottom=True),
    "perforated_hex": dict(height=150, base_radius=40, top_radius=40,
                           perf=dict(enabled=True, shape="hexagon", count=14,
                                     rows=10, fill=0.6, z_start=0.15, z_end=0.90)),
}
ORDER = list(PRESETS.keys())


def make(key: str) -> VaseParams:
    return VaseParams.from_dict(dict(PRESETS.get(key, {})))
