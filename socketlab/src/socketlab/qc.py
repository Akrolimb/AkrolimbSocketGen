from __future__ import annotations

import csv
from typing import Iterable, List, Dict

import numpy as np
import shapely.geometry as sgeom
import shapely.ops as sops
import trimesh as tm


def _section_polygons_xy(mesh: tm.Trimesh, z: float):
    section = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if section is None:
        return []
    planar, _ = section.to_planar()
    return planar.polygons_full


def compute_sections(mesh: tm.Trimesh, z_values: Iterable[float]) -> List[Dict]:
    rows: List[Dict] = []
    for z in z_values:
        polys = _section_polygons_xy(mesh, z)
        if not polys:
            continue
        loops = []
        for poly in polys:
            try:
                ext = np.asarray(poly.exterior.coords)
                if ext.shape[0] >= 3:
                    holes = []
                    for hole in getattr(poly, 'interiors', []):
                        hcoords = np.asarray(hole.coords)
                        if hcoords.shape[0] >= 3:
                            holes.append(hcoords)
                    loops.append(sgeom.Polygon(ext, holes))
            except Exception:
                continue
        if not loops:
            continue
        # Union all loops into a MultiPolygon for robust metrics
        geom = sops.unary_union(loops)
        if geom.is_empty:
            continue
        perimeter = float(geom.length)
        area = float(geom.area)
        # Equivalent diameter from area
        eq_diam = 2.0 * np.sqrt(area / np.pi)
        rows.append({
            "z_mm": float(z),
            "perimeter_mm": perimeter,
            "area_mm2": area,
            "equivalent_diameter_mm": eq_diam,
        })
    return rows


def write_sections_csv(rows: List[Dict], path: str) -> None:
    if not rows:
        # Write header even if empty
        rows = []
    fieldnames = ["z_mm", "perimeter_mm", "area_mm2", "equivalent_diameter_mm"]
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
