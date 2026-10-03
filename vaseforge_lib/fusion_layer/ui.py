"""Command dialog, live validation and registration (Fusion API)."""
from __future__ import annotations

import json
import math
import os
import traceback

import adsk.core
import adsk.fusion

from ..core.params import VaseParams
from ..core import presets
from ..core.validate import validate, compute_limits
from ..core.i18n import tr, issue_text
from .. import __version__
from . import builder, preview, orient

CMD_ID = "vaseforge_cmd"
PANEL_ID = "SolidCreatePanel"
DEFAULT_PRESET = "twisted_tower"

# (group id, [(field, kind), ...]); kinds: len deg pct num int:lo:hi bool enum:a,b,c
GROUPS = [
    ("g_profile", [("height", "len"), ("base_radius", "len"), ("top_radius", "len"),
                   ("belly_amount", "pct"), ("belly_pos", "pct"), ("belly_width", "pct"),
                   ("neck_amount", "pct"), ("neck_pos", "pct"), ("neck_width", "pct")]),
    ("g_section", [("shape", "enum:circle,polygon"), ("sides", "int:3:16"),
                   ("corner_round", "pct")]),
    ("g_l1", [("lobes", "int:0:30"), ("lobe_amp", "pct"), ("lobe_top_factor", "pct"),
              ("twist", "deg"), ("twist_ease", "enum:linear,smooth")]),
    ("g_l2", [("lobes2", "int:0:30"), ("lobe2_amp", "pct"), ("twist2", "deg")]),
    ("g_wave", [("wave_amp", "pct"), ("wave_count", "int:0:20")]),
    ("g_wall", [("wall", "len"), ("floor", "len"), ("open_bottom", "bool"),
                ("base_hole_d", "len")]),
    ("g_perf", [("perf.enabled", "bool"), ("perf.shape", "enum:circle,hexagon,diamond,slot"),
                ("perf.count", "int:3:60"), ("perf.rows", "int:1:40"), ("perf.fill", "pct"),
                ("perf.z_start", "pct"), ("perf.z_end", "pct"), ("perf.stagger", "bool"),
                ("perf.slot_aspect", "num")]),
    ("g_quality", [("up_axis", "enum:auto,z,y"), ("n_sections", "int:0:150"), ("n_points", "int:0:360"),
                   ("chord_tol", "len"), ("max_overhang", "deg")]),
]
OPEN_GROUPS = ("g_profile", "g_l1")

_handlers = []
_inp = {}
_app = None
_ui = None
_lang = "en"
_cache = {"key": None, "rep": None, "lim": None}


# ------------------------------------------------------------------- helpers
def _iid(name):
    return "vf_" + name.replace(".", "_")


def _get(p, name):
    obj = p
    for part in name.split("."):
        obj = getattr(obj, part)
    return obj


def _set(p, name, val):
    parts = name.split(".")
    obj = p
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], val)


def _enum_keys(kind):
    return kind.split(":", 1)[1].split(",")


def _detect_lang(app):
    try:
        if app.preferences.generalPreferences.userLanguage == adsk.core.UserLanguages.SpanishLanguage:
            return "es"
    except Exception:
        pass
    return "en"


# ------------------------------------------------------------ dialog building
def _add_field(container, name, kind, p):
    iid = _iid(name)
    label = tr("f_" + name.replace(".", "_"), _lang)
    val = _get(p, name)
    VI = adsk.core.ValueInput
    if kind == "len":
        c = container.addValueInput(iid, label, "mm", VI.createByReal(val / 10.0))
    elif kind == "deg":
        c = container.addValueInput(iid, label, "deg", VI.createByReal(math.radians(val)))
    elif kind == "pct":
        c = container.addValueInput(iid, label, "", VI.createByReal(val * 100.0))
    elif kind == "num":
        c = container.addValueInput(iid, label, "", VI.createByReal(val))
    elif kind.startswith("int"):
        _, lo, hi = kind.split(":")
        c = container.addIntegerSpinnerCommandInput(iid, label, int(lo), int(hi), 1, int(val))
    elif kind == "bool":
        c = container.addBoolValueInput(iid, label, True, "", bool(val))
    elif kind.startswith("enum"):
        c = container.addDropDownCommandInput(iid, label, adsk.core.DropDownStyles.TextListDropDownStyle)
        for key in _enum_keys(kind):
            c.listItems.add(tr("e_%s_%s" % (name.replace(".", "_"), key), _lang), key == val)
    else:
        raise ValueError(kind)
    _inp[iid] = (c, kind, name)


