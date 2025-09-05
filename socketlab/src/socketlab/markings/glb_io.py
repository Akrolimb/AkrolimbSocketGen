from __future__ import annotations

import os
from typing import Dict, Any, List, Tuple

import numpy as np

try:
    import trimesh as tm
except Exception:  # pragma: no cover
    tm = None


def load_glb_with_textures(path: str) -> Dict[str, Any]:
    """Load GLB and return a simple dict with meshes and materials.
    For demo MVP we rely on trimesh to load geometry. Texture IO is stubbed.
    """
    if tm is None:
        raise RuntimeError("trimesh not available")
    scene = tm.load(path, force='scene')
    data = {
        'scene': scene,
        'meshes': [],
    }
    if isinstance(scene, tm.Scene):
        for name, geom in scene.geometry.items():
            g = geom
            uv = g.visual.uv if hasattr(g.visual, 'uv') else None
            data['meshes'].append({
                'name': name,
                'vertices': np.asarray(g.vertices),
                'faces': np.asarray(g.faces, dtype=np.int32),
                'uv': np.asarray(uv) if uv is not None else None,
                'visual': g.visual,
            })
    else:
        g = scene
        uv = g.visual.uv if hasattr(g.visual, 'uv') else None
        data['meshes'].append({
            'name': 'mesh',
            'vertices': np.asarray(g.vertices),
            'faces': np.asarray(g.faces, dtype=np.int32),
            'uv': np.asarray(uv) if uv is not None else None,
            'visual': g.visual,
        })
    return data
