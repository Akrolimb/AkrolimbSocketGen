from __future__ import annotations

import os
import time
import uuid
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .types import MakeSocketOptions
from .cli import make_socket


DATA_ROOT = os.environ.get("DATA_ROOT", "/data")
UPLOADS_DIR = os.path.join(DATA_ROOT, "uploads")
OUT_DIR = os.path.join(DATA_ROOT, "out")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

app = FastAPI(title="Akrolimb SocketLab API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
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
    if not file and not limb_path:
        return {"error": "Provide file upload or limb_path."}

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
        limb_abs = limb_path
        if not os.path.isabs(limb_abs):
            limb_abs = os.path.join(DATA_ROOT, limb_abs)

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

    res = make_socket(opts)

    # Build static URLs (we mount DATA_ROOT at /static)
    def to_static_url(p: str) -> str:
        # Return path relative to DATA_ROOT
        rel = os.path.relpath(p, DATA_ROOT).replace("\\", "/")
        return f"/static/{rel}"

    return {
        "socket_inner_url": to_static_url(res.socket_inner_path),
        "socket_outer_url": to_static_url(res.socket_outer_path),
        "socket_trimmed_url": to_static_url(res.socket_trimmed_path),
        "sections_csv_url": to_static_url(res.sections_csv_path),
        "provenance_url": to_static_url(res.provenance_path),
        "stats": res.stats,
        "input_path": limb_abs,
        "outdir": outdir,
    }


# Serve /static from DATA_ROOT so the frontend can fetch outputs
app.mount("/static", StaticFiles(directory=DATA_ROOT), name="static")


def main():
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("socketlab.src.socketlab.server:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
