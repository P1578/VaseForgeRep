"""Cheap wireframe preview in the viewport (custom graphics).

Never raises; problems are written to Fusion's Text Commands window so they can
be diagnosed. Every group we create carries a fixed id, and clear() removes all
groups with that id, so a stale drawing can never be left behind."""
from __future__ import annotations

import array
import traceback

import adsk.core
import adsk.fusion

from ..core.model import VaseModel
from . import orient

GROUP_ID = "vaseforge_preview"


def _log(app, msg):
    try:
        app.log("VaseForge preview: " + msg)
    except Exception:
        pass


def clear(app=None):
    app = app or adsk.core.Application.get()
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        cgs = design.activeComponent.customGraphicsGroups
        for i in range(cgs.count - 1, -1, -1):
            g = cgs.item(i)
            try:
                if g.id == GROUP_ID:
                    g.deleteMe()
            except Exception:
                _log(app, "could not delete old group:\n" + traceback.format_exc(limit=2))
    except Exception:
        _log(app, "clear failed:\n" + traceback.format_exc(limit=2))


def update(app, p, rings: int = 14, m: int = 96):
    """Draw the wireframe. Call from the command's executePreview handler only:
    Fusion discards it automatically before the next preview."""
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        comp = design.activeComponent
        model = VaseModel(p)
        frame = orient.resolve(app, p.up_axis)
        coords, idx, starts = [], [], []
        for i in range(rings):
            u = i / (rings - 1)
            base = len(coords) // 3
            starts.append(base)
            for x, y in model.section_outer(u, m):
                wx, wy, wz = frame.world(x, y, model.z(u))
                coords += [wx / 10.0, wy / 10.0, wz / 10.0]
            for k in range(m):
                idx += [base + k, base + (k + 1) % m]
        step = max(1, m // 32)
        for k in range(0, m, step):
            for i in range(rings - 1):
                idx += [starts[i] + k, starts[i + 1] + k]
        group = comp.customGraphicsGroups.add()
        try:
            group.id = GROUP_ID            # lets clear() find it; a duplicate id must not abort the drawing
        except Exception:
            pass
        c = adsk.fusion.CustomGraphicsCoordinates.create(array.array("d", coords))
        lines = group.addLines(c, idx, False, [])
        lines.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
            adsk.core.Color.create(40, 120, 220, 255))
        lines.weight = 1
        app.activeViewport.refresh()
    except Exception:
        _log(app, "update failed:\n" + traceback.format_exc(limit=3))
