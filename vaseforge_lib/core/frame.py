"""Maps vase-model coordinates (axis = +Z) to Fusion world coordinates.

Y-up documents use a proper rotation of -90 degrees about X:
(x, y, z) -> (x, z, -y). Lengths and handedness are preserved."""
from __future__ import annotations


class Frame:
    def __init__(self, up: str = "z"):
        self.up = "y" if str(up).lower() == "y" else "z"

    def world(self, x: float, y: float, z: float):
        return (x, y, z) if self.up == "z" else (x, z, -y)

    vec = world          # directions transform exactly like points here
