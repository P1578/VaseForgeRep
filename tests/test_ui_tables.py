import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _stub_adsk():
    class _Mod(types.ModuleType):
        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            cls = type(name, (object,), {})
            setattr(self, name, cls)
            return cls
    adsk = _Mod("adsk")
    for sub in ("core", "fusion"):
        m = _Mod("adsk." + sub)
        setattr(adsk, sub, m)
        sys.modules["adsk." + sub] = m
    sys.modules["adsk"] = adsk


_stub_adsk()

from vaseforge_lib.fusion_layer import ui  # noqa: E402
from vaseforge_lib.core.params import VaseParams  # noqa: E402
from vaseforge_lib.core.i18n import _S, tr  # noqa: E402
from vaseforge_lib.core import presets  # noqa: E402


def test_every_dialog_field_maps_to_a_param_and_has_labels():
    p = VaseParams()
    for gid, fields in ui.GROUPS:
        assert gid in _S
        for name, kind in fields:
            ui._get(p, name)                                   # attribute exists
            assert "f_" + name.replace(".", "_") in _S, name
            if kind.startswith("enum"):
                for key in ui._enum_keys(kind):
                    assert "e_%s_%s" % (name.replace(".", "_"), key) in _S


def test_every_param_is_exposed_or_intentionally_hidden():
    exposed = {n.split(".")[0] for _, fs in ui.GROUPS for n, _ in fs}
    hidden_ok = {"perf", "max_sections"}
    missing = set(VaseParams().to_dict()) - exposed - hidden_ok
    assert not missing, missing


def test_presets_have_names_in_both_languages():
    for key in presets.ORDER:
        assert tr("p_" + key, "en") != "p_" + key
        assert tr("p_" + key, "es") != "p_" + key


def test_issue_codes_have_messages():
    from vaseforge_lib.core import validate as v
    import re
    src = open(v.__file__).read()
    codes = set(re.findall(r'add\("(?:error|warn)",\s*"(\w+)"', src))
    for c in codes:
        assert "i_" + c in _S, c
