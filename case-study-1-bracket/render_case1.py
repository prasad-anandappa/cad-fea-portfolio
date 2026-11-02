#!/usr/bin/env python3
"""
Renders for case study 1:
  * von Mises contour plots from the FEA result arrays (<job>_mesh.npz)
  * deformed-shape overlay (exaggeration x25) for the fine t6 run
  * plain shaded geometry renders from the exported STL files
Uses matplotlib (Agg) only -- fully headless.
"""
import argparse, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ap = argparse.ArgumentParser()
ap.add_argument("--npz", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("--title", default="")
ap.add_argument("--defl-scale", type=float, default=25.0)
a = ap.parse_args()

d = np.load(a.npz)
coords, elems, vm, u = d["coords"], d["elems"], d["vm"], d["u"]
corners = elems[:, :4]


def boundary_faces(corner_elems):
    faces = {}
    for ei, e in enumerate(corner_elems):
        for f in ((e[0], e[1], e[2]), (e[0], e[1], e[3]),
                  (e[1], e[2], e[3]), (e[0], e[2], e[3])):
            key = tuple(sorted(f))
            faces[key] = faces.get(key, 0) + 1
    return np.array([k for k, c in faces.items() if c == 1])


bf = boundary_faces(corners)
print("boundary faces:", len(bf))

LIGHT = np.array([0.4, 0.5, 0.75])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def render(pts, face_idx, face_val, fname, elev, azim, title,
           cmap_name="jet", vmin=None, vmax=None, colorbar_label=None,
           xlim=None, ylim=None, zlim=None, base_rgb=None):
    tris = pts[face_idx]                       # (nf, 3, 3)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    shade = 0.72 + 0.28 * np.abs(n @ LIGHT)
    if base_rgb is None:
        cmap = plt.get_cmap(cmap_name)
        norm = plt.Normalize(vmin if vmin is not None else face_val.min(),
                             vmax if vmax is not None else face_val.max())
        cols = cmap(norm(face_val))[:, :3] * shade[:, None]
    else:
        cols = np.array(base_rgb)[None, :] * shade[:, None]
    order = np.argsort(tris.mean(axis=1) @
                       np.array([np.cos(np.radians(elev)) * np.sin(np.radians(azim)),
                                 -np.cos(np.radians(elev)) * np.cos(np.radians(azim)),
                                 np.sin(np.radians(elev))]))
    fig = plt.figure(figsize=(9, 7), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    pc = Poly3DCollection(tris[order], facecolors=cols[order],
                          edgecolors="none", linewidths=0)
    ax.add_collection3d(pc)
    if base_rgb is None:
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        fig.colorbar(sm, ax=ax, shrink=0.62, pad=0.08,
                     label=colorbar_label or "")
    ax.set_xlim(xlim or (coords[:, 0].min() - 4, coords[:, 0].max() + 4))
    ax.set_ylim(ylim or (coords[:, 1].min() - 4, coords[:, 1].max() + 4))
    ax.set_zlim(zlim or (coords[:, 2].min() - 4, coords[:, 2].max() + 4))
    ax.set_box_aspect((np.ptp(coords[:, 0]) + 8, np.ptp(coords[:, 1]) + 8,
                       np.ptp(coords[:, 2]) + 8))
    ax.view_init(elev=elev, azim=azim)
    ax.set_xlabel("X [mm]"); ax.set_ylabel("Y [mm]"); ax.set_zlabel("Z [mm]")
    ax.set_title(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(fname, bbox_inches="tight")
    plt.close(fig)
    print("wrote", fname)


face_vm = vm[bf].mean(axis=1)
vmax = float(vm.max())

# iso contour
render(coords, bf, face_vm, f"contour_{a.tag}_iso.png", 18, -58,
       f"{a.title} — von Mises stress (max {vmax:.0f} MPa)",
       vmin=0.0, vmax=vmax, colorbar_label="von Mises [MPa]")
# corner close-up: fillet region x 0..38, z 58..92
render(coords, bf, face_vm, f"contour_{a.tag}_corner.png", 12, -35,
       f"{a.title} — inner-corner detail (hotspot at fillet)",
       vmin=0.0, vmax=vmax, colorbar_label="von Mises [MPa]",
       xlim=(0, 38), ylim=(-34, 34), zlim=(58, 92))
# view from the wall side (shows the fixed plate + arm underside)
render(coords, bf, face_vm, f"contour_{a.tag}_back.png", 22, 125,
       f"{a.title} — von Mises, view from mounting side",
       vmin=0.0, vmax=vmax, colorbar_label="von Mises [MPa]")

# deformed shape (grey) vs undeformed (wireframe-ish translucent)
deformed = coords + u * a.defl_scale
maxu = float(np.linalg.norm(u, axis=1).max())
fig = plt.figure(figsize=(9, 7), dpi=150)
ax = fig.add_subplot(111, projection="3d")
tris_u = coords[bf]
order = np.argsort(tris_u.mean(axis=1)[:, 0])
ax.add_collection3d(Poly3DCollection(
    tris_u, facecolors=(0.75, 0.78, 0.82, 0.25),
    edgecolors=(0.3, 0.3, 0.3, 0.15), linewidths=0.1))
tris_d = deformed[bf]
n = np.cross(tris_d[:, 1] - tris_d[:, 0], tris_d[:, 2] - tris_d[:, 0])
ln = np.linalg.norm(n, axis=1, keepdims=True)
n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
shade = 0.72 + 0.28 * np.abs(n @ LIGHT)
cols = np.array([0.85, 0.35, 0.25])[None, :] * shade[:, None]
ax.add_collection3d(Poly3DCollection(tris_d, facecolors=cols, edgecolors="none"))
ax.set_xlim(coords[:, 0].min() - 4, coords[:, 0].max() + 4)
ax.set_ylim(coords[:, 1].min() - 4, coords[:, 1].max() + 4)
ax.set_zlim(coords[:, 2].min() - 4, coords[:, 2].max() + 4)
ax.set_box_aspect((np.ptp(coords[:, 0]) + 8, np.ptp(coords[:, 1]) + 8,
                   np.ptp(coords[:, 2]) + 8))
ax.view_init(elev=18, azim=-58)
ax.set_xlabel("X [mm]"); ax.set_ylabel("Y [mm]"); ax.set_zlabel("Z [mm]")
ax.set_title(f"{a.title} — deformed shape x{a.defl_scale:.0f} "
             f"(true max deflection {maxu:.3f} mm); grey = undeformed", fontsize=11)
fig.tight_layout()
fig.savefig(f"deformed_{a.tag}.png", bbox_inches="tight")
plt.close(fig)
print("wrote", f"deformed_{a.tag}.png")
print("RENDER_OK", a.tag)
