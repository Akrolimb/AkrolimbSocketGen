from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, Any

from .io import save_json


def write_provenance(path: str, socketlab_version: str, inputs: Dict[str, Any], params: Dict[str, Any], stats: Dict[str, Any]) -> None:
    data = {
        "socketlab_version": socketlab_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "inputs": inputs,
        "params": params,
        "stats": stats,
    }
    save_json(data, path)
