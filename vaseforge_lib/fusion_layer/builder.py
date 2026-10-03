"""Turns a VaseParams into native Fusion geometry (sketches -> loft -> cut)."""
from __future__ import annotations

import json
import math
import traceback

import adsk.core
import adsk.fusion

from ..core.model import VaseModel, discretization
from ..core.i18n import tr
from . import perforate, orient

BODY_NAME = "VaseForge Vase"
ATTR_GROUP, ATTR_NAME = "VaseForge", "last_params"
EXT_MM = 1.0          # how far the cavity tool pokes outside the rim / base


class BuildError(Exception):
    pass


def _offset_plane(comp, frame, z_mm, hidden):
    """Plane at height z (mm) along the vase axis, built by offsetting an origin plane.
    (Planes defined by an explicit point + normal are not allowed in parametric designs.)"""
    base = comp.xYConstructionPlane if frame.up == "z" else comp.xZConstructionPlane
    if abs(z_mm) < 1e-9:
        return base
    off = z_mm / 10.0
    n = base.geometry.normal
    ux, uy, uz = frame.vec(0.0, 0.0, 1.0)
    if n.x * ux + n.y * uy + n.z * uz < 0:       # plane normal points down the axis: flip
        off = -off
    planes = comp.constructionPlanes
    pin = planes.createInput()
    pin.setByOffset(base, adsk.core.ValueInput.createByReal(off))
    plane = planes.add(pin)
    hidden.append(plane)
    return plane


def _ring_profile(comp, frame, z_mm, pts_mm, hidden):
    plane = _offset_plane(comp, frame, z_mm, hidden)
    sk = comp.sketches.add(plane)
    hidden.append(sk)
    sk.isComputeDeferred = True
    if frame.up == "z":
        convert = lambda x, y: adsk.core.Point3D.create(x / 10.0, y / 10.0, 0.0)
    else:
        def convert(x, y):
            wx, wy, wz = frame.world(x, y, z_mm)
            return sk.modelToSketchSpace(adsk.core.Point3D.create(wx / 10.0, wy / 10.0, wz / 10.0))
    coll = adsk.core.ObjectCollection.create()
    for x, y in pts_mm:
        coll.add(convert(x, y))
    spl = sk.sketchCurves.sketchFittedSplines.add(coll)
    spl.isClosed = True
    sk.isComputeDeferred = False
    if sk.profiles.count < 1:
        raise BuildError("Section sketch produced no closed profile at z=%.2f mm" % z_mm)
    return sk.profiles.item(0)


def _loft(comp, profiles):
    lofts = comp.features.loftFeatures
    lin = lofts.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    for prof in profiles:
        lin.loftSections.add(prof)
    lin.isSolid = True
    return lofts.add(lin)


def _set_user_param(design, name, value_mm, comment):
    expr = "%.4f mm" % value_mm
    prm = design.userParameters.itemByName(name)
    if prm:
        prm.expression = expr
    else:
        design.userParameters.add(name, adsk.core.ValueInput.createByString(expr), "mm", comment)


def _rollback(tl, start):
    for i in range(tl.count - 1, start - 1, -1):
        try:
            tl.item(i).entity.deleteMe()
        except Exception:
            pass


