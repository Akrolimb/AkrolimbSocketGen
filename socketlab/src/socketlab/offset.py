from __future__ import annotations

from typing import Optional, Tuple, List, Dict, Any

import numpy as np
import trimesh as tm
from skimage.morphology import ball
from skimage import measure
from scipy.ndimage import binary_dilation, binary_erosion
from scipy.ndimage import distance_transform_edt


def auto_voxel_mm(bbox_mm: Tuple[float, float, float]) -> float:
    # Aim for ~384 voxels along the long axis for better fidelity; clamp 0.3–1.0mm
    target = max(bbox_mm) / 384.0
    return float(np.clip(target, 0.3, 1.0))


def volumetric_offset_mesh(
    mesh: tm.Trimesh, offset_mm: float, voxel_mm: Optional[float] = None
) -> tm.Trimesh:
    # Voxelization via Trimesh voxelized fill with pitch = voxel_mm
    bbox = mesh.bounding_box.extents
    if voxel_mm is None:
        voxel_mm = auto_voxel_mm(tuple(map(float, bbox)))

    vox, grid, voxel_mm = _voxelize_surface(mesh, voxel_mm)

    # Compute radius in voxels for the offset using a spherical structuring element
    r_vox = max(1, int(round(abs(offset_mm) / voxel_mm)))
    selem = ball(r_vox)

    # For dilation (positive offset), we want to grow outward; for negative, erode
    if offset_mm >= 0:
        grid2 = binary_dilation(grid, structure=selem)
    else:
        grid2 = binary_erosion(grid, structure=selem)

    # Marching cubes to surface
    grid_mc = _ensure_min_shape(grid2)
    verts, faces, normals, _ = measure.marching_cubes(grid_mc.astype(np.uint8), level=0.5, spacing=(voxel_mm, voxel_mm, voxel_mm))

    # marching_cubes gives coordinates in voxel space; map to world by adding transform translation
    origin = np.array(vox.transform[:3, 3])
    verts = verts + origin

    out = tm.Trimesh(vertices=verts, faces=faces, process=True)
    out.remove_degenerate_faces()
    out.remove_duplicate_faces()
    out.remove_unreferenced_vertices()
    out.process(validate=True)
    out.fix_normals()
    return out


