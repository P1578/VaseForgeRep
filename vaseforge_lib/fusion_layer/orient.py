"""Decide which world axis is the vase axis."""
from __future__ import annotations

import adsk.core

from ..core.frame import Frame


def resolve(app, up_axis: str = "auto") -> Frame:
    if up_axis in ("y", "z"):
        return Frame(up_axis)
    try:
        orient = app.preferences.generalPreferences.defaultModelingOrientation
        if orient == adsk.core.DefaultModelingOrientations.YUpModelingOrientation:
            return Frame("y")
    except Exception:
        pass
    return Frame("z")
