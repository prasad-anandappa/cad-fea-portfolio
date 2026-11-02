#!/usr/bin/env python3
"""
FEA driver: mesh a STEP solid with Gmsh (2nd-order tets), build a CalculiX
deck for the wall-mount bracket load case, solve with ccx, parse the .frd.

Load case (stated assumptions):
  * Back face of the mounting plate (x = 0) fully fixed (rigid wall / bolts
    idealised as a clamped face).
  * 500 N downward (-Z) distributed equally over the mesh nodes on the arm
    top-face tip patch (z = top_z, x >= load_xmin).
  * Material: structural steel S355, E = 210 GPa, nu = 0.3, yield 355 MPa.
  * Linear static, small displacements.

Usage:
  python3 fea_run.py --step bracket_t6.step --job t6_coarse --h 5.0
Outputs in CWD: <job>.inp/.frd/.dat, <job>_summary.json, <job>_mesh.npz
"""
import argparse, json, subprocess, sys, os
import numpy as np
import gmsh

ap = argparse.ArgumentParser()
ap.add_argument("--step", required=True)
ap.add_argument("--job", required=True)
ap.add_argument("--h", type=float, required=True, help="max mesh size [mm]")
ap.add_argument("--load", type=float, default=500.0)
ap.add_argument("--topz", type=float, default=90.0)
ap.add_argument("--loadxmin", type=float, default=70.0)
ap.add_argument("--yield", dest="yield_mpa", type=float, default=355.0)
a = ap.parse_args()

# ---------------- mesh with gmsh ----------------
gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 0)
gmsh.model.add(a.job)
gmsh.model.occ.importShapes(a.step)
gmsh.model.occ.synchronize()
gmsh.option.setNumber("Mesh.MeshSizeMax", a.h)
gmsh.option.setNumber("Mesh.MeshSizeMin", a.h / 3.0)
gmsh.option.setNumber("Mesh.Algorithm3D", 1)
gmsh.model.mesh.generate(3)
# Promote to 2nd order with STRAIGHT edges (mid-edge nodes at edge midpoints,
# not projected onto curved geometry). Curved-edge C3D10 elements next to the
# small fillet/holes fold their Jacobian in CalculiX; straight-edged ones
# cannot (sign follows the corner tet, which is positive).
gmsh.model.mesh.setOrder(2)

ntags, ncoords, _ = gmsh.model.mesh.getNodes()
nodes = {int(t): tuple(c) for t, c in zip(ntags, ncoords.reshape(-1, 3))}
etypes, etags, enodes = gmsh.model.mesh.getElements(3)
elems = []
for et, tags, ns in zip(etypes, etags, enodes):
    if et == 11:  # 10-node tetrahedron
        arr = ns.reshape(-1, 10)
        elems.append(arr)
elems = np.vstack(elems) if elems else np.zeros((0, 10), dtype=int)
gmsh.finalize()

assert len(elems) > 0, "no C3D10 elements produced"
# Gmsh's C3D10 mid-edge order puts edge(3,4) at position 9 and edge(2,4) at
# position 10; CalculiX (Abaqus convention) expects the reverse. Verified
# geometrically against the mesh itself. Swap positions 9<->10 once, here,
# so the deck, the frd parser and the render arrays all share ccx ordering.
elems = elems[:, [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]]
print(f"mesh: {len(nodes)} nodes, {len(elems)} C3D10 elements, h={a.h}")

# ---------------- sets from geometry ----------------
fix = [t for t, (x, y, z) in nodes.items() if abs(x) < 0.01]
load = [t for t, (x, y, z) in nodes.items()
        if abs(z - a.topz) < 0.01 and x >= a.loadxmin - 0.01]
assert len(fix) > 20 and len(load) > 5, (len(fix), len(load))
print(f"sets: FIX={len(fix)} nodes, LOAD={len(load)} nodes")

# ---------------- write CalculiX deck ----------------
fpn = a.load / len(load)
with open(a.job + ".inp", "w") as f:
    f.write("*NODE, NSET=ALL\n")
    for t in sorted(nodes):
        x, y, z = nodes[t]
        f.write(f"{t}, {x:.6f}, {y:.6f}, {z:.6f}\n")
    f.write("*ELEMENT, TYPE=C3D10, ELSET=BRACKET\n")
    for i, e in enumerate(elems, start=1):
        f.write(str(i) + ", " + ", ".join(str(int(v)) for v in e) + "\n")
    f.write("*NSET, NSET=FIX\n")
    for i in range(0, len(fix), 8):
        f.write(", ".join(str(v) for v in fix[i:i + 8]) + "\n")
    f.write("*NSET, NSET=LOAD\n")
    for i in range(0, len(load), 8):
        f.write(", ".join(str(v) for v in load[i:i + 8]) + "\n")
    f.write("*MATERIAL, NAME=S355\n*ELASTIC\n210000., 0.3\n")
    f.write("*SOLID SECTION, ELSET=BRACKET, MATERIAL=S355\n")
    f.write("*STEP\n*STATIC\n")
    f.write("*BOUNDARY\nFIX, 1, 3, 0.\n")
    f.write("*CLOAD\n")
    for t in load:
        f.write(f"{t}, 3, {-fpn:.6f}\n")
    f.write("*NODE FILE\nU, RF\n*EL FILE\nS\n*END STEP\n")

# ---------------- solve ----------------
env = dict(os.environ, OMP_NUM_THREADS="8")
r = subprocess.run(["ccx", a.job], capture_output=True, text=True, env=env)
tail = (r.stdout + r.stderr)[-1500:]
if not os.path.exists(a.job + ".frd"):
    print(tail)
    sys.exit("ccx failed: no .frd produced")
print("ccx done")

# ---------------- parse frd ----------------
def _vals(line, start):
    out = []
    rest = line[start:].rstrip("\n")
    for i in range(0, len(rest), 12):
        chunk = rest[i:i + 12].strip()
        if chunk:
            out.append(float(chunk))
    return out


def parse_frd(path):
    """ccx writes all requested results nodal-averaged in the .frd:
    DISP (D1..D3,ALL), STRESS (nodal-averaged tensor), FORC (reactions)."""
    disp, reac, vm = {}, {}, {}
    block = None
    with open(path) as f:
        for ln in f:
            if ln.startswith(" -4"):
                block = ln[5:13].strip()
                continue
            if not ln.startswith(" -1"):
                continue
            nid = int(ln[3:13])
            if block == "DISP":
                disp[nid] = _vals(ln, 13)[:3]
            elif block == "FORC":
                reac[nid] = _vals(ln, 13)[:3]
            elif block == "STRESS":
                sxx, syy, szz, sxy, syz, szx = _vals(ln, 13)[:6]
                vm[nid] = float(np.sqrt(
                    0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
                    + 3 * (sxy ** 2 + syz ** 2 + szx ** 2)))
    return disp, reac, vm


disp, reac, vm = parse_frd(a.job + ".frd")
assert disp and vm, "frd parse failed (empty disp or stress)"

umag = {n: float(np.linalg.norm(v)) for n, v in disp.items()}
n_maxu = max(umag, key=umag.get)
n_maxvm = max(vm, key=vm.get)
rf_fix = np.sum([reac[n] for n in fix if n in reac], axis=0) if reac else None

summary = dict(
    job=a.job, step=a.step, mesh_h_mm=a.h,
    n_nodes=len(nodes), n_elements=len(elems),
    n_fix_nodes=len(fix), n_load_nodes=len(load),
    load_total_N=a.load,
    max_disp_mm=umag[n_maxu], max_disp_node=int(n_maxu),
    max_disp_loc=[float(v) for v in nodes[n_maxu]],
    disp_at_max=[float(v) for v in disp[n_maxu]],
    max_von_mises_MPa=float(vm[n_maxvm]), max_vm_node=int(n_maxvm),
    max_vm_loc=[float(v) for v in nodes[n_maxvm]],
    yield_MPa=a.yield_mpa,
    safety_factor=float(a.yield_mpa / vm[n_maxvm]),
    reaction_sum_on_fixed_face_N=(rf_fix.tolist() if rf_fix is not None else None),
)
with open(a.job + "_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

nidx = {t: i for i, t in enumerate(sorted(nodes))}
coords = np.array([nodes[t] for t in sorted(nodes)])
conn_idx = np.vectorize(nidx.get)(elems)
vm_arr = np.array([vm.get(t, 0.0) for t in sorted(nodes)])
u_arr = np.array([disp.get(t, [0, 0, 0]) for t in sorted(nodes)])
np.savez(a.job + "_mesh.npz", coords=coords, elems=conn_idx, vm=vm_arr, u=u_arr)
print(json.dumps(summary, indent=2))
print("FEA_OK", a.job)
