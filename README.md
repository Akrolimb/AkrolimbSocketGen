# Akrolimb SocketLab

Dockerized CLI to generate a prosthetic socket from a limb STL/OBJ.

## Build the Docker image

```powershell
# From repo root
docker build -t akrolimb/socketlab:0.1.0 .
```

## Run against your limb STL

```powershell
# Replace paths as needed; we mount the repo to /data inside the container
$in = "C:\GitHub\AkrolimbSocketGen\testModel\TestLimb.stl"
$out = "C:\GitHub\AkrolimbSocketGen\out"

# Create output folder if needed
mkdir $out -Force | Out-Null

# Run CLI
docker run --rm -v "C:\GitHub\AkrolimbSocketGen:/data" akrolimb/socketlab:0.1.0 \
  make-socket --limb "/data/testModel/TestLimb.stl" --outdir "/data/out" \
  --base-clearance-mm 2.5 --wall-mm 4.0 --trim-z-mm 120
```

Outputs will be in `out/`: `socket_inner.stl`, `socket_outer.stl`, `socket_trimmed.stl`, `sections.csv`, `provenance.json`.

## Notes
- All units in mm; ensure your input mesh is in mm. The CLI records bbox and flags suspicious scales in provenance.
- Offsets and trim use a robust volumetric approach for M0.
- If you see performance issues, tweak `--voxel-mm` (e.g., 0.8–1.0 for faster runtimes, 0.5 for higher fidelity).

## Local API (FastAPI)

You can run a small API server to generate sockets and serve outputs under `/static` for the web viewer.

```powershell
pip install -r socketlab/requirements.txt
python -m socketlab.src.socketlab.server
```

It will listen on http://localhost:8000

Endpoint:
- POST `/api/make-socket`
  - form-data: `file` (upload) or `limb_path` (path relative to repo),
    and optional `base_clearance_mm`, `wall_mm`, `trim_z_mm`, `voxel_mm`, `assume_units`, `scale_factor`.
  - returns JSON with `socket_trimmed_url` etc., e.g. `/static/out/.../socket_trimmed.stl`.

Static files:
- `/static/...` maps to the repo root by default. Adjust `DATA_ROOT` env if needed.