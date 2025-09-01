from __future__ import annotations

import hashlib
import json
import os
from typing import Tuple

import numpy as np
import trimesh as tm
from trimesh import repair as tmrepair


MM_BOUNDS = (30.0, 1000.0)  # expected bbox range in mm


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_mesh(path: str) -> tm.Trimesh:
    mesh = tm.load(path, force="mesh")
    if isinstance(mesh, tm.Scene):
        mesh = tm.util.concatenate(tuple(m for m in mesh.dump().geometry.values()))
    mesh.remove_unreferenced_vertices()
    mesh.remove_duplicate_faces()
    mesh.remove_degenerate_faces()
    mesh.process(validate=True)
    # Ensure normals are coherent outward
    mesh.rezero()
    if not mesh.is_watertight:
        try:
            tmrepair.fill_holes(mesh)
        except Exception:
            pass
    mesh.fix_normals()
    return mesh


def check_units_mm(mesh: tm.Trimesh) -> Tuple[bool, Tuple[float, float, float]]:
    extents = mesh.extents
    dx, dy, dz = float(extents[0]), float(extents[1]), float(extents[2])
    mx = max(dx, dy, dz)
    ok = MM_BOUNDS[0] <= mx <= MM_BOUNDS[1]
    return ok, (dx, dy, dz)


def save_mesh(mesh: tm.Trimesh, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mesh.export(path)


def save_json(data, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def apply_scale(mesh: tm.Trimesh, scale: float) -> tm.Trimesh:
    if scale and abs(scale - 1.0) > 1e-9:
        mesh = mesh.copy()
        mesh.apply_scale(scale)
        mesh.process(validate=True)
        mesh.fix_normals()
    return mesh
