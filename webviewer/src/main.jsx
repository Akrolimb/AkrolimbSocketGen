import React from 'react'
import { createRoot } from 'react-dom/client'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls, Grid, Environment, GizmoHelper, GizmoViewport, Html } from '@react-three/drei'
import { GLTFLoader, STLLoader } from 'three-stdlib'
import * as THREE from 'three'
function MarkingController({ enabled, limbObject, onPlace }) {
  const { gl, camera } = useThree()
  const raycasterRef = React.useRef(new THREE.Raycaster())
  React.useEffect(() => {
    function handleDown(e) {
      if (!enabled || !limbObject) return
      const rect = gl.domElement.getBoundingClientRect()
      const x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      const y = -((e.clientY - rect.top) / rect.height) * 2 + 1
      const raycaster = raycasterRef.current
      raycaster.setFromCamera({ x, y }, camera)
      const intersects = raycaster.intersectObject(limbObject, true)
      if (intersects && intersects.length > 0) {
        onPlace && onPlace(intersects[0].point)
      }
    }
    const el = gl.domElement
    el.addEventListener('pointerdown', handleDown)
    return () => el.removeEventListener('pointerdown', handleDown)
  }, [enabled, limbObject, gl, camera, onPlace])
  return null
}

function Model({ url, onTransform, onObjectReady }) {
  const [scene, setScene] = React.useState()
  const [error, setError] = React.useState(null)
  const lastObjectUrlRef = React.useRef(null)
  const [norm, setNorm] = React.useState(null) // { scale, center }

  React.useEffect(() => {
    if (!url) return
    // Revoke any previous object URL
    if (lastObjectUrlRef.current && lastObjectUrlRef.current.startsWith('blob:')) {
      URL.revokeObjectURL(lastObjectUrlRef.current)
      lastObjectUrlRef.current = null
    }
    const loader = new GLTFLoader()
  loader.load(
      url,
      (gltf) => {
        const s = gltf.scene
        // Auto-center and scale to a reasonable size
        const box = new THREE.Box3().setFromObject(s)
        const size = new THREE.Vector3();
        box.getSize(size)
        const maxDim = Math.max(size.x, size.y, size.z)
        const scale = 1.0 / (maxDim || 1)
        const center = new THREE.Vector3()
        box.getCenter(center)
        // Translate first, then scale (so socket can reuse same transform order)
        s.position.sub(center)
        s.scale.setScalar(scale)
  setScene(s)
        const t = { scale, center: center.clone() }
        setNorm(t)
        onTransform && onTransform(t)
  onObjectReady && onObjectReady(s)
      },
      undefined,
      (e) => setError(e.message || 'Failed to load model')
    )
    lastObjectUrlRef.current = url
  }, [url])

  if (error) return <Html center style={{color:'#fff'}}>Error: {error}</Html>
  if (!scene) return null
  return <primitive object={scene} />
}

