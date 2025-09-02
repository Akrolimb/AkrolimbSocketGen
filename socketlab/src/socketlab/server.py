from __future__ import annotations

import os
import time
import uuid
from typing import Optional

import logging
import traceback
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .types import MakeSocketOptions
from .cli import make_socket


# Prefer env DATA_ROOT; otherwise default to the repo root (three parents up from this file)
_default_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))
DATA_ROOT = os.environ.get("DATA_ROOT", _default_root)
UPLOADS_DIR = os.path.join(DATA_ROOT, "uploads")
OUT_DIR = os.path.join(DATA_ROOT, "out")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

app = FastAPI(title="Akrolimb SocketLab API", version="0.1.0")
logger = logging.getLogger("socketlab.api")
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/make-socket")
async def api_make_socket(
    file: Optional[UploadFile] = File(default=None),
    limb_path: Optional[str] = Form(default=None),
    base_clearance_mm: float = Form(default=2.5),
    wall_mm: float = Form(default=4.0),
    trim_z_mm: Optional[float] = Form(default=None),
    voxel_mm: Optional[float] = Form(default=None),
    assume_units: Optional[str] = Form(default=None),  # mm|cm|m
    scale_factor: Optional[float] = Form(default=None),
):
    dbg_id = uuid.uuid4().hex[:8]
    logger.info("[%s] POST /api/make-socket", dbg_id)
    if not file and not limb_path:
        raise HTTPException(status_code=400, detail="Provide file upload or limb_path.")

    # Resolve input path
    if file is not None:
        suffix = os.path.splitext(file.filename or "upload.glb")[1] or ".glb"
        stem = os.path.splitext(file.filename or "upload")[0]
        ts = time.strftime("%Y%m%d-%H%M%S")
        unique = f"{stem}_{ts}_{uuid.uuid4().hex[:8]}{suffix}"
        save_path = os.path.join(UPLOADS_DIR, unique)
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)
        limb_abs = save_path
    else:
        # limb_path is relative to DATA_ROOT or absolute
        raw = (limb_path or "").strip()
        lp = Path(raw)
        # On Windows, a path like '/foo' has empty drive and root '/', treat as relative
        if not lp.is_absolute() or (not lp.drive and lp.root == '/'):
            limb_abs = str(Path(DATA_ROOT) / raw.lstrip('/\\'))
        else:
            limb_abs = str(lp)
        # Fallbacks: try testModel/ and webviewer/public if not found
        if not os.path.exists(limb_abs):
            name = os.path.basename(raw.lstrip('/\\'))
            cand1 = str(Path(DATA_ROOT) / 'testModel' / name)
            cand2 = str(Path(DATA_ROOT) / 'webviewer' / 'public' / name)
            if os.path.exists(cand1):
                limb_abs = cand1
            elif os.path.exists(cand2):
                limb_abs = cand2

    logger.info(
        "[%s] DATA_ROOT=%s limb_path_in=%s resolved=%s exists=%s",
        dbg_id,
        DATA_ROOT,
        limb_path if limb_path is not None else (file.filename if file else None),
        limb_abs,
        os.path.exists(limb_abs),
    )
    if not os.path.exists(limb_abs):
        raise HTTPException(status_code=404, detail=f"Input file not found: {limb_abs}")

    # Prepare output directory (unique)
    base_name = os.path.splitext(os.path.basename(limb_abs))[0]
    ts = time.strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(OUT_DIR, f"{base_name}_{ts}_{uuid.uuid4().hex[:6]}")
    os.makedirs(outdir, exist_ok=True)

    # Build options and call make_socket
    opts = MakeSocketOptions(
        limb_path=limb_abs,
        outdir=outdir,
        base_clearance_mm=float(base_clearance_mm),
        wall_thickness_mm=float(wall_mm),
        trim_z_mm=float(trim_z_mm) if trim_z_mm is not None else None,
        voxel_mm=float(voxel_mm) if voxel_mm is not None else None,
        decimate_preview=False,
    )
    # Attach scaling hints used by make_socket()
    if assume_units is not None:
        setattr(opts, "assume_units", assume_units)
    if scale_factor is not None:
        try:
            setattr(opts, "scale_factor", float(scale_factor))
        except Exception:
            pass

    try:
        res = make_socket(opts)
    except Exception as e:
        logger.exception("[%s] make_socket failed: %s", dbg_id, e)
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}\n{tb}")

    # Build static URLs (we mount DATA_ROOT at /static)
    def to_static_url(p: str) -> str:
        # Return path relative to DATA_ROOT
        rel = os.path.relpath(p, DATA_ROOT).replace("\\", "/")
        return f"/static/{rel}"

    # Extract scale_applied from provenance for viewer alignment
    scale_applied = 1.0
    try:
        import json as _json
        with open(res.provenance_path, "r", encoding="utf-8") as f:
            prov = _json.load(f)
        scale_applied = float(prov.get("params", {}).get("scale_applied", 1.0))
    except Exception:
        pass

    # Compute centers in mm for limb and socket (bbox centers) for alignment
    limb_center_mm = None
    socket_center_mm = None
    try:
        import trimesh as _tm
        _limb = _tm.load(limb_abs, force="mesh")
        if isinstance(_limb, _tm.Scene):
            _limb = _tm.util.concatenate(tuple(m for m in _limb.dump().geometry.values()))
        if scale_applied and abs(scale_applied - 1.0) > 1e-9:
            _limb = _limb.copy(); _limb.apply_scale(scale_applied)
        lb = _limb.bounds
        limb_center_mm = [float((lb[0][i] + lb[1][i]) * 0.5) for i in range(3)]

        _sock = _tm.load(res.socket_trimmed_path, force="mesh")
        if isinstance(_sock, _tm.Scene):
            _sock = _tm.util.concatenate(tuple(m for m in _sock.dump().geometry.values()))
        sb = _sock.bounds
        socket_center_mm = [float((sb[0][i] + sb[1][i]) * 0.5) for i in range(3)]
    except Exception as e:
        logger.warning("[%s] center compute failed: %s", dbg_id, e)

    # Delta (socket minus limb) in mm
    delta_mm = None
    if limb_center_mm and socket_center_mm:
        delta_mm = [socket_center_mm[i] - limb_center_mm[i] for i in range(3)]

    return {
        "socket_inner_url": to_static_url(res.socket_inner_path),
        "socket_outer_url": to_static_url(res.socket_outer_path),
        "socket_trimmed_url": to_static_url(res.socket_trimmed_path),
        "sections_csv_url": to_static_url(res.sections_csv_path),
        "provenance_url": to_static_url(res.provenance_path),
        "stats": res.stats,
        "input_path": limb_abs,
        "outdir": outdir,
        "input_exists": True,
        "data_root": DATA_ROOT,
        "scale_applied": scale_applied,
        "limb_center_mm": limb_center_mm,
        "socket_center_mm": socket_center_mm,
        "delta_mm": delta_mm,
    }


# Serve /static from DATA_ROOT so the frontend can fetch outputs
app.mount("/static", StaticFiles(directory=DATA_ROOT), name="static")


@app.get("/api/debug/resolve")
def debug_resolve(limb_path: str = Query(..., description="Path as provided by client")):
    raw = limb_path.strip()
    lp = Path(raw)
    candidates = []
    if not lp.is_absolute() or (not lp.drive and lp.root == '/'):
        candidates.append(str(Path(DATA_ROOT) / raw.lstrip('/\\')))
    else:
        candidates.append(str(lp))
    name = os.path.basename(raw.lstrip('/\\'))
    candidates.append(str(Path(DATA_ROOT) / 'testModel' / name))
    candidates.append(str(Path(DATA_ROOT) / 'webviewer' / 'public' / name))
    hit = next((c for c in candidates if os.path.exists(c)), None)
    return {
        "provided": limb_path,
        "DATA_ROOT": DATA_ROOT,
        "candidates": candidates,
        "resolved": hit,
        "exists": bool(hit),
    }


def main():
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("socketlab.src.socketlab.server:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
