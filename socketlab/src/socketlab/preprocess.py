from __future__ import annotations

import numpy as np


def _rotation_matrix_from_vectors(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Return 3x3 rotation matrix that rotates unit vector a to unit vector b."""
    a = a / (np.linalg.norm(a) + 1e-12)
    b = b / (np.linalg.norm(b) + 1e-12)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    s = float(np.linalg.norm(v))
    if s < 1e-8:
        return np.eye(3, dtype=float) if c > 0 else -np.eye(3, dtype=float)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]], dtype=float)
    R = np.eye(3) + vx + vx @ vx * ((1 - c) / (s**2 + 1e-12))
    return R


def normalize_pose(vertices: np.ndarray, faces: np.ndarray, dz_mm: float = 10.0):
    """
    Normalize limb pose to a canonical frame:
    - Align principal (long) axis to +Z via PCA
    - Slice along Z, compute centroid per slice, take median XY centroid and recenter XY
    - Set min Z to 0 (distal)

    Returns: (vertices_norm, T_world_to_norm 4x4)
    """
    V = np.asarray(vertices, dtype=float)
    if V.ndim != 2 or V.shape[1] != 3 or V.shape[0] < 3:
        T = np.eye(4)
        return V.copy(), T
    # PCA on centered points
    mean = V.mean(axis=0)
    X = V - mean
    C = np.cov(X.T)
    try:
        w, U = np.linalg.eigh(C)  # ascending eigenvalues
    except Exception:
        T = np.eye(4)
        return V.copy(), T
    axis = U[:, np.argmax(w)]  # principal component
    z = np.array([0.0, 0.0, 1.0])
    R = _rotation_matrix_from_vectors(axis, z)
    V1 = (R @ X.T).T  # rotate around origin (mean)

    # Slice along Z and compute XY centroids
    zmin, zmax = float(V1[:, 2].min()), float(V1[:, 2].max())
    if not np.isfinite(zmin) or not np.isfinite(zmax) or zmax <= zmin:
        T = np.eye(4)
        return V.copy(), T
    dz = max(dz_mm, 1.0)
    zs = np.arange(zmin, zmax + 0.5 * dz, dz)
    cents = []
    for z0 in zs:
        z1 = z0 + dz
        slab = V1[(V1[:, 2] >= z0) & (V1[:, 2] < z1)]
        if slab.shape[0] >= 50:
            cents.append(slab[:, :2].mean(axis=0))
    if len(cents) == 0:
        xy_med = V1[:, :2].mean(axis=0)
    else:
        cents = np.array(cents)
        xy_med = np.median(cents, axis=0)
    # recenter XY; set min Z to 0
    V2 = V1.copy()
    V2[:, 0] -= xy_med[0]
    V2[:, 1] -= xy_med[1]
    z_shift = float(V2[:, 2].min())
    V2[:, 2] -= z_shift

    # Compose T_world_to_norm: T = Tz * Txy * R * T(-mean)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = -mean
    Txy = np.eye(4); Txy[0, 3] = -xy_med[0]; Txy[1, 3] = -xy_med[1]
    Tz = np.eye(4); Tz[2, 3] = -z_shift
    T = Tz @ Txy @ T
    return V2, T
