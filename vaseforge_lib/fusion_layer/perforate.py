"""Cuts rows of holes through the finished wall (Fusion API).

Parametric-safe: every plane is an offset of the YZ origin plane (the plane
x = const), so no explicit point+normal planes are needed. Cutters therefore run
along the model X axis; staggered rows shift the hole centre along Y instead of
rotating the plane (exact centre, cutter axis off the local radial by <= pi/count)."""
from __future__ import annotations

import math

import adsk.core
import adsk.fusion

from ..core.perforation import layout, hole_outline
from ..core.model import VaseModel


def _pt(frame, x, y, z):
    wx, wy, wz = frame.world(x, y, z)
    return adsk.core.Point3D.create(wx / 10.0, wy / 10.0, wz / 10.0)


def build_perforations(comp, body, model: VaseModel, p, frame, axis, tick=None, hidden=None):
    pp = p.perf
    rows = layout(model, p)
    yz = comp.yZConstructionPlane
    flip = -1.0 if yz.geometry.normal.x < 0 else 1.0       # world X is X in both Y-up and Z-up
    cuts = []
    for row in rows:
        c, s = math.cos(row.theta), math.sin(row.theta)
        x0 = row.r_mid * c                                  # plane x = const
        yc = row.r_mid * s                                  # hole centre along the plane
        planes = comp.constructionPlanes
        pin = planes.createInput()
        pin.setByOffset(yz, adsk.core.ValueInput.createByReal(flip * x0 / 10.0))
        plane = planes.add(pin)
        sk = comp.sketches.add(plane)
        sk.isComputeDeferred = True

        def to_sketch(a, b):
            return sk.modelToSketchSpace(_pt(frame, x0, yc + a, row.z + b))

        kind, data = hole_outline(pp.shape, row.size, pp.slot_aspect)
        if kind == "circle":
            sk.sketchCurves.sketchCircles.addByCenterRadius(to_sketch(0.0, 0.0), data / 10.0)
        else:
            pts = [to_sketch(a, b) for a, b in data]
            lines = sk.sketchCurves.sketchLines
            first = lines.addByTwoPoints(pts[0], pts[1])
            prev = first
            for k in range(2, len(pts)):
                prev = lines.addByTwoPoints(prev.endSketchPoint, pts[k])
            lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)
        sk.isComputeDeferred = False

        sag = (row.size / 2.0) ** 2 / (2.0 * max(row.r_mid, 1.0))
        full_len = 2.0 * (row.wall_h / max(c, 0.5) + sag + 1.5)          # mm, symmetric about the plane
        ext = comp.features.extrudeFeatures
        ein = ext.createInput(sk.profiles.item(0), adsk.fusion.FeatureOperations.CutFeatureOperation)
        ein.setSymmetricExtent(adsk.core.ValueInput.createByReal(full_len / 10.0), True)
        ein.participantBodies = [body]
        cuts.append(ext.add(ein))
        if hidden is not None:
            hidden.extend([plane, sk])
        if tick:
            tick()

    if pp.count > 1 and cuts:
        ents = adsk.core.ObjectCollection.create()
        for f in cuts:
            ents.add(f)
        cps = comp.features.circularPatternFeatures
        cin = cps.createInput(ents, axis)
        cin.quantity = adsk.core.ValueInput.createByReal(pp.count)
        cin.totalAngle = adsk.core.ValueInput.createByString("360 deg")
        cin.isSymmetric = False
        cps.add(cin)
    return len(cuts)
