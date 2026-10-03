"""VaseForge - parametric vases, containers and lampshades for Fusion.

Entry point: Fusion calls run() / stop() when the add-in is started / stopped.
"""
import os
import sys
import traceback

import adsk.core

_here = os.path.dirname(os.path.realpath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from vaseforge_lib.fusion_layer import ui as vf_ui  # noqa: E402


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        vf_ui.register(app, ui)
    except Exception:
        ui.messageBox("VaseForge failed to start:\n" + traceback.format_exc())


def stop(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        vf_ui.unregister(ui)
    except Exception:
        ui.messageBox("VaseForge failed to stop:\n" + traceback.format_exc())
