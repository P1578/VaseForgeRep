"""Generate the 16x16 / 32x32 toolbar icons (a vase silhouette)."""
import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "resources")


def vase(size, fg, bg=(0, 0, 0, 0)):
    S = size * 8
    im = Image.new("RGBA", (S, S), bg)
    d = ImageDraw.Draw(im)
    pts_l, pts_r = [], []
    for i in range(61):
        t = i / 60
        r = 0.20 + 0.20 * math.exp(-((t - 0.40) / 0.22) ** 2) - 0.10 * math.exp(-((t - 0.86) / 0.10) ** 2)
        y = S * (0.90 - 0.80 * t)
        pts_l.append((S * (0.5 - r), y))
        pts_r.append((S * (0.5 + r), y))
    d.polygon(pts_l + pts_r[::-1], fill=fg)
    return im.resize((size, size), Image.LANCZOS)


for size in (16, 32):
    vase(size, (30, 90, 160, 255)).save(os.path.join(OUT, "%dx%d.png" % (size, size)))
    vase(size, (210, 225, 245, 255)).save(os.path.join(OUT, "%dx%d-dark.png" % (size, size)))
print("icons written to", os.path.abspath(OUT))
