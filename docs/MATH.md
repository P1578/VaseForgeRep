# The maths behind VaseForge

Everything the add-in accepts or rejects comes from the surface model below
(`vaseforge_lib/core/model.py`, `validate.py`). Units are mm and radians.

## 1. Surface model

With `u in [0,1]` the normalised height and `theta` the world angle,

```
rho(theta,u) = R(u) * wave(u) * S(theta - phi1(u))
               * (1 + A1(u) cos(N1 (theta - phi1(u))))
               * (1 + A2    cos(N2 (theta - phi2(u))))
```

* `R(u)`: linear taper plus Gaussian bumps (belly, neck), re-normalised so the
  base and top radii are exact.
* `S`: unit-circumradius smooth polygon. With face normals `a_i` it is
  `S(t) = c / (sum_i max(0, cos(t - a_i))^p)^(1/p)`; `p` (from the *corner
  rounding* slider) goes from 2 (almost round) to 40 (almost sharp).
* `phi1(u)`, `phi2(u)`: twist angle, linear or smoothstep in `u`.

Each horizontal section is a polar curve with `rho > 0`, and sections sit on
strictly increasing `z`, so **the outer surface cannot intersect itself**. The
three real failure modes are handled explicitly:

## 2. Wall thickness limit (inner offset must not fold)

Offsetting a planar curve inward by `d` is regular iff `d * kappa < 1` where
`kappa` is the signed curvature of the section:

```
kappa = (rho^2 + 2 rho'^2 - rho rho'') / (rho^2 + rho'^2)^(3/2)
```

For `rho = R(1 + A cos N theta)` the tightest spot is a lobe tip:

```
kappa_tip = (1 + A (1 + N^2)) / (R (1 + A)^2)
```

(the unit tests compare the numeric curvature against this closed form).

A wall of normal thickness `t` on a surface tilted by `alpha` from vertical
needs a *horizontal* offset `d = t / cos(alpha)` with

```
tan(alpha) = |d rho/dz| / sqrt(1 + (rho'/rho)^2)
```

where `d rho/dz` is taken at fixed world angle, so twist-induced tilt is
included. The same idea applies along the meridian (`R''` along the rails).
The reported limit is

```
t_max = 0.9 * min over (u, theta) of 1 / (kappa * g),   g = 1/cos(alpha)
```

and the **lobe-depth limit** is found by bisection on the validator.
A final geometric test builds the inner sections and rejects segments that
flip direction relative to the outer ones.

## 3. Number of loft sections (and therefore the twist limit)

A loft chord between two sections turned by `dphi` cuts the helix of radius
`R` by `R dphi^2 / 8`. Requiring that to stay under the tolerance `tol` gives

```
dphi_max = sqrt(8 tol / R)        sections >= twist / dphi_max + 1
```

Counter-rotating lobes (layer 2) move relative to the rails, with error
`A2 R (N2 dphi_rel)^2 / 8`. With a cap of `max_sections` the maximum twist is
`dphi_max * (max_sections - 1)`; the dialog shows it live.

## 4. Printability

The overhang angle is `atan(max(0, d rho/dz) / sqrt(1 + (rho'/rho)^2))`
(outward-leaning walls only). It is a warning, not an error, because lampshades
are often printed with supports.

## 5. Perforations

Rows are placed between `z_start` and `z_end`; the hole width is `fill * pitch`
with `pitch = 2 pi r_mid / count`, so holes scale with the local radius. Rules:
web between holes >= 1.2 mm, rows must not overlap (staggered rows may
interlock), and the first row must clear the floor.
