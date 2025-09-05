from __future__ import annotations

import json
from typing import Dict, Any


def detect_markings_from_glb(glb_in: str, glb_out: str, anno_out: str, color_profiles: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Minimal stub for marking detection. Writes empty annotations and copies pass-through GLB path.
    Replace with HSV segmentation + UV back-projection.
    """
    ann = {"units": "mm", "curves": []}
    with open(anno_out, 'w', encoding='utf-8') as f:
        json.dump(ann, f, indent=2)
    # For MVP, "overlay glb" is just the input; the viewer already supports overlaying STL; GLB overlay can be added later
    return {"curves": 0, "overlay_path": glb_out, "annotations": anno_out}
