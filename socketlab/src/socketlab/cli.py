from __future__ import annotations

import argparse
import os
from typing import Optional, List

import numpy as np
import trimesh as tm

from .types import MakeSocketOptions, MakeSocketResult
from .io import load_mesh, check_units_mm, save_mesh, save_json, sha256_file, apply_scale
from .offset import make_shell_inner_outer, trim_with_plane_volumetric, auto_voxel_mm
from .qc import compute_sections, write_sections_csv
from .prov import write_provenance


def make_socket(opts: MakeSocketOptions) -> MakeSocketResult:
    limb = load_mesh(opts.limb_path)
    ok_units, bbox = check_units_mm(limb)
    scale_applied = 1.0
    # Optional explicit scaling can override heuristics (injected via parsed args in main)
    # Note: parsed args are only known inside main; here we rely on environment via attributes set there.
    assume_units = getattr(opts, "assume_units", None)
    scale_factor = getattr(opts, "scale_factor", None)

    if scale_factor is not None and scale_factor > 0:
        limb = apply_scale(limb, float(scale_factor))
        scale_applied = float(scale_factor)
        ok_units, bbox = check_units_mm(limb)
    elif assume_units in ("m", "cm"):
        sf = 1000.0 if assume_units == "m" else 10.0
        limb = apply_scale(limb, sf)
        scale_applied = sf
        ok_units, bbox = check_units_mm(limb)
    elif not ok_units:
        # If the mesh is too small, assume meters and scale to mm.
        mx = max(bbox)
        if mx < 5.0:
            limb = apply_scale(limb, 1000.0)
            scale_applied = 1000.0
            ok_units, bbox = check_units_mm(limb)

    voxel_mm = opts.voxel_mm or auto_voxel_mm(tuple(map(float, bbox)))
    # For very small meshes, force a finer voxel pitch
    if max(bbox) < 100.0:
        voxel_mm = min(voxel_mm, 0.4)
    inner, outer, shell = make_shell_inner_outer(limb, opts.base_clearance_mm, opts.wall_thickness_mm, voxel_mm, marks=getattr(opts, 'marks', None))

    trimmed = shell
    if opts.trim_z_mm is not None:
        trimmed = trim_with_plane_volumetric(shell, voxel_mm, opts.trim_z_mm)

    os.makedirs(opts.outdir, exist_ok=True)
    socket_inner_path = os.path.join(opts.outdir, "socket_inner.stl")
    socket_outer_path = os.path.join(opts.outdir, "socket_outer.stl")
    socket_trimmed_path = os.path.join(opts.outdir, "socket_trimmed.stl")
    save_mesh(inner, socket_inner_path)
    save_mesh(outer, socket_outer_path)
    save_mesh(trimmed, socket_trimmed_path)

    # QC slices every 10 mm along Z
    zmin, zmax = float(trimmed.bounds[0][2]), float(trimmed.bounds[1][2])
    step = 10.0
    z_values = np.arange(zmin, zmax + 0.5 * step, step)
    sections = compute_sections(trimmed, z_values)
    sections_csv_path = os.path.join(opts.outdir, "sections.csv")
    write_sections_csv(sections, sections_csv_path)

    # Provenance
    provenance_path = os.path.join(opts.outdir, "provenance.json")
    params = {
        "offset_mode": "volumetric",
        "base_clearance_mm": float(opts.base_clearance_mm),
        "wall_mm": float(opts.wall_thickness_mm),
        "trim": {"mode": "plane" if opts.trim_z_mm is not None else "none", "z_mm": opts.trim_z_mm},
        "voxel_mm": float(voxel_mm),
        "scale_applied": scale_applied,
    }
    if getattr(opts, 'marks', None):
        params["marks"] = getattr(opts, 'marks')
    stats = {
        "bbox_mm": [float(bbox[0]), float(bbox[1]), float(bbox[2])],
    "faces": int(trimmed.faces.shape[0]),
        "sections": int(len(sections)),
        "volume_cm3": float(trimmed.volume) / 1000.0 if trimmed.is_volume else None,
    }
    inputs = {
        "limb_mesh_sha256": sha256_file(opts.limb_path) if os.path.exists(opts.limb_path) else None,
        "annotations_sha256": None,
    }
    write_provenance(provenance_path, "0.1.0", inputs, params, stats)

    return MakeSocketResult(
        socket_inner_path=socket_inner_path,
        socket_outer_path=socket_outer_path,
        socket_trimmed_path=socket_trimmed_path,
        sections_csv_path=sections_csv_path,
        provenance_path=provenance_path,
        stats=stats,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="socketlab", description="Generate prosthetic socket from limb mesh")
    sub = p.add_subparsers(dest="cmd")
    m = sub.add_parser("make-socket", help="Create socket STL from limb mesh")
    m.add_argument("--limb", required=True, help="Path to limb mesh (STL/OBJ) in mm")
    m.add_argument("--outdir", required=True, help="Output directory")
    m.add_argument("--base-clearance-mm", type=float, default=2.5)
    m.add_argument("--wall-mm", type=float, default=4.0)
    m.add_argument("--trim-z-mm", type=float, default=None)
    m.add_argument("--voxel-mm", type=float, default=None)
    m.add_argument("--decimate-preview", action="store_true")
    m.add_argument("--assume-units", choices=["mm", "cm", "m"], default=None, help="If provided, rescale to mm from these units before processing.")
    m.add_argument("--scale-factor", type=float, default=None, help="Explicit scale applied to the mesh before processing (e.g., 1000 for m→mm).")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    p = build_arg_parser()
    args = p.parse_args(argv)
    if args.cmd == "make-socket":
        opts = MakeSocketOptions(
            limb_path=args.limb,
            outdir=args.outdir,
            base_clearance_mm=args.base_clearance_mm,
            wall_thickness_mm=args.wall_mm,
            trim_z_mm=args.trim_z_mm,
            voxel_mm=args.voxel_mm,
            decimate_preview=args.decimate_preview,
        )
        # Attach optional scaling knobs to opts dynamically
        setattr(opts, "assume_units", args.assume_units)
        setattr(opts, "scale_factor", args.scale_factor)
        res = make_socket(opts)
    print("Socket written:", res.socket_trimmed_path)
    return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