function SocketModel({ url, transform, zUp=true }) {
  const [mesh, setMesh] = React.useState()
  const [error, setError] = React.useState(null)
  React.useEffect(() => {
    if (!url) return
    const loader = new STLLoader()
    loader.load(
      url,
      (geom) => {
        geom.computeVertexNormals()
        const m = new THREE.Mesh(
          geom,
          new THREE.MeshStandardMaterial({ color: '#8B5CF6', roughness: 0.5, metalness: 0.0, transparent: true, opacity: 0.6 })
        )
  // First, align coordinate systems if STL is Z-up; viewer (glTF) is Y-up.
  // Rotate +90° around X so that Z->Y and Y->-Z.
  if (zUp) m.rotation.x = Math.PI / 2
  const hasServerScale = transform && (transform.serverScale || transform.serverScale === 0)
  const hasUnit = transform && transform.unitScale && transform.unitCenter
  const hasCentersMm = transform && transform.limbCenterMm && Array.isArray(transform.limbCenterMm)
        if (hasServerScale || hasUnit) {
          const serverScale = hasServerScale ? (transform.serverScale || 1.0) : 1.0
          const invServer = serverScale ? (1.0 / serverScale) : 1.0
          const unitCenter = hasUnit ? transform.unitCenter : new THREE.Vector3(0,0,0)
          const unitScale = hasUnit ? transform.unitScale : 1.0
          const hasDelta = transform && Array.isArray(transform.deltaMm)
          // Convert mm back to native GLB units
          if (serverScale !== 1.0) m.scale.multiplyScalar(invServer)
          // If we have delta_mm or limb_center_mm from API, rotate them to viewer axes and apply
          const rotX90 = (v) => new THREE.Vector3(v.x, v.z, -v.y)
          if (transform?.deltaMm && Array.isArray(transform.deltaMm)) {
            const d = transform.deltaMm
            const dn = new THREE.Vector3(d[0], d[1], d[2]).multiplyScalar(invServer)
            const dnR = zUp ? rotX90(dn) : dn
            m.position.sub(dnR)
          } else if (hasCentersMm) {
            const c = transform.limbCenterMm
            const cn = new THREE.Vector3(c[0], c[1], c[2]).multiplyScalar(invServer)
            const cnR = zUp ? rotX90(cn) : cn
            m.position.sub(cnR)
          }
          // Align to viewer limb center
          m.position.sub(unitCenter)
          // Scale to unit like limb
          m.scale.multiplyScalar(unitScale)
          // Residual snap: after all transforms, snap STL center to origin (limb center) to remove tiny offsets
          const postBox = new THREE.Box3().setFromObject(m)
          const postCenter = new THREE.Vector3(); postBox.getCenter(postCenter)
          // Only correct if small (avoid masking gross misalignments)
          if (postCenter.length() < 0.5) {
            m.position.sub(postCenter)
          }
          // Optional user nudge in mm
          if (transform?.extraOffsetMm) {
            const off = transform.extraOffsetMm
            const mm = new THREE.Vector3(off.x || 0, off.y || 0, off.z || 0)
            const rotX90 = (v) => new THREE.Vector3(v.x, v.z, -v.y)
            const native = (zUp ? rotX90(mm) : mm).multiplyScalar(invServer)
            const normalized = native.multiplyScalar(unitScale)
            m.position.add(normalized)
          }
        } else {
          // Fallback: normalize by its own bbox
          const box = new THREE.Box3().setFromObject(m)
          const size = new THREE.Vector3(); box.getSize(size)
          const maxDim = Math.max(size.x, size.y, size.z)
          const scale = 1.0 / (maxDim || 1)
          m.scale.setScalar(scale)
          const center = new THREE.Vector3(); box.getCenter(center)
          m.position.sub(center)
        }
        setMesh(m)
      },
      undefined,
      (e) => setError(e.message || 'Failed to load socket')
    )
  }, [url, transform])
  if (error) return <Html center style={{color:'#fff'}}>Socket error: {error}</Html>
  if (!mesh) return null
  return <primitive object={mesh} />
}