def _build_dialog(inputs, p, preset_key):
    _inp.clear()
    dd = inputs.addDropDownCommandInput("vf_preset", tr("preset", _lang),
                                        adsk.core.DropDownStyles.TextListDropDownStyle)
    for key in presets.ORDER:
        dd.listItems.add(tr("p_" + key, _lang), key == preset_key)
    status = inputs.addTextBoxCommandInput("vf_status", tr("status", _lang), "", 7, True)
    _inp["vf_status"] = (status, "text", "")
    for gid, fields in GROUPS:
        g = inputs.addGroupCommandInput("vf_" + gid, tr(gid, _lang))
        g.isExpanded = gid in OPEN_GROUPS
        for name, kind in fields:
            _add_field(g.children, name, kind, p)


def _write_inputs(p):
    for iid, (c, kind, name) in _inp.items():
        if kind == "text":
            continue
        val = _get(p, name)
        if kind == "len":
            c.value = val / 10.0
        elif kind == "deg":
            c.value = math.radians(val)
        elif kind == "pct":
            c.value = val * 100.0
        elif kind == "num":
            c.value = val
        elif kind.startswith("int") or kind == "bool":
            c.value = type(c.value)(val)
        elif kind.startswith("enum"):
            c.listItems.item(_enum_keys(kind).index(val)).isSelected = True


def _read_params():
    p = VaseParams()
    for iid, (c, kind, name) in _inp.items():
        if kind == "text":
            continue
        try:
            if kind == "len":
                v = c.value * 10.0
            elif kind == "deg":
                v = math.degrees(c.value)
            elif kind == "pct":
                v = c.value / 100.0
            elif kind == "num" or kind == "bool" or kind.startswith("int"):
                v = c.value
            else:
                keys = _enum_keys(kind)
                v = keys[c.selectedItem.index]
            _set(p, name, v)
        except Exception:
            pass                                       # keep default for invalid expressions
    return p


# ---------------------------------------------------------------- live checks
def _analyse(p):
    key = p.to_json()
    if _cache["key"] != key:
        _cache["key"] = key
        _cache["rep"] = validate(p)
        try:
            _cache["lim"] = compute_limits(p) if "rho_min" in _cache["rep"].metrics else None
        except Exception:
            _cache["lim"] = None
    return _cache["rep"], _cache["lim"]


def _status_html(rep, lim):
    lines = [issue_text(i, _lang) for i in rep.issues] or ["✔ " + tr("ok", _lang)]
    if lim:
        amp = "—" if lim["lobe_amp"] is None else "%.0f %%" % (lim["lobe_amp"] * 100)
        lines.append(tr("limits", _lang, wall="%.2f" % min(lim["wall"], 99.0), amp=amp,
                        tw="%.0f" % min(lim["twist"], 9999.0), n=lim["n_sections"], m=lim["n_points"]))
    return "<br>".join(lines)


def _refresh():
    if not _inp:
        return
    p = _read_params()
    rep, lim = _analyse(p)
    head = "<b>v%s</b> · %s: %s" % (__version__, tr("f_up_axis", _lang),
                                  orient.resolve(_app, p.up_axis).up.upper())
    _inp["vf_status"][0].formattedText = head + "<br>" + _status_html(rep, lim)


