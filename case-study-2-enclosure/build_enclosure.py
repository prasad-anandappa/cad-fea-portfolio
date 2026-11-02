#!/usr/bin/env python3
"""
Parametric two-part electronics enclosure — FreeCAD 1.0 headless build.

One script, driven by the PCB size (board L x W) and the component height
above the board. It generates:
  * a base tray (floor, walls, 4x board standoff bosses, 4x corner posts
    with pilot holes for the lid screws, one cable-gland hole),
  * a lid (top panel + overlap skirt, vent-slot array, 4x screw holes),
  * a closed assembly (base + lid) for reference.
Run twice with different --board/--comp values to prove the parametric
variants. Units: mm. M3 screws throughout.

    freecadcmd build_enclosure.py -- --board 85x60 --comp 18 --out sizeA
Outputs: <out>_base.step/.stl, <out>_lid.step/.stl, <out>_assembly.step,
         <out>_params.json
"""
import sys, json
import FreeCAD
from FreeCAD import Vector
import Part
import Mesh

# fixed design parameters [mm]
WALL = 2.4        # wall / floor / lid panel thickness
CLEAR = 3.0       # board-to-cavity clearance per side
STANDOFF = 4.0    # board standoff height above cavity floor
BOARD_T = 1.6     # PCB thickness
HEADROOM = 4.0    # air gap above tallest component to lid
POST_D = 8.0      # lid-screw corner post diameter
POST_INSET = 4.0  # post centre inset from cavity corner
PILOT_D = 2.9     # M3 self-tap pilot hole
BOSS_D = 6.0      # board standoff boss diameter
BOSS_INSET = 4.0  # board hole inset from board edge
SKIRT = 10.0      # lid skirt height (overlap portion 7.6)
SKIRT_GAP = 0.4   # lid-to-base sliding clearance per side
VENT_W = 3.0      # vent slot width
VENT_PITCH = 7.0  # vent slot row pitch
GLAND_D = 12.0    # cable gland hole in front wall

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
board_l, board_w, comp_h, out = 85.0, 60.0, 18.0, "enclosure"
for i in range(len(args)):
    if args[i] == "--board":
        board_l, board_w = (float(v) for v in args[i + 1].split("x"))
    elif args[i] == "--comp":
        comp_h = float(args[i + 1])
    elif args[i] == "--out":
        out = args[i + 1]

Li, Wi = board_l + 2 * CLEAR, board_w + 2 * CLEAR      # cavity
Lo, Wo = Li + 2 * WALL, Wi + 2 * WALL                  # base outer
H_base = WALL + STANDOFF + BOARD_T + comp_h + HEADROOM

# ---------------- base ----------------
base = Part.makeBox(Lo, Wo, H_base, Vector(0, 0, 0))
cavity = Part.makeBox(Li, Wi, H_base, Vector(WALL, WALL, WALL))
base = base.cut(cavity)

# corner posts (lid screws) — fused bosses inside the cavity corners
post_h = H_base - 1.5 - WALL
for cx in (WALL + POST_INSET, WALL + Li - POST_INSET):
    for cy in (WALL + POST_INSET, WALL + Wi - POST_INSET):
        post = Part.makeCylinder(POST_D / 2, post_h, Vector(cx, cy, WALL))
        base = base.fuse(post)
        pilot = Part.makeCylinder(PILOT_D / 2, 13, Vector(cx, cy, H_base - 1.5 - 13))
        base = base.cut(pilot)

# board standoff bosses on the cavity floor
for bx in (WALL + CLEAR + BOSS_INSET, WALL + CLEAR + board_l - BOSS_INSET):
    for by in (WALL + CLEAR + BOSS_INSET, WALL + CLEAR + board_w - BOSS_INSET):
        boss = Part.makeCylinder(BOSS_D / 2, STANDOFF, Vector(bx, by, WALL))
        base = base.fuse(boss)
        pilot = Part.makeCylinder(PILOT_D / 2, STANDOFF + 2, Vector(bx, by, WALL + 0.5))
        base = base.cut(pilot)

# cable gland hole through the front (y=0) wall
gz = WALL + (H_base - WALL) * 0.55
gland = Part.makeCylinder(GLAND_D / 2, WALL + 2, Vector(Lo / 2, -1, gz), Vector(0, 1, 0))
base = base.cut(gland)
base = base.removeSplitter()

# outer vertical edge fillets (best effort)
try:
    vedges = [e for e in base.Edges
              if abs(e.CenterOfMass.x) in (0.0,) or True]
    corner_edges = []
    for e in base.Edges:
        c = e.CenterOfMass
        on_corner = (min(c.x, Lo - c.x) < 0.01) and (min(c.y, Wo - c.y) < 0.01)
        if on_corner and e.Length > H_base * 0.9:
            corner_edges.append(e)
    if corner_edges:
        base = base.makeFillet(2.0, corner_edges)