function Viewer() {
  // Default to file served from public/ folder
  const [path, setPath] = React.useState('/05_09_2025.glb')
  const fileInputRef = React.useRef(null)
  const [apiHost, setApiHost] = React.useState('http://localhost:8000')
  const [apiResult, setApiResult] = React.useState(null)
  const [busy, setBusy] = React.useState(false)
  const [socketUrl, setSocketUrl] = React.useState(null)
  const [showLimb, setShowLimb] = React.useState(true)
  const [showSocket, setShowSocket] = React.useState(true)
  const [limbTransform, setLimbTransform] = React.useState(null)
  const [socketTransform, setSocketTransform] = React.useState(null)
  const [socketZUp, setSocketZUp] = React.useState(true)
  const [nudge, setNudge] = React.useState({ x: 0, y: 0, z: 0 })
  const [limbObject, setLimbObject] = React.useState(null)
  const [showDebug, setShowDebug] = React.useState(false)

  // Marking state
  const [markMode, setMarkMode] = React.useState(false)
  const [markType, setMarkType] = React.useState('pad') // 'pad' | 'relief' | 'trim'
  const [markRadius, setMarkRadius] = React.useState(20)
  const [markAmount, setMarkAmount] = React.useState(2)
  const [marks, setMarks] = React.useState([]) // items: { type, vpos: Vector3, center_mm:[x,y,z], radius_mm, amount_mm }
  const [trimZmm, setTrimZmm] = React.useState('')
  const [overlayUrl, setOverlayUrl] = React.useState(null)
  const [annotationsUrl, setAnnotationsUrl] = React.useState(null)

  const onPickFile = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const url = URL.createObjectURL(file)
    setPath(url)
  }

  const callMakeSocket = async (includeMarks=false) => {
    try {
      setBusy(true)
      setApiResult(null)
      setSocketUrl(null)
      const fd = new FormData()
      // If path is a blob URL, fetch the blob and append; else send limb_path
      if (path.startsWith('blob:')) {
        const blob = await fetch(path).then(r => r.blob())
        fd.append('file', new File([blob], 'model.glb', { type: 'model/gltf-binary' }))
      } else {
        // Remove origin if full URL
        let p = path
        try {
          const u = new URL(path)
          p = u.pathname
        } catch {}
        // for public served asset, we can map to relative limb_path under repo if needed
        // default: try testModel path if it matches
        fd.append('limb_path', p.startsWith('/') ? p.slice(1) : p)
      }
      fd.append('base_clearance_mm', '2.5')
      fd.append('wall_mm', '4.0')
      if (trimZmm !== '') fd.append('trim_z_mm', String(parseFloat(trimZmm)))
      if (includeMarks && marks.length > 0) {
        // Ensure we can convert viewer coords to mm: need limbTransform and last scale_applied if available
        const unitScale = limbTransform?.scale ?? 1.0
        const unitCenter = limbTransform?.center ?? new THREE.Vector3(0,0,0)
        const serverScale = apiResult?.scale_applied ?? 1.0
        const toMm = (v) => {
          // viewer -> native -> mm
          const native = new THREE.Vector3().copy(v).multiplyScalar(1.0 / unitScale).add(unitCenter)
          return native.multiplyScalar(serverScale)
        }
        const payload = marks.map(m => ({
          type: m.type,
          center_mm: (()=>{ const mm = toMm(m.vpos); return [mm.x, mm.y, mm.z] })(),
          radius_mm: m.radius_mm,
          amount_mm: m.amount_mm
        }))
        fd.append('marks_json', JSON.stringify(payload))
        fd.append('marks_units', 'mm')
      }
      const res = await fetch(`${apiHost}/api/make-socket`, { method: 'POST', body: fd })
      const json = await res.json()
      setApiResult(json)
      if (json.socket_trimmed_url) {
        const u = json.socket_trimmed_url.startsWith('http') ? json.socket_trimmed_url : `${apiHost}${json.socket_trimmed_url}`
        setSocketUrl(u)
      }
      // Prepare a transform to align the STL to the limb view: first undo any unit scaling applied server-side
      // then apply the same viewer normalization (translate center, then scale to unit box)
      if (json.scale_applied || limbTransform) {
        const unitScale = limbTransform?.scale ?? 1.0
        const unitCenter = limbTransform?.center ?? new THREE.Vector3(0,0,0)
        const serverScale = json.scale_applied || 1.0
        const limbCenterMm = json.limb_center_mm || null
        const deltaMm = json.delta_mm || null
        setSocketTransform({ serverScale, unitScale, unitCenter, limbCenterMm, deltaMm })
      }
    } catch (e) {
      setApiResult({ error: e.message || 'API call failed' })
    } finally {
      setBusy(false)
    }
  }

  // Mark placement callback (consumed by MarkingController inside Canvas)
  const onPlaceMark = React.useCallback((p) => {
    const m = {
      type: markType,
      vpos: p.clone(),
      radius_mm: parseFloat(markRadius) || 10,
      amount_mm: parseFloat(markAmount) || 2,
    }
    setMarks(prev => [...prev, m])
  }, [markType, markRadius, markAmount])

  // Helper to compute viewer sphere radius for display
  const viewerRadius = React.useCallback((radius_mm) => {
    const unitScale = limbTransform?.scale ?? 1.0
    const serverScale = apiResult?.scale_applied ?? 1.0
    return (radius_mm / (serverScale || 1.0)) * unitScale
  }, [limbTransform, apiResult])

  const clearMarks = () => setMarks([])
  const popMark = () => setMarks(prev => prev.slice(0, -1))

  const detectMarkings = async () => {
    try {
      if (!path) return
      const fd = new FormData()
      if (path.startsWith('blob:')) {
        const blob = await fetch(path).then(r => r.blob())
        fd.append('glb_file', new File([blob], 'model.glb', { type: 'model/gltf-binary' }))
      } else {
        // Fetch the public asset and reupload (browser cannot send server-side path for this endpoint)
        const blob = await fetch(path).then(r => r.blob())
        fd.append('glb_file', new File([blob], 'model.glb', { type: 'model/gltf-binary' }))
      }
      const res = await fetch(`${apiHost}/api/markings/detect`, { method: 'POST', body: fd })
      const json = await res.json()
      setApiResult(prev => ({ ...(prev||{}), markings: json }))
      if (json.overlay_glb_url) setOverlayUrl(json.overlay_glb_url.startsWith('http') ? json.overlay_glb_url : `${apiHost}${json.overlay_glb_url}`)
      if (json.annotations_url) setAnnotationsUrl(json.annotations_url.startsWith('http') ? json.annotations_url : `${apiHost}${json.annotations_url}`)
    } catch (e) {
      setApiResult(prev => ({ ...(prev||{}), markings_error: e.message || 'Detect failed' }))
    }
  }

  return (
    <div style={{width:'100vw', height:'100vh'}}>
  <Canvas camera={{ position: [1.5, 1.2, 1.5], fov: 50 }} dpr={[1, 2]}>
        <color attach="background" args={[0,0,0]} />
        <ambientLight intensity={0.6} />
        <directionalLight position={[3,3,3]} intensity={0.8} />
        <Environment preset="city" />
        <Grid args={[10,10]} cellSize={0.1} cellThickness={0.6} sectionThickness={1.0} infiniteGrid />
        <GizmoHelper alignment="bottom-right" margin={[80, 80]}>
          <GizmoViewport axisColors={["#ff3653", "#8adb00", "#2c8fff"]} labelColor="white" />
        </GizmoHelper>
        <React.Suspense fallback={<Html center style={{color:'#fff'}}>Loading GLB…</Html>}>
          {showLimb && <Model url={path} onTransform={setLimbTransform} onObjectReady={setLimbObject} />}
          {showSocket && socketUrl && <SocketModel url={socketUrl} transform={{ ...(socketTransform||{}), extraOffsetMm: nudge }} zUp={socketZUp} />}
          {/* Mark visualizers */}
          {marks.map((m, idx) => (
            <mesh key={idx} position={m.vpos}>
              <sphereGeometry args={[viewerRadius(m.radius_mm), 16, 16]} />
              <meshStandardMaterial color={m.type==='pad'?'#22c55e': m.type==='relief'?'#ef4444':'#f59e0b'} transparent opacity={0.25} />
            </mesh>
          ))}
          <MarkingController enabled={markMode} limbObject={limbObject} onPlace={onPlaceMark} />
        </React.Suspense>
        <OrbitControls makeDefault enableDamping dampingFactor={0.1} />
      </Canvas>
      <div style={{position:'absolute', top: 12, left: 12, display:'flex', gap:8, alignItems:'center'}}>
        <input style={{padding:'8px 12px', borderRadius:8, border:'1px solid #444', width:380, background:'#111', color:'#fff'}} 
               value={path} onChange={(e)=>setPath(e.target.value)} />
  <button style={{padding:'8px 12px', borderRadius:8, border:'1px solid #8B5CF6', background:'transparent', color:'#fff'}}
    onClick={()=>setPath(path)}>Load</button>
  <input ref={fileInputRef} type="file" accept=".glb,.gltf" onChange={onPickFile}
         style={{padding:'8px 12px', borderRadius:8, border:'1px solid #444', background:'#111', color:'#fff'}} />
        <input style={{padding:'8px 12px', borderRadius:8, border:'1px solid #444', width:220, background:'#111', color:'#fff'}}
               value={apiHost} onChange={(e)=>setApiHost(e.target.value)} />
  <button disabled={busy} style={{padding:'8px 12px', borderRadius:8, border:'1px solid #8B5CF6', background: busy?'#333':'transparent', color:'#fff'}}
    onClick={() => callMakeSocket(false)}>{busy ? 'Generating…' : 'Generate Socket'}</button>
        <label style={{color:'#fff', display:'flex', alignItems:'center', gap:6}}>
          <input type="checkbox" checked={showLimb} onChange={(e)=>setShowLimb(e.target.checked)} /> Limb
        </label>
        <label style={{color:'#fff', display:'flex', alignItems:'center', gap:6}}>
          <input type="checkbox" checked={showSocket} onChange={(e)=>setShowSocket(e.target.checked)} /> Socket
        </label>
        <label style={{color:'#fff', display:'flex', alignItems:'center', gap:6}}>
          <input type="checkbox" checked={socketZUp} onChange={(e)=>setSocketZUp(e.target.checked)} /> STL is Z-up
        </label>
  <button style={{padding:'8px 12px', borderRadius:8, border:'1px solid #8B5CF6', background:'transparent', color:'#fff'}} onClick={detectMarkings}>Detect Markings</button>
  {socketUrl && (
          <a href={socketUrl} download style={{color:'#8B5CF6', textDecoration:'none', border:'1px solid #8B5CF6', borderRadius:8, padding:'6px 10px'}}>
            Download STL
          </a>
        )}
        <label style={{color:'#fff', display:'flex', alignItems:'center', gap:6}}>
          <input type="checkbox" checked={showDebug} onChange={(e)=>setShowDebug(e.target.checked)} /> Debug
        </label>
  <span style={{color:'#aaa', marginLeft:12}}>Nudge (mm):</span>
  <input type="number" step="0.1" value={nudge.x} onChange={(e)=>setNudge({...nudge, x: parseFloat(e.target.value||'0')})} style={{width:70, padding:'6px 8px', borderRadius:6, border:'1px solid #444', background:'#111', color:'#fff'}} />
  <input type="number" step="0.1" value={nudge.y} onChange={(e)=>setNudge({...nudge, y: parseFloat(e.target.value||'0')})} style={{width:70, padding:'6px 8px', borderRadius:6, border:'1px solid #444', background:'#111', color:'#fff'}} />
  <input type="number" step="0.1" value={nudge.z} onChange={(e)=>setNudge({...nudge, z: parseFloat(e.target.value||'0')})} style={{width:70, padding:'6px 8px', borderRadius:6, border:'1px solid #444', background:'#111', color:'#fff'}} />
      </div>
      {/* Marking + trim controls */}
      <div style={{position:'absolute', top: 60, left: 12, display:'flex', gap:8, alignItems:'center', background:'rgba(17,17,17,0.9)', padding:8, border:'1px solid #333', borderRadius:8}}>
        <label style={{color:'#fff', display:'flex', alignItems:'center', gap:6}}>
          <input type="checkbox" checked={markMode} onChange={(e)=>setMarkMode(e.target.checked)} /> Mark mode
        </label>
        <select value={markType} onChange={(e)=>setMarkType(e.target.value)} style={{padding:'6px 8px', borderRadius:6, border:'1px solid #444', background:'#111', color:'#fff'}}>
          <option value="pad">Loosen (pad)</option>
          <option value="relief">Tighten (press)</option>
          <option value="trim">Trim (cutout)</option>
        </select>
        <span style={{color:'#aaa'}}>Radius (mm)</span>
        <input type="number" step="1" value={markRadius} onChange={(e)=>setMarkRadius(e.target.value)} style={{width:90, padding:'6px 8px', borderRadius:6, border:'1px solid #444', background:'#111', color:'#fff'}} />
        <span style={{color:'#aaa'}}>Amount (mm)</span>
        <input type="number" step="0.5" value={markAmount} onChange={(e)=>setMarkAmount(e.target.value)} style={{width:90, padding:'6px 8px', borderRadius:6, border:'1px solid #444', background:'#111', color:'#fff'}} />
        <button style={{padding:'6px 10px', borderRadius:8, border:'1px solid #666', background:'transparent', color:'#fff'}} onClick={popMark}>Undo</button>
        <button style={{padding:'6px 10px', borderRadius:8, border:'1px solid #666', background:'transparent', color:'#fff'}} onClick={clearMarks}>Clear</button>
        <button disabled={busy || marks.length===0 || !apiResult} style={{padding:'6px 10px', borderRadius:8, border:'1px solid #8B5CF6', background: busy?'#333':'transparent', color:'#fff'}} onClick={()=>callMakeSocket(true)}>Apply Marks</button>
        <span style={{color:'#aaa', marginLeft:12}}>Trim Z (mm)</span>
        <input type="number" step="1" value={trimZmm} onChange={(e)=>setTrimZmm(e.target.value)} style={{width:110, padding:'6px 8px', borderRadius:6, border:'1px solid #444', background:'#111', color:'#fff'}} />
      </div>

  {apiResult && showDebug && (
        <div style={{position:'absolute', bottom: 12, left: 12, right: 12, padding:12, background:'rgba(17,17,17,0.9)', color:'#fff', border:'1px solid #333', borderRadius:8}}>
          <pre style={{margin:0, whiteSpace:'pre-wrap'}}>{JSON.stringify(apiResult, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}

createRoot(document.getElementById('root')).render(<Viewer />)
