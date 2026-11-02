#!/usr/bin/env python3
"""
Shaded STL renders for case study 2 (matplotlib, headless).
Scenes: assembled (closed), exploded (lid lifted), base interior, lid top.
"""
import struct
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

D = "/workspace/cad-freelance/portfolio/case-study-2-enclosure/"
LIGHT = np.array([0.45, 0.5, 0.74]); LIGHT /= np.linalg.norm(LIGHT)


def read_stl(path):
    data = open(path, "rb").read()
    n = struct.unpack("<I", data[80:84])[0]
    dt = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])
    return np.frombuffer(data[84:84 + n * 50], dtype=dt)["v"].astype(np.float64)


def shade_cols(tris, rgb):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    shade = 0.62 + 0.38 * np.abs(n @ LIGHT)
    return np.array(rgb)[None, :] * shade[:, None]


def scene(parts, fname, title, elev, azim):
    """parts: list of (tris, rgb, offset)"""
    fig = plt.figure(figsize=(9, 7), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    allpts = []
    for tris, rgb, off in parts:
        t = tris + np.array(off)
        allpts.append(t.reshape(-1, 3))
        cols = shade_cols(t, rgb)
        view = np.array([np.cos(np.radians(elev)) * np.sin(np.radians(azim)),
                         -np.cos(np.radians(elev)) * np.cos(np.radians(azim)),
                         np.sin(np.radians(elev))])
        order = np.argsort(t.mean(axis=1) @ view)
        ax.add_collection3d(Poly3DCollection(t[order], facecolors=cols[order],
                                             edgecolors=(0, 0, 0, 0.05), linewidths=0.05))
    P = np.vstack(allpts)
    c = P.mean(axis=0); span = np.ptp(P, axis=0).max() / 2 + 6
    ax.set_xlim(c[0] - span, c[0] + span)
    ax.set_ylim(c[1] - span, c[1] + span)
    ax.set_zlim(P[:, 2].min() - 4, P[:, 2].min() - 4 + 2 * span)
    ax.view_init(elev=elev, azim=azim)
    ax.set_xlabel("X [mm]"); ax.set_ylabel("Y [mm]"); ax.set_zlabel("Z [mm]")
    ax.set_title(title, fontsize=11)
    fig.tight_layout(); fig.savefig(fname, bbox_inches="tight"); plt.close(fig)
    print("wrote", fname)


BASE_RGB = (0.30, 0.45, 0.75)
LID_RGB = (0.95, 0.55, 0.25)

for tag, bl, lw, bh in (("sizeA", "85x60 board", "95.8 x 70.8 mm", 30.0),
                        ("sizeB", "120x90 board", "130.8 x 100.8 mm", 34.0)):
    base = read_stl(D + f"{tag}_base.stl")
    lid = read_stl(D + f"{tag}_lid.stl")
    scene([(base, BASE_RGB, (0, 0, 0)), (lid, LID_RGB, (0, 0, 0))],
          D + f"render_{tag}_assembled.png",
          f"Enclosure {tag} ({bl}) — assembled, closed height {bh + 2.4:.1f} mm", 20, -52)
    scene([(base, BASE_RGB, (0, 0, 0)), (lid, LID_RGB, (0, 0, 42))],
          D + f"render_{tag}_exploded.png",
          f"Enclosure {tag} ({bl}) — exploded: lid lifted 42 mm", 20, -52)
    scene([(base, BASE_RGB, (0, 0, 0))],
          D + f"render_{tag}_base.png",
          f"Enclosure {tag} — base interior: standoff bosses, corner posts, gland hole", 42, -52)
    scene([(lid, LID_RGB, (0, 0, 0))],
          D + f"render_{tag}_lid.png",
          f"Enclosure {tag} — lid: vent slots + screw holes", 32, -52)
print("RENDER2_OK")