# ------------------------------------------------------------------- handlers
class _Changed(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            if args.input.id == "vf_preset":
                key = presets.ORDER[args.input.selectedItem.index]
                _write_inputs(presets.make(key))
            _refresh()
        except Exception:
            _ui.messageBox(traceback.format_exc())


class _Validate(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            if not _inp:
                return
            rep, _ = _analyse(_read_params())
            args.areInputsValid = bool(rep.ok)
        except Exception:
            args.areInputsValid = False


class _Execute(adsk.core.CommandEventHandler):
    def notify(self, args):
        pd = None
        try:
            p = _read_params()
            rep = validate(p, fine=True)
            if not rep.ok:
                _ui.messageBox(tr("err_invalid", _lang,
                                  list="\n".join(issue_text(i, _lang) for i in rep.errors)))
                return
            preview.clear(_app)
            pd = _ui.createProgressDialog()
            pd.isBackgroundTranslucent = False
            pd.show(tr("cmd_name", _lang), tr("progress", _lang), 0, 100, 1)
            builder.build(_app, p, _lang, pd)
        except builder.BuildError as e:
            _ui.messageBox(str(e))
        except Exception:
            _ui.messageBox(traceback.format_exc())
        finally:
            if pd:
                pd.hide()


class _Preview(adsk.core.CommandEventHandler):
    """Fusion rolls back everything drawn here before the next preview, so the
    wireframe can never go stale (drawing from inputChanged gets undone)."""
    def notify(self, args):
        try:
            if not _inp:
                return
            p = _read_params()
            rep, _ = _analyse(p)
            _app.log("VaseForge v%s preview: h=%.0f r0=%.0f r1=%.0f shape=%s twist=%.0f ok=%s"
                     % (__version__, p.height, p.base_radius, p.top_radius, p.shape, p.twist, rep.ok))
            if rep.ok:
                preview.update(_app, p)
        except Exception:
            _app.log("VaseForge preview handler failed:\n" + traceback.format_exc(limit=3))


class _Destroy(adsk.core.CommandEventHandler):
    def notify(self, args):
        preview.clear(_app)
        _inp.clear()
        _cache["key"] = None


class _Created(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            preview.clear(_app)            # remove orphan wireframes left by earlier sessions
            _app.log("VaseForge v%s loaded from %s" % (__version__, os.path.dirname(os.path.abspath(__file__))))
            try:
                cmd.setDialogInitialSize(430, 820)
            except Exception:
                pass
            for ev, cls in ((cmd.execute, _Execute), (cmd.executePreview, _Preview),
                            (cmd.inputChanged, _Changed),
                            (cmd.validateInputs, _Validate), (cmd.destroy, _Destroy)):
                h = cls()
                ev.add(h)
                _handlers.append(h)
            last = builder.load_last_params(_app)
            if last:
                p, key = VaseParams.from_json(last), None
            else:
                p, key = presets.make(DEFAULT_PRESET), DEFAULT_PRESET
            _build_dialog(cmd.commandInputs, p, key)
            _refresh()
        except Exception:
            _ui.messageBox(traceback.format_exc())


# --------------------------------------------------------------- registration
def register(app, ui):
    global _app, _ui, _lang
    _app, _ui, _lang = app, ui, _detect_lang(app)
    # Remove leftovers from a previous (or duplicate) registration first:
    # a stale control bound to a deleted definition makes the button do nothing.
    panel = ui.allToolbarPanels.itemById(PANEL_ID)
    stale = panel.controls.itemById(CMD_ID)
    if stale:
        stale.deleteMe()
    old = ui.commandDefinitions.itemById(CMD_ID)
    if old:
        old.deleteMe()
    res = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "resources")
    cdef = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, tr("cmd_name", _lang), tr("cmd_tip", _lang), res)
    h = _Created()
    cdef.commandCreated.add(h)
    _handlers.append(h)
    ctrl = panel.controls.addCommand(cdef)
    try:
        ctrl.isPromoted = True
    except Exception:
        pass


def unregister(ui):
    preview.clear()
    panel = ui.allToolbarPanels.itemById(PANEL_ID)
    if panel:
        ctrl = panel.controls.itemById(CMD_ID)
        if ctrl:
            ctrl.deleteMe()
    cdef = ui.commandDefinitions.itemById(CMD_ID)
    if cdef:
        cdef.deleteMe()
    _handlers.clear()
