import React from 'react'
import { createRoot } from 'react-dom/client'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid, Environment, GizmoHelper, GizmoViewport, Html, Loader } from '@react-three/drei'
import { GLTFLoader } from 'three-stdlib'
import * as THREE from 'three'

function Model({ url }) {
  const [scene, setScene] = React.useState()
  const [error, setError] = React.useState(null)
  const lastObjectUrlRef = React.useRef(null)

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
        s.scale.setScalar(scale)
        const center = new THREE.Vector3()
        box.getCenter(center)
        s.position.sub(center)
        setScene(s)
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

function Viewer() {
  // Default to file served from public/ folder
  const [path, setPath] = React.useState('/26_02_2025.glb')
  const fileInputRef = React.useRef(null)
  const [apiHost, setApiHost] = React.useState('http://localhost:8000')
  const [apiResult, setApiResult] = React.useState(null)
  const [busy, setBusy] = React.useState(false)

  const onPickFile = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const url = URL.createObjectURL(file)
    setPath(url)
  }

  const callMakeSocket = async () => {
    try {
      setBusy(true)
      setApiResult(null)
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
      const res = await fetch(`${apiHost}/api/make-socket`, { method: 'POST', body: fd })
      const json = await res.json()
      setApiResult(json)
    } catch (e) {
      setApiResult({ error: e.message || 'API call failed' })
    } finally {
      setBusy(false)
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
          <Model url={path} />
        </React.Suspense>
        <OrbitControls makeDefault enableDamping dampingFactor={0.1} />
      </Canvas>
      <div style={{position:'absolute', top: 12, left: 12, display:'flex', gap:8}}>
        <input style={{padding:'8px 12px', borderRadius:8, border:'1px solid #444', width:380, background:'#111', color:'#fff'}} 
               value={path} onChange={(e)=>setPath(e.target.value)} />
  <button style={{padding:'8px 12px', borderRadius:8, border:'1px solid #8B5CF6', background:'transparent', color:'#fff'}}
    onClick={()=>setPath(path)}>Load</button>
  <input ref={fileInputRef} type="file" accept=".glb,.gltf" onChange={onPickFile}
         style={{padding:'8px 12px', borderRadius:8, border:'1px solid #444', background:'#111', color:'#fff'}} />
        <input style={{padding:'8px 12px', borderRadius:8, border:'1px solid #444', width:220, background:'#111', color:'#fff'}}
               value={apiHost} onChange={(e)=>setApiHost(e.target.value)} />
        <button disabled={busy} style={{padding:'8px 12px', borderRadius:8, border:'1px solid #8B5CF6', background: busy?'#333':'transparent', color:'#fff'}}
                onClick={callMakeSocket}>{busy ? 'Generating…' : 'Generate Socket'}</button>
      </div>
      {apiResult && (
        <div style={{position:'absolute', bottom: 12, left: 12, right: 12, padding:12, background:'rgba(17,17,17,0.9)', color:'#fff', border:'1px solid #333', borderRadius:8}}>
          <pre style={{margin:0, whiteSpace:'pre-wrap'}}>{JSON.stringify(apiResult, null, 2)}</pre>
        </div>
      )}
      <Loader containerStyles={{ background: 'rgba(0,0,0,0.6)' }} barStyles={{ background: '#8B5CF6' }} />
    </div>
  )
}

createRoot(document.getElementById('root')).render(<Viewer />)
