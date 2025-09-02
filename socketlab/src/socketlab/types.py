from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class MakeSocketOptions:
    limb_path: str
    outdir: str
    base_clearance_mm: float = 2.5
    wall_thickness_mm: float = 4.0
    trim_z_mm: Optional[float] = None
    voxel_mm: Optional[float] = None  # None => auto (0.5–1.0mm based on bbox)
    decimate_preview: bool = False
    # Optional annotations/marks to modulate clearance/trim locally.
    # Format: List of dicts with keys: type ('pad'|'relief'|'trim'), center_mm [x,y,z], radius_mm, amount_mm
    marks: Optional[List[Dict[str, Any]]] = None
    marks_units: Optional[str] = None  # 'mm' or 'native'


@dataclass
class MakeSocketResult:
    socket_inner_path: str
    socket_outer_path: str
    socket_trimmed_path: str
    sections_csv_path: str
    provenance_path: str
    stats: Dict[str, Any]