def make_shell_inner_outer(
    limb: tm.Trimesh,
    base_clearance_mm: float,
    wall_mm: float,
    voxel_mm: Optional[float] = None,
    marks: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[tm.Trimesh, tm.Trimesh, tm.Trimesh]:
    """Return inner, outer, and solid shell (outer minus inner) meshes via volumetric banding."""
    bbox = limb.bounding_box.extents
    if voxel_mm is None:
        voxel_mm = auto_voxel_mm(tuple(map(float, bbox)))

    vox, grid, voxel_mm = _voxelize_surface(limb, voxel_mm)

    r_clear = max(1, int(round(abs(base_clearance_mm) / voxel_mm)))
    r_wall = max(1, int(round(abs(wall_mm) / voxel_mm)))
    selem_c = ball(r_clear)
    selem_w = ball(r_wall)

    # Pad to allow dilation to grow outward
    pad_vox = r_clear + r_wall + 3
    grid_padded = _pad_grid(grid, pad_vox)

    inner_grid = _safe_dilation(grid_padded, r_clear)
    outer_grid = _safe_dilation(inner_grid, r_wall)

    # Apply local mark adjustments on the shell band if provided
    if marks:
        inner_grid, outer_grid = _apply_marks(inner_grid, outer_grid, voxel_mm, origin=np.array(vox.transform[:3, 3]) - pad_vox * voxel_mm, marks=marks)

    shell_grid = outer_grid & (~inner_grid)
    if not shell_grid.any():
        # Approximate shell by boundary of outer
        shell_grid = outer_grid & (~binary_erosion(outer_grid, structure=ball(1)))

    origin = np.array(vox.transform[:3, 3]) - pad_vox * voxel_mm
    spacing = (voxel_mm, voxel_mm, voxel_mm)
    # Surfaces for inner and outer (for reference/outputs)
    # Shell is primary
    vs, fs, ns, _ = measure.marching_cubes(_ensure_min_shape(shell_grid).astype(np.uint8), level=0.5, spacing=spacing)
    vs += origin
    shell = tm.Trimesh(vertices=vs, faces=fs, process=True)
    # For M0, mirror shell to inner/outer for export stability
    inner = shell.copy()
    outer = shell.copy()
    for m in (inner, outer, shell):
        m.remove_degenerate_faces(); m.remove_duplicate_faces(); m.remove_unreferenced_vertices(); m.process(validate=True); m.fix_normals()
    return inner, outer, shell


def trim_with_plane_volumetric(mesh: tm.Trimesh, voxel_mm: float, z_trim: float) -> tm.Trimesh:
    """Trim by zeroing voxels above z_trim and remeshing."""
    vox, grid, voxel_mm = _voxelize_surface(mesh, voxel_mm)
    origin = np.array(vox.transform[:3, 3])
    spacing = (voxel_mm, voxel_mm, voxel_mm)

    # Build a mask with world Z for each voxel index
    nx, ny, nz = grid.shape
    # Voxel centers along z (last axis)
    z_coords = origin[2] + np.arange(nz) * voxel_mm
    mask = z_coords <= (z_trim + 0.5 * voxel_mm)
    grid[:, :, ~mask] = False

    grid_mc = _ensure_min_shape(grid)
    vs, fs, ns, _ = measure.marching_cubes(grid_mc.astype(np.uint8), level=0.5, spacing=spacing)
    vs += origin
    out = tm.Trimesh(vertices=vs, faces=fs, process=True)
    out.remove_degenerate_faces(); out.remove_duplicate_faces(); out.remove_unreferenced_vertices(); out.process(validate=True); out.fix_normals()
    return out


def _ensure_min_shape(grid: np.ndarray, min_size: int = 2) -> np.ndarray:
    """Pad grid with zeros to ensure each dimension is at least min_size."""
    pad = []
    for d in range(3):
        size = grid.shape[d]
        if size >= min_size:
            pad.append((0, 0))
        else:
            need = min_size - size
            pad.append((0, need))
    if any(p[1] > 0 for p in pad):
        return np.pad(grid, pad_width=tuple(pad), mode="constant", constant_values=False)
    return grid


def _voxelize_surface(mesh: tm.Trimesh, voxel_mm: float, retries: int = 3):
    """Voxelize surface occupancy (no fill). Retries with smaller pitch if degenerate. Returns (vox, grid, voxel_mm)."""
    v = voxel_mm
    last_vox = None
    for _ in range(retries + 1):
        vox = mesh.voxelized(pitch=v)
        grid = vox.matrix.astype(bool)
        if grid.any() and not grid.all() and min(grid.shape) >= 2:
            return vox, grid, v
        last_vox = vox
        v = max(v * 0.5, 0.25)
    if last_vox is None:
        last_vox = mesh.voxelized(pitch=v)
    grid = last_vox.matrix.astype(bool)
    grid = _ensure_min_shape(grid)
    return last_vox, grid, v


def _pad_grid(grid: np.ndarray, pad: int) -> np.ndarray:
    if pad <= 0:
        return grid
    return np.pad(grid, pad_width=((pad, pad), (pad, pad), (pad, pad)), mode="constant", constant_values=False)


def _safe_dilation(grid: np.ndarray, r: int) -> np.ndarray:
    rr = max(1, int(r))
    while rr >= 1:
        g = binary_dilation(grid, structure=ball(rr))
        if g.any() and not g.all():
            return g
        rr -= 1
    return grid.copy()


def _apply_marks(inner_grid: np.ndarray, outer_grid: np.ndarray, voxel_mm: float, origin: np.ndarray, marks: List[Dict[str, Any]]):
    """Modify inner/outer occupancy using spherical marks:
    - pad: increase local clearance (grow inner locally)
    - relief: decrease local clearance (erode inner locally)
    - trim: cut shell entirely inside sphere
    """
    grid_shape = inner_grid.shape
    # Precompute voxel coordinate grid origin and spacing
    # Map world point p to voxel index approx: i = round((p - origin)/voxel_mm)
    for mk in marks:
        try:
            mtype = mk.get('type', 'pad')
            cx, cy, cz = [float(v) for v in mk.get('center_mm', mk.get('center', [0,0,0]))]
            radius_mm = float(mk.get('radius_mm', mk.get('radius', 10.0)))
            amount_mm = float(mk.get('amount_mm', mk.get('amount', 1.0)))
        except Exception:
            continue
        # Build a spherical mask in voxel space around center
        # Determine bounding box in voxel indices
        center_vox = np.round((np.array([cx, cy, cz]) - origin) / voxel_mm).astype(int)
        r_vox = max(1, int(np.ceil(radius_mm / voxel_mm)))
        # Bounds
        x0, x1 = max(0, center_vox[0]-r_vox), min(grid_shape[0]-1, center_vox[0]+r_vox)
        y0, y1 = max(0, center_vox[1]-r_vox), min(grid_shape[1]-1, center_vox[1]+r_vox)
        z0, z1 = max(0, center_vox[2]-r_vox), min(grid_shape[2]-1, center_vox[2]+r_vox)
        if x0>=x1 or y0>=y1 or z0>=z1:
            continue
        # Create local boolean cube
        lx = np.arange(x0, x1+1)
        ly = np.arange(y0, y1+1)
        lz = np.arange(z0, z1+1)
        gx, gy, gz = np.meshgrid(lx, ly, lz, indexing='ij')
        # World distance from sphere center for each voxel center
        px = origin[0] + gx * voxel_mm
        py = origin[1] + gy * voxel_mm
        pz = origin[2] + gz * voxel_mm
        dist = np.sqrt((px - cx)**2 + (py - cy)**2 + (pz - cz)**2)
        sphere = dist <= radius_mm

        if mtype == 'trim':
            # Zero out both inner and outer where sphere applies
            inner_grid[x0:x1+1, y0:y1+1, z0:z1+1][sphere] = False
            outer_grid[x0:x1+1, y0:y1+1, z0:z1+1][sphere] = False
            continue
        # For pad/relief, adjust inner surface position locally by amount_mm
        amt_vox = max(1, int(np.round(abs(amount_mm) / voxel_mm)))
        local = inner_grid[x0:x1+1, y0:y1+1, z0:z1+1]
        if mtype == 'pad':
            # Grow inner outward within the spherical region
            grown = binary_dilation(local, structure=ball(amt_vox))
            # Only apply inside the sphere mask to avoid global growth
            local[sphere] = grown[sphere]
        elif mtype == 'relief':
            er = binary_erosion(local, structure=ball(amt_vox))
            local[sphere] = er[sphere]
        inner_grid[x0:x1+1, y0:y1+1, z0:z1+1] = local
        # Ensure outer contains inner plus wall; grow outer if needed locally
        outer_local = outer_grid[x0:x1+1, y0:y1+1, z0:z1+1]
        need = inner_grid[x0:x1+1, y0:y1+1, z0:z1+1] & (~outer_local)
        if need.any():
            outer_local = outer_local | need
        outer_grid[x0:x1+1, y0:y1+1, z0:z1+1] = outer_local
    return inner_grid, outer_grid
