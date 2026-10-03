"""Render a gallery of every preset (silhouette + top section) with matplotlib.
No Fusion needed: this uses the same math model as the add-in.

    python tools/gallery.py            # writes docs/gallery.png
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from vaseforge_lib.core import presets
from vaseforge_lib.core.model import VaseModel, TAU
from vaseforge_lib.core.validate import validate, compute_limits


def draw(ax_side, ax_top, key):
    p = presets.make(key)
    m = VaseModel(p)
    n = 160
    zs = [p.height * i / n for i in range(n + 1)]
    right = [m.rho(0.0, i / n) for i in range(n + 1)]
    left = [-m.rho(math.pi, i / n) for i in range(n + 1)]
    ax_side.fill_betweenx(zs, left, right, color="#9ec5ee", alpha=0.6)
    ax_side.plot(right, zs, "k", lw=1)
    ax_side.plot(left, zs, "k", lw=1)
    inner_r = [m.rho(0.0, i / n) - p.wall for i in range(n + 1)]
    inner_l = [-(m.rho(math.pi, i / n) - p.wall) for i in range(n + 1)]
    z0 = 0 if p.open_bottom else p.floor
    mask = [i for i, z in enumerate(zs) if z >= z0]
    ax_side.fill_betweenx([zs[i] for i in mask], [inner_l[i] for i in mask],
                          [inner_r[i] for i in mask], color="white")
    ax_side.set_aspect("equal")
    ax_side.axis("off")
    for u, col in ((0.0, "#2a6fb0"), (1.0, "#d95f02")):
        pts = m.section_outer(u, 360)
        ax_top.plot([x for x, _ in pts] + [pts[0][0]], [y for _, y in pts] + [pts[0][1]], color=col, lw=1)
    ax_top.set_aspect("equal")
    ax_top.axis("off")
    rep = validate(p, fine=True)
    lim = compute_limits(p)
    ax_side.set_title("%s%s" % (key, "" if rep.ok else "  (invalid)"), fontsize=9)
    return lim


def main():
    keys = presets.ORDER
    cols = 4
    rows = math.ceil(len(keys) / cols)
    fig, axes = plt.subplots(rows * 2, cols, figsize=(cols * 2.6, rows * 5.2),
                             gridspec_kw={"height_ratios": [3, 1.6] * rows})
    for idx, key in enumerate(keys):
        r, c = divmod(idx, cols)
        draw(axes[2 * r][c], axes[2 * r + 1][c], key)
    for idx in range(len(keys), rows * cols):
        r, c = divmod(idx, cols)
        axes[2 * r][c].axis("off")
        axes[2 * r + 1][c].axis("off")
    fig.suptitle("VaseForge presets - side view (cut) and base (blue) / rim (orange) sections", fontsize=11)
    fig.tight_layout()
    out = os.path.join(os.path.dirname(__file__), "..", "docs", "gallery.png")
    fig.savefig(out, dpi=110)
    print("wrote", os.path.abspath(out))


if __name__ == "__main__":
    main()
