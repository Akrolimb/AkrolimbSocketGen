# Akrolimb Web 3D Viewer (MVP)

A minimal React + three.js viewer to load and inspect GLB/GLTF models with OrbitControls, grid and lighting. Styled to match Akrolimb’s dark UI.

## Usage

1) Install Node.js 18+.
2) Install deps:

```bash
cd webviewer
npm install
```

3) Dev server:

```bash
npm run dev
```

4) Open the URL printed by Vite (e.g., http://localhost:5173). In the input box, set the path to your GLB. Examples:
- If you copy your GLB into `webviewer/public/26_02_2025.glb`, set `/26_02_2025.glb`.
- If you want to reference the workspace file at `../testModel/26_02_2025.glb`, set `/data/26_02_2025.glb` and serve that path via a static route (see below).

## Serving testModel files
By default, Vite can’t read outside the project. Two options:
- Copy the GLB into `webviewer/public/` and load it with `/<filename>`.
- Or, run a tiny static server from the workspace root and proxy it.

### Option A: copy file
```bash
# from repo root
copy testModel\26_02_2025.glb webviewer\public\26_02_2025.glb
```
Then use path `/26_02_2025.glb` in the viewer.

### Option B: run a static server from repo root
```bash
# from repo root (PowerShell)
python -m http.server 8081
```
Update the input box in the viewer to `http://localhost:8081/testModel/26_02_2025.glb`.

## Build
```bash
npm run build
npm run preview
```

## Notes
- The viewer auto-centers and scales the model to fit the scene.
- This is a base for adding marking overlays and UI controls next.
