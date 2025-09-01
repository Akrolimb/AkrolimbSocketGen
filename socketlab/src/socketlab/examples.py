from __future__ import annotations

import os
import numpy as np
import trimesh as tm


def generate_tapered_cylinder(height_mm: float = 200.0, r_top_mm: float = 40.0, r_bottom_mm: float = 60.0, segments: int = 128) -> tm.Trimesh:
    zs = np.array([0.0, height_mm])
    rs = np.array([r_bottom_mm, r_top_mm])
    theta = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    verts = []
    for zi, ri in zip(zs, rs):
        for t in theta:
            x = ri * np.cos(t)
            y = ri * np.sin(t)
            verts.append([x, y, zi])
    verts = np.array(verts)
    faces = []
    for i in range(segments):
        i0 = i
        i1 = (i + 1) % segments
        j0 = i + segments
        j1 = ((i + 1) % segments) + segments
        faces.append([i0, i1, j1])
        faces.append([i0, j1, j0])
    mesh = tm.Trimesh(vertices=verts, faces=np.array(faces), process=True)
    mesh.fix_normals()
    return mesh


def write_example(path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mesh = generate_tapered_cylinder()
    mesh.export(path)
    return path
