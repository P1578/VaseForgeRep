"""Parameter containers. Units: millimetres, degrees, fractions (0.1 == 10 %)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields
from typing import Any, Dict


@dataclass
class PerforationParams:
    enabled: bool = False
    shape: str = "circle"        # circle | hexagon | diamond | slot
    count: int = 12              # holes per row
    rows: int = 6
    fill: float = 0.5            # hole width as a fraction of the local pitch
    z_start: float = 0.15        # fraction of height
    z_end: float = 0.90
    stagger: bool = True
    slot_aspect: float = 2.0     # slot height / width


@dataclass
class VaseParams:
    # ---- profile -------------------------------------------------------
    height: float = 150.0
    base_radius: float = 40.0
    top_radius: float = 40.0
    belly_pos: float = 0.45
    belly_amount: float = 0.0    # +0.3 = 30 % wider at the belly
    belly_width: float = 0.25
    neck_pos: float = 0.85
    neck_amount: float = 0.0     # -0.3 = 30 % narrower at the neck
    neck_width: float = 0.12
    # ---- cross-section -------------------------------------------------
    shape: str = "circle"        # circle | polygon
    sides: int = 6
    corner_round: float = 0.5    # 0 = sharp, 1 = nearly round
    # ---- layer 1: lobes + twist ---------------------------------------
    lobes: int = 0
    lobe_amp: float = 0.0
    lobe_top_factor: float = 1.0  # amplitude at the top relative to the base
    twist: float = 0.0            # total degrees base -> top
    twist_ease: str = "linear"    # linear | smooth
    # ---- layer 2: counter lobes (diamond / lattice looks) ---------------
    lobes2: int = 0
    lobe2_amp: float = 0.0
    twist2: float = 0.0
    # ---- vertical waves -------------------------------------------------
    wave_amp: float = 0.0
    wave_count: int = 0
    # ---- wall -----------------------------------------------------------
    wall: float = 1.2
    floor: float = 1.6
    open_bottom: bool = False     # lampshade mode
    base_hole_d: float = 0.0      # 0 = none
    # ---- quality / safety ----------------------------------------------
    n_sections: int = 0           # 0 = automatic
    n_points: int = 0             # 0 = automatic
    chord_tol: float = 0.08       # mm, loft accuracy target
    max_sections: int = 90
    max_overhang: float = 55.0    # degrees, warning threshold only
    up_axis: str = "auto"         # auto | z | y  (vase axis in the Fusion document)
    # ---- perforations ---------------------------------------------------
    perf: PerforationParams = field(default_factory=PerforationParams)

    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VaseParams":
        d = dict(d)
        perf_d = d.pop("perf", {}) or {}
        known = {f.name for f in fields(cls)}
        p = cls(**{k: v for k, v in d.items() if k in known and k != "perf"})
        pknown = {f.name for f in fields(PerforationParams)}
        p.perf = PerforationParams(**{k: v for k, v in perf_d.items() if k in pknown})
        return p

    @classmethod
    def from_json(cls, s: str) -> "VaseParams":
        return cls.from_dict(json.loads(s))

    def copy(self, **kw) -> "VaseParams":
        d = self.to_dict()
        d.update(kw)
        return VaseParams.from_dict(d)
