import { useEffect, useRef, type ComponentRef } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { CameraControls, useGLTF } from "@react-three/drei"
import * as THREE from "three"
import type { Findings, ViewerCommand } from "@/api/types"

/** RAS mm → three/glTF: x = patient Left (−R), y = Superior, z = Anterior. Right-handed, mm, not recentred. */
function resolveAsset(url: string) {
  return url.startsWith("/") ? url : `/${url}`
}

export function rasToThree([r, a, s]: [number, number, number]) {
  return new THREE.Vector3(-r, s, a)
}

const LUNG_SHADER = {
  vertexShader: /* glsl */ `
    varying vec3 vN; varying vec3 vV;
    void main() {
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
      gl_Position = projectionMatrix * mv;
    }`,
  fragmentShader: /* glsl */ `
    uniform vec3 uColor; uniform float uAlpha;
    varying vec3 vN; varying vec3 vV;
    void main() {
      float f = 1.0 - abs(dot(normalize(vN), normalize(vV)));
      gl_FragColor = vec4(uColor, uAlpha * (0.07 + 0.5 * f * f) * 10.0);
    }`,
}

function Lung({ url }: { url: string }) {
  const gltf = useGLTF(url, false, false)
  const scene = gltf.scene.clone(true)
  useEffect(() => {
    scene.traverse((o) => {
    const m = o as THREE.Mesh
    if (m.isMesh) {
      const mat = new THREE.ShaderMaterial({
        ...LUNG_SHADER,
        uniforms: { uColor: { value: new THREE.Color("#9db8d8") }, uAlpha: { value: 0.5 } },
        transparent: true,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
      m.material = mat
    }
    })
  }, [scene])
  return <primitive object={scene} />
}

function Nodules({ url, selected, onSelect }: { url: string; selected: string | null; onSelect: (id: string) => void }) {
  const gltf = useGLTF(url, false, false)
  const scene = gltf.scene.clone(true)
  useEffect(() => {
    scene.traverse((o) => {
      const m = o as THREE.Mesh
      if (!m.isMesh) return
      const isSel = m.name === selected
      m.material = new THREE.MeshStandardMaterial({
        color: isSel ? "#ffb257" : "#ff8a3d",
        emissive: new THREE.Color(isSel ? "#ffcf8a" : "#e8742c"),
        emissiveIntensity: isSel ? 1.6 : 0.7,
        roughness: 0.4,
        metalness: 0,
      })
      m.userData.nodule_id = m.name
    })
  }, [selected])
  return (
    <primitive
      object={scene}
      onClick={(e: { stopPropagation: () => void; object: THREE.Object3D }) => {
        e.stopPropagation()
        const id = e.object.userData.nodule_id as string | undefined
        if (id) onSelect(id)
      }}
    />
  )
}

function Controls({
  findings, selected, command,
}: {
  findings: Findings
  selected: string | null
  command: { command: ViewerCommand["command"]; nodule_id?: string } | null
}) {
  const ccObj = useRef<ComponentRef<typeof CameraControls> | null>(null)
  const shared = useRef({ auto: true, focused: false, center: new THREE.Vector3(), radius: 140, lastInteract: 0 })

  // Compute the lung bounding sphere from the loaded meshes' world positions.
  const scene = useThree((s) => s.scene)
  useEffect(() => {
    const box = new THREE.Box3()
    scene.traverse((o) => {
      const m = o as THREE.Mesh
      if (m.isMesh && (m.parent as THREE.Object3D | null)?.type === "Scene") box.expandByObject(m)
    })
    const sphere = new THREE.Sphere()
    if (!box.isEmpty()) box.getBoundingSphere(sphere)
    shared.current.center.copy(sphere.center)
    shared.current.radius = Math.min(400, Math.max(100, sphere.radius || 140))
  }, [scene, findings.study_uid])

  const home = (cc2: ComponentRef<typeof CameraControls>) => {
    const fov = (35 * Math.PI) / 180
    const d = (shared.current.radius / Math.sin(fov / 2)) * 0.82
    cc2.smoothTime = 0.28
    void cc2.setLookAt(shared.current.center.x, shared.current.center.y, shared.current.center.z + d, shared.current.center.x, shared.current.center.y, shared.current.center.z, true)
  }

  const flyTo = (p: THREE.Vector3) => {
    const cc2 = ccObj.current
    if (!cc2) return
    shared.current.focused = true
    shared.current.auto = false
    const dir = new THREE.Vector3(p.x - shared.current.center.x, 0, p.z - shared.current.center.z)
    if (dir.lengthSq() < 1) dir.set(0, 0, 1)
    dir.normalize().add(new THREE.Vector3(0, 0, 0.35)).setY(0.3).normalize()
    const dist = THREE.MathUtils.clamp(shared.current.radius * 1.6, 160, 400)
    const pos = p.clone().addScaledVector(dir, dist)
    cc2.smoothTime = 0.28
    void cc2.setLookAt(pos.x, pos.y, pos.z, p.x, p.y, p.z, true)
  }

  useEffect(() => {
    const cc2 = ccObj.current
    if (!cc2) return
    if (command?.command === "show_nodule") {
      const id = command.nodule_id ?? selected
      const n = findings.nodules.find((x) => x.nodule_id === id)
      if (n?.center_mm) flyTo(rasToThree(n.center_mm))
    } else if (command?.command === "reset_view") {
      home(cc2)
      shared.current.focused = false
      shared.current.auto = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command])

  useEffect(() => {
    const cc2 = ccObj.current
    if (cc2) home(cc2)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [findings.study_uid])

  useFrame((_, dt) => {
    const cc2 = ccObj.current
    const sh = shared.current
    if (!cc2) return
    const since = performance.now() - sh.lastInteract
    if (!sh.auto || sh.focused || since < 6000) return
    void cc2.rotate(0.18 * dt, 0, false)
  })

  return (
    <CameraControls
      ref={ccObj}
      makeDefault
      minDistance={40}
      maxDistance={900}
      onStart={() => {
        shared.current.lastInteract = performance.now()
      }}
      onEnd={() => {
        shared.current.lastInteract = performance.now()
      }}
    />
  )
}

export default function Lung3D({
  findings, selected, onSelect, command,
}: {
  uid: string
  findings: Findings | undefined
  selected: string | null
  onSelect: (id: string) => void
  command: { command: ViewerCommand["command"]; nodule_id?: string } | null
}) {
  const lung = findings?.assets.lung_mesh ? resolveAsset(findings.assets.lung_mesh) : null
  const nod = findings?.assets.nodule_mesh ? resolveAsset(findings.assets.nodule_mesh) : null
  if (!findings || !lung || !nod)
    return <div className="grid h-full place-items-center text-[11px] text-white/50">No 3D assets for this study</div>
  return (
    <Canvas camera={{ fov: 35, near: 1, far: 5000, position: [0, 0, 600] }} gl={{ antialias: true }} dpr={[1, 1.5]}>
      <color attach="background" args={["#0b0d10"]} />
      <ambientLight intensity={1.2} />
      <directionalLight position={[200, 400, 600]} intensity={1.6} />
      <directionalLight position={[-300, -200, -400]} intensity={0.5} />
      <Lung url={lung} />
      <Nodules url={nod} selected={selected} onSelect={onSelect} />
      <Controls findings={findings} selected={selected} command={command} />
    </Canvas>
  )
}