except Exception as ex:
    print("base fillet skipped:", ex)

assert base.isValid() and len(base.Solids) == 1, "base solid invalid"

# ---------------- lid ----------------
lid_Lo = Lo + 2 * (SKIRT_GAP + WALL)
lid_Wo = Wo + 2 * (SKIRT_GAP + WALL)
z_top0 = H_base - (SKIRT - WALL)          # lid underside plane (skirt bottom)
lid = Part.makeBox(lid_Lo, lid_Wo, SKIRT, Vector(-(SKIRT_GAP + WALL), -(SKIRT_GAP + WALL), z_top0))
lid_cav = Part.makeBox(Lo + 2 * SKIRT_GAP, Wo + 2 * SKIRT_GAP, SKIRT - WALL + 1,
                       Vector(-SKIRT_GAP, -SKIRT_GAP, z_top0 - 1))
lid = lid.cut(lid_cav)                    # leaves the top panel (WALL thick)

# vent slots through the top panel
panel_z = H_base + WALL                   # top face of lid
slot_len = lid_Lo - 28
rows = int((lid_Wo - 30) // VENT_PITCH)
y0 = lid_Wo / 2 - (rows - 1) * VENT_PITCH / 2 - SKIRT_GAP - WALL
for r in range(rows):
    yc = y0 + r * VENT_PITCH
    xc = lid_Lo / 2 - SKIRT_GAP - WALL
    body = Part.makeBox(slot_len - VENT_W, VENT_W, WALL + 2,
                        Vector(xc - slot_len / 2 + VENT_W / 2, yc - VENT_W / 2, panel_z - WALL - 1))
    c1 = Part.makeCylinder(VENT_W / 2, WALL + 2, Vector(xc - slot_len / 2 + VENT_W / 2, yc, panel_z - WALL - 1), Vector(0, 0, 1))
    c2 = Part.makeCylinder(VENT_W / 2, WALL + 2, Vector(xc + slot_len / 2 - VENT_W / 2, yc, panel_z - WALL - 1), Vector(0, 0, 1))
    lid = lid.cut(body.fuse(c1).fuse(c2))

# lid screw clearance holes over the corner posts
for cx in (WALL + POST_INSET, WALL + Li - POST_INSET):
    for cy in (WALL + POST_INSET, WALL + Wi - POST_INSET):
        hole = Part.makeCylinder(3.4 / 2, WALL + 2, Vector(cx, cy, panel_z - WALL - 1), Vector(0, 0, 1))
        lid = lid.cut(hole)
lid = lid.removeSplitter()
try:
    corner_edges = []
    for e in lid.Edges:
        c = e.CenterOfMass
        on_corner = (min(c.x + SKIRT_GAP + WALL, lid_Lo - (c.x + SKIRT_GAP + WALL)) < 0.01) and \
                    (min(c.y + SKIRT_GAP + WALL, lid_Wo - (c.y + SKIRT_GAP + WALL)) < 0.01)
        if on_corner and e.Length > SKIRT * 0.9:
            corner_edges.append(e)
    if corner_edges:
        lid = lid.makeFillet(2.0, corner_edges)
except Exception as ex:
    print("lid fillet skipped:", ex)

assert lid.isValid() and len(lid.Solids) == 1, "lid solid invalid"

# ---------------- export ----------------
doc = FreeCAD.newDocument("Enclosure")

def export(shape, name, stem):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    doc.recompute()
    shape.exportStep(stem + ".step")
    Mesh.export([o], stem + ".stl")
    return o

export(base, "Base", out + "_base")
export(lid, "Lid", out + "_lid")
asm = Part.makeCompound([base, lid])
asm.exportStep(out + "_assembly.step")

info = dict(board=dict(l=board_l, w=board_w, comp_h=comp_h),
            fixed=dict(wall=WALL, clearance=CLEAR, standoff=STANDOFF),
            base_outer=dict(l=Lo, w=Wo, h=H_base),
            closed_height=H_base + WALL,
            base_volume_mm3=base.Volume, lid_volume_mm3=lid.Volume,
            vent_rows=rows)
with open(out + "_params.json", "w") as f:
    json.dump(info, f, indent=2)
print("ENCLOSURE_OK", out, "base", (round(Lo, 1), round(Wo, 1), round(H_base, 1)),
      "closed_h", round(H_base + WALL, 1), "vents", rows,
      "base_vol", round(base.Volume), "lid_vol", round(lid.Volume))