def build(app, p, lang="en", progress=None):
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise BuildError(tr("err_nodesign", lang))
    if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        raise BuildError(tr("err_parametric", lang))
    comp = design.activeComponent
    tl = design.timeline
    start = tl.markerPosition

    frame = orient.resolve(app, p.up_axis)
    model = VaseModel(p)
    disc = discretization(p, model)
    n, m = disc["n_sections"], disc["n_points"]
    u0 = 0.0 if p.open_bottom else min(p.floor / p.height, 0.95)
    n_in = max(4, int(round(n * (1.0 - u0))) + 1)
    steps = n + n_in + 4 + (len(range(p.perf.rows)) if p.perf.enabled else 0)
    state = {"i": 0}
    if progress:
        try:
            progress.maximumValue = steps
        except Exception:
            pass

    def tick():
        state["i"] += 1
        if progress:
            progress.progressValue = min(state["i"], steps)
            adsk.doEvents()

    hidden = []
    try:
        # 1. outer loft ---------------------------------------------------
        profs = []
        for i in range(n):
            u = i / (n - 1) if n > 1 else 0.0
            profs.append(_ring_profile(comp, frame, model.z(u), model.section_outer(u, m), hidden))
            tick()
        outer = _loft(comp, profs)
        body = outer.bodies.item(0)
        body.name = BODY_NAME
        tick()

        # 2. cavity tool body (inner offset sections, poking out of rim/base)
        cprofs = []
        if p.open_bottom:
            cprofs.append(_ring_profile(comp, frame, -EXT_MM, model.section_inner(0.0, m, p.wall), hidden))
        for i in range(n_in):
            u = u0 + (1.0 - u0) * i / (n_in - 1)
            cprofs.append(_ring_profile(comp, frame, model.z(u), model.section_inner(u, m, p.wall), hidden))
            tick()
        cprofs.append(_ring_profile(comp, frame, p.height + EXT_MM, model.section_inner(1.0, m, p.wall), hidden))
        cavity = _loft(comp, cprofs)
        tools = adsk.core.ObjectCollection.create()
        tools.add(cavity.bodies.item(0))
        combs = comp.features.combineFeatures
        cin = combs.createInput(body, tools)
        cin.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
        cin.isKeepToolBodies = False
        combs.add(cin)
        tick()
        body = comp.bRepBodies.itemByName(BODY_NAME)

        # 3. optional hole through the floor ------------------------------
        if p.base_hole_d > 0 and not p.open_bottom:
            base_plane = comp.xYConstructionPlane if frame.up == "z" else comp.xZConstructionPlane
            sk = comp.sketches.add(base_plane)
            hidden.append(sk)
            sk.sketchCurves.sketchCircles.addByCenterRadius(
                adsk.core.Point3D.create(0, 0, 0), p.base_hole_d / 20.0)
            ext = comp.features.extrudeFeatures
            ein = ext.createInput(sk.profiles.item(0), adsk.fusion.FeatureOperations.CutFeatureOperation)
            # symmetric about the base plane: independent of which way the plane normal points
            ein.setSymmetricExtent(adsk.core.ValueInput.createByReal((p.floor + 1.0) / 10.0), False)
            ein.participantBodies = [body]
            ext.add(ein)
        tick()

        # 4. perforations --------------------------------------------------
        if p.perf.enabled:
            axis = comp.zConstructionAxis if frame.up == "z" else comp.yConstructionAxis
            perforate.build_perforations(comp, body, model, p, frame, axis, tick, hidden)

        # 5. housekeeping: reference parameters, hidden helpers, timeline group
        _set_user_param(design, "VF_height", p.height, "VaseForge: overall height (reference only)")
        _set_user_param(design, "VF_base_diameter", 2 * p.base_radius, "VaseForge: nominal base diameter (reference only)")
        _set_user_param(design, "VF_top_diameter", 2 * p.top_radius, "VaseForge: nominal top diameter (reference only)")
        _set_user_param(design, "VF_wall", p.wall, "VaseForge: wall thickness (reference only)")
        _set_user_param(design, "VF_floor", 0.0 if p.open_bottom else p.floor, "VaseForge: floor thickness (reference only)")
        for ent in hidden:
            try:
                ent.isLightBulbOn = False
            except Exception:
                pass
        design.attributes.add(ATTR_GROUP, ATTR_NAME, p.to_json())
        end = tl.markerPosition - 1
        if end >= start:
            try:
                grp = tl.timelineGroups.add(start, end)
                grp.name = "VaseForge"
            except Exception:
                pass
        return body
    except Exception as exc:
        _rollback(tl, start)
        raise BuildError(tr("err_build", lang, err=str(exc) + "\n" + traceback.format_exc(limit=3)))


def load_last_params(app):
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        attr = design.attributes.itemByName(ATTR_GROUP, ATTR_NAME)
        return attr.value if attr else None
    except Exception:
        return None
