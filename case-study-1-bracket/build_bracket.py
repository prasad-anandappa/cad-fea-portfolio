#!/usr/bin/env python3
"""
Parametric wall-mount cantilever bracket — FreeCAD 1.0 headless build script.

Design: a flat mounting plate (bolted flat against a wall, back face x=0)
with a horizontal arm plate fused at the top. The arm cantilevers out in +X
and carries a downward load near its tip. One plate thickness `t` drives both
plates, so changing `t` regenerates the whole bracket (the parametric demo).

Units: mm. Run with freecadcmd:
    freecadcmd build_bracket.py -- --t 6 --out bracket_t6
Outputs: <out>.step, <out>.stl, <out>_params.json
"""
import sys, json
import FreeCAD
from FreeCAD import Vector
import Part
import Mesh

# ---------- parameters (defaults = variant A) ----------
P = dict(
    t=6.0,          # plate thickness (both plates)         [mm]
    mount_w=70.0,   # mounting plate width  (Y)             [mm]
    mount_h=90.0,   # mounting plate height (Z)             [mm]
    arm_len=95.0,   # arm length from wall  (X)             [mm]
    arm_w=60.0,     # arm width             (Y)             [mm]
    fillet_r=4.0,   # inner corner fillet radius            [mm]
    mount_hole_d=9.0,    # 4x mounting holes (M8 clearance)
    mount_hole_dy=22.0,  # mounting hole Y offset from centre
    mount_hole_z1=22.0,  # mounting hole row 1 height
    mount_hole_z2=68.0,  # mounting hole row 2 height
    tip_hole_d=11.0,     # arm tip hole (pin / hanging point)
    tip_hole_x=80.0,     # arm tip hole X position
)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out_prefix = "bracket"
for i in range(len(args)):
    if args[i] == "--t":
        P["t"] = float(args[i + 1])
    elif args[i] == "--out":
        out_prefix = args[i + 1]

t, W, H = P["t"], P["mount_w"], P["mount_h"]
A, AW = P["arm_len"], P["arm_w"]

# ---------- solid construction ----------
mount = Part.makeBox(t, W, H, Vector(0, -W / 2.0, 0))
arm = Part.makeBox(A, AW, t, Vector(0, -AW / 2.0, H - t))
shape = mount.fuse(arm).removeSplitter()

# inner corner fillet: the concave edge at x=t, z=H-t running along Y
target = None
for e in shape.Edges:
    c = e.CenterOfMass
    if abs(c.x - t) < 0.01 and abs(c.z - (H - t)) < 0.01 and e.Length > AW * 0.9:
        target = e
        break
if target is not None and P["fillet_r"] > 0:
    shape = shape.makeFillet(P["fillet_r"], [target])

# mounting holes (through X)
r_m = P["mount_hole_d"] / 2.0
for yy in (-P["mount_hole_dy"], P["mount_hole_dy"]):
    for zz in (P["mount_hole_z1"], P["mount_hole_z2"]):
        cyl = Part.makeCylinder(r_m, t + 4, Vector(-2, yy, zz), Vector(1, 0, 0))
        shape = shape.cut(cyl)

# arm tip hole (through Z)
r_t = P["tip_hole_d"] / 2.0
cyl = Part.makeCylinder(r_t, t + 4, Vector(P["tip_hole_x"], 0, H - t - 2), Vector(0, 0, 1))
shape = shape.cut(cyl)
shape = shape.removeSplitter()

assert shape.isValid(), "resulting solid is not valid"
assert len(shape.Solids) == 1, "expected a single solid"

# ---------- export ----------
doc = FreeCAD.newDocument("Bracket")
obj = doc.addObject("Part::Feature", "Bracket")
obj.Shape = shape
doc.recompute()

shape.exportStep(out_prefix + ".step")
Mesh.export([obj], out_prefix + ".stl")

bb = shape.BoundBox
info = dict(params=P, volume_mm3=shape.Volume, area_mm2=shape.Area,
            bbox=dict(x=bb.XLength, y=bb.YLength, z=bb.ZLength),
            mass_kg_steel7850=shape.Volume * 7850e-9)
with open(out_prefix + "_params.json", "w") as f:
    json.dump(info, f, indent=2)
print("BRACKET_OK", out_prefix, "t=", t, "vol=", round(shape.Volume, 1),
      "bbox=", (round(bb.XLength, 1), round(bb.YLength, 1), round(bb.ZLength, 1)))
