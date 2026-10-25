import { useCallback, useEffect, useMemo, useRef, useState, type ComponentRef } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { CameraControls, useGLTF } from "@react-three/drei"
import * as THREE from "three"
import type { Findings, ViewerCommand } from "@/api/types"
import { Toggle } from "@/components/ui/toggle"
import { cn } from "@/lib/utils"
import { Crosshair, Rotate3d } from "lucide-react"
import { viewerBus } from "@/api/viewer-bus"

/** RAS mm → three/glTF: x = patient Left (−R), y = Superior, z = Anterior. Right-handed, mm, not recentred. */
/** Worker assets are paths; a relative URL resolves against the current page's origin and hash route. */
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

/** 08 §3D viewer layers: glb node name → colour and alpha multiplier on the lung fresnel shader. */
type Layer = "lungs" | "airways" | "vessels" | "skeleton"
type ToggleLayer = "vessels" | "skeleton"
const LAYERS: Layer[] = ["lungs", "airways", "vessels", "skeleton"]
const TOGGLES: ToggleLayer[] = ["vessels", "skeleton"]
const LAYER_STYLE: Record<Layer, { color: string; alpha: number }> = {
  lungs: { color: "#9db8d8", alpha: 0.4 }, // lighter than the layers so vessels read through it
  airways: { color: "#d8e6f2", alpha: 1.7 },
  vessels: { color: "#e3a3ae", alpha: 2.2 },
  skeleton: { color: "#efe4cf", alpha: 0.9 },
}
const LUNG_ALPHA = 0.5
const TOGGLE_CLASS =
  "h-6 rounded-md bg-white/5 px-1.5 text-[11px] font-normal text-white/50 hover:bg-white/10 hover:text-white data-[state=on]:bg-white/15 data-[state=on]:text-white"
/**
 * Fixed draw order per layer. Per-object depth sorting flips between these nested meshes as the
 * camera orbits (their centres are mm apart), so whole layers popped over/under the lungs. Bone is
 * drawn first and writes depth, so ribs in front hide the lung and the lung covers the spine behind.
 * Both lungs share an order and still sort against each other.
 */
const LAYER_ORDER: Record<Layer, number> = { skeleton: 0, vessels: 1, lungs: 2, airways: 3 }
/** Skeleton alpha multiplier while a nodule is focused, so the ribs don't sit between camera and nodule. */
const SKELETON_FOCUSED = 0.25

function layerOf(o: THREE.Object3D): Layer {
  for (let p: THREE.Object3D | null = o; p; p = p.parent) {
    if (p.name === "airways" || p.name === "vessels" || p.name === "skeleton") return p.name
  }
  return "lungs"
}

function Lung({
  url, onReady, onLayers, hidden, focusRef,
}: {
  url: string
  onReady: () => void
  onLayers: (l: Layer[]) => void
  hidden: Record<ToggleLayer, boolean>
  focusRef: { current: boolean }
}) {
  const gltf = useGLTF(url, false, false)
  const scene = useMemo(() => gltf.scene.clone(true), [gltf])
  const invalidate = useThree((s) => s.invalidate)
  const skeletonMats = useRef<THREE.ShaderMaterial[]>([])
  useEffect(() => {
    const present = new Set<Layer>()
    skeletonMats.current = []
    scene.traverse((o) => {
      const m = o as THREE.Mesh
      if (!m.isMesh) return
      const layer = layerOf(m)
      present.add(layer)
      const mat = new THREE.ShaderMaterial({
        ...LUNG_SHADER,
        uniforms: { uColor: { value: new THREE.Color(LAYER_STYLE[layer].color) }, uAlpha: { value: LUNG_ALPHA * LAYER_STYLE[layer].alpha } },
        transparent: true,
        side: THREE.DoubleSide,
        depthWrite: layer === "skeleton",
      })
      m.material = mat
      m.userData.layer = layer
      m.renderOrder = LAYER_ORDER[layer]
      if (layer === "skeleton") skeletonMats.current.push(mat)
    })
    onLayers(LAYERS.filter((l) => present.has(l)))
  }, [scene, onLayers])
  useEffect(() => {
    scene.traverse((o) => {
      if (o.name === "vessels" || o.name === "skeleton") o.visible = !hidden[o.name]
    })
    invalidate()
  }, [scene, hidden, invalidate])
  // Damp (λ 4) the skeleton toward its focused/unfocused alpha; requests frames only until it settles.
  useFrame((_, delta) => {
    const mats = skeletonMats.current
    if (!mats.length) return
    // Focused: faint ribs must not punch depth holes in the lung around the nodule.
    const depth = !focusRef.current
    if (mats[0].depthWrite !== depth) {
      for (const m of mats) m.depthWrite = depth
      invalidate()
    }
    const target = LUNG_ALPHA * (focusRef.current ? SKELETON_FOCUSED : LAYER_STYLE.skeleton.alpha)
    const cur = mats[0].uniforms.uAlpha.value as number
    if (cur === target) return
    const next = Math.abs(cur - target) < 1e-3 ? target : THREE.MathUtils.damp(cur, target, 4, Math.min(delta, 0.1))
    for (const m of mats) m.uniforms.uAlpha.value = next
    invalidate()
  })
  useEffect(() => onReady(), [scene, onReady]) // attached after commit: the meshes are in the scene graph
  return <primitive object={scene} />
}

function Nodules({
  url, selected, onSelect, onReady, onNodes, nodules,
}: {
  url: string
  selected: string | null
  onSelect: (id: string) => void
  onReady: () => void
  onNodes: (m: Map<string, THREE.Vector3>) => void
  nodules: { nodule_id: string; center_mm: [number, number, number] | null }[]
}) {
  const gltf = useGLTF(url, false, false)
  const scene = useMemo(() => gltf.scene.clone(true), [gltf])
  useEffect(() => {
    scene.updateMatrixWorld(true)
    const centers = new Map<string, THREE.Vector3>()
    for (const n of nodules) {
      const node = scene.getObjectByName(n.nodule_id)
      if (!node) continue
      const c = new THREE.Box3().setFromObject(node).getCenter(new THREE.Vector3())
      centers.set(n.nodule_id, c)
      if (n.center_mm) {
        const d = c.distanceTo(rasToThree(n.center_mm))
        if (d > 2) console.warn(`[sparkmd] nodule ${n.nodule_id} glb node is ${d.toFixed(1)} mm from center_mm`)
      }
    }
    onNodes(centers)
}, [scene, nodules, onNodes])
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
  }, [scene, selected])
  useEffect(() => onReady(), [scene, onReady])
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
  findings, selected, command, ready, nodesRef, paused, focusRef, onHomed, orbit,
}: {
  findings: Findings
  selected: string | null
  command: { command: ViewerCommand["command"]; nodule_id?: string } | null
  ready: number
  nodesRef: { current: Map<string, THREE.Vector3> }
  paused: boolean
  focusRef: { current: boolean }
  onHomed: (uid: string) => void
  orbit: boolean
}) {
  const ccObj = useRef<ComponentRef<typeof CameraControls> | null>(null)
  const shared = useRef({ center: new THREE.Vector3(), radius: 140 })

  // Lung bounding sphere from the lung + nodule meshes (glbs nest meshes under Group nodes,
  // and real anatomy is NOT origin-centred — a wrong center/home target frames empty space).
  // Airways/vessels/skeleton layers are excluded: the trachea would pull the orbit centre up,
  // and toggling a layer must not move home.
  const scene = useThree((s) => s.scene)
  const invalidate = useThree((s) => s.invalidate)
  const setFrameloop = useThree((s) => s.setFrameloop)
  const get = useThree((s) => s.get)
  // `active` = a tween or drag; `auto` = the idle auto-rotate. Either keeps the loop running.
  const motion = useRef({ active: false, dragging: false, paused, auto: false, orbit, lastInteract: 0 })
  motion.current.paused = paused
  motion.current.orbit = orbit
  const syncLoop = () => {
    const m = motion.current
    const next = m.paused ? "never" : m.active || m.auto ? "always" : "demand"
    if (get().frameloop !== next) setFrameloop(next)
    invalidate()
  }
  const startMotion = () => {
    motion.current.active = true
    syncLoop()
  }
  const restMotion = () => {
    if (motion.current.dragging) return
    motion.current.active = false
    syncLoop()
  }

  // 08 auto-rotate: 0.18 rad/s about S, resumes 6 s after the last drag, stays put while a nodule
  // is focused (until reset_view), off with the Orbit toggle or while the viewer is paused.
  const resumeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const canAuto = () => {
    const m = motion.current
    return m.orbit && !m.paused && !m.dragging && !focusRef.current
  }
  const stopAuto = () => {
    clearTimeout(resumeTimer.current)
    if (!motion.current.auto) return
    motion.current.auto = false
    syncLoop()
  }
  const scheduleAuto = () => {
    clearTimeout(resumeTimer.current)
    const wait = Math.max(0, motion.current.lastInteract + 6000 - performance.now())
    resumeTimer.current = setTimeout(() => {
      if (!canAuto() || motion.current.auto) return
      motion.current.auto = true
      syncLoop()
    }, wait)
  }
  useEffect(() => () => clearTimeout(resumeTimer.current), [])
  useEffect(() => {
    if (orbit && !paused) scheduleAuto()
    else stopAuto()
    if (!paused) syncLoop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orbit, paused])
  useFrame((_, delta) => {
    if (!motion.current.auto) return
    if (!canAuto()) return stopAuto()
    ccObj.current?.rotate(0.18 * Math.min(delta, 0.1), 0, false)
  })
  // ANGLE translation can saturate a CPU core at 60 draws/s on this box. Keep controls
  // updating each frame, but cap expensive active WebGL drawing at 30 Hz.
  const lastDraw = useRef(0)
  useFrame(({ gl, scene: world, camera }) => {
    if (motion.current.paused) return
    const now = performance.now()
    if ((motion.current.active || motion.current.auto) && now - lastDraw.current < 1000 / 30 - 1) return
    lastDraw.current = now
    gl.render(world, camera)
  }, 1)
  useEffect(() => {
    const box = new THREE.Box3()
    scene.updateMatrixWorld(true)
    scene.traverse((o) => {
      const m = o as THREE.Mesh
      if (m.isMesh && (m.userData.layer ?? "lungs") === "lungs") box.expandByObject(m)
    })
    if (box.isEmpty()) return
    const sphere = box.getBoundingSphere(new THREE.Sphere())
    shared.current.center.copy(sphere.center)
    shared.current.radius = Math.min(400, Math.max(100, sphere.radius || 140))
  }, [scene, findings.study_uid, ready, invalidate])

  /** Auto-rotate accumulates azimuth: unwind to within π of the target so a tween goes the short way. */
  const nearAzimuth = (cc2: ComponentRef<typeof CameraControls>, target: number) => {
    cc2.normalizeRotations()
    const d = cc2.azimuthAngle - target
    if (d > Math.PI) cc2.rotate(-2 * Math.PI, 0, false)
    else if (d < -Math.PI) cc2.rotate(2 * Math.PI, 0, false)
  }

  /** Anterior home view; `animate` false snaps (first load) so the canvas never shows a pre-home frame. */
  const home = (cc2: ComponentRef<typeof CameraControls>, animate: boolean) => {
    const fov = (35 * Math.PI) / 180
    const d = (shared.current.radius / Math.sin(fov / 2)) * 0.82
    const c = shared.current.center
    cc2.smoothTime = 0.18
    nearAzimuth(cc2, 0)
    if (animate) startMotion()
    void cc2.setLookAt(c.x, c.y, c.z + d, c.x, c.y, c.z, animate).then(() => {
      if (animate) restMotion()
      if (motion.current.orbit) scheduleAuto()
    })
    invalidate()
  }

  const flyTo = (p: THREE.Vector3) => {
    const cc2 = ccObj.current
    if (!cc2) return
    focusRef.current = true
    const dir = new THREE.Vector3(p.x - shared.current.center.x, 0, p.z - shared.current.center.z)
    if (dir.lengthSq() < 1) dir.set(0, 0, 1)
    dir.normalize().add(new THREE.Vector3(0, 0, 0.35)).setY(0.3).normalize()
    const dist = THREE.MathUtils.clamp(shared.current.radius * 1.6, 160, 400)
    const pos = p.clone().addScaledVector(dir, dist)
    cc2.smoothTime = 0.28
    stopAuto()
    nearAzimuth(cc2, Math.atan2(dir.x, dir.z))
    startMotion()
    void cc2.setLookAt(pos.x, pos.y, pos.z, p.x, p.y, p.z, true).then(restMotion)
    invalidate()
  }

  useEffect(() => {
    const cc2 = ccObj.current
    if (!cc2) return
    if (command?.command === "show_nodule") {
      const id = command.nodule_id ?? selected
      const n = findings.nodules.find((x) => x.nodule_id === id)
      if (n?.center_mm && id) flyTo(nodesRef.current.get(id) ?? rasToThree(n.center_mm))
    } else if (command?.command === "reset_view") {
      focusRef.current = false
      motion.current.lastInteract = 0
      stopAuto()
      home(cc2, true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command])

  useEffect(() => {
    const cc2 = ccObj.current
    if (cc2 && !focusRef.current) home(cc2, false)
    onHomed(findings.study_uid)
    invalidate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [findings.study_uid, ready])
  useEffect(() => invalidate(), [selected, invalidate])
  return (
    <CameraControls
      ref={ccObj}
      makeDefault
      enabled={!paused}
      minDistance={40}
      maxDistance={900}
      onStart={() => {
        motion.current.dragging = true
        motion.current.lastInteract = performance.now()
        stopAuto()
        startMotion()
      }}
      onEnd={() => {
        motion.current.dragging = false
        motion.current.lastInteract = performance.now()
        if (motion.current.orbit) scheduleAuto()
        if (ccObj.current?.active) startMotion()
        else restMotion()
      }}
      onTransitionStart={startMotion}
      onWake={startMotion}
      onRest={restMotion}
      onSleep={restMotion}
      onChange={() => invalidate()}
    />
  )
}


export default function Lung3D({
  findings, selected, onSelect, command, paused,
}: {
  uid: string
  findings: Findings | undefined
  selected: string | null
  onSelect: (id: string) => void
  command: { command: ViewerCommand["command"]; nodule_id?: string } | null
  /** Freeze rendering entirely (report sheet open): demand frameloop already idles at 0 frames. */
  paused?: boolean
}) {
  const lung = findings?.assets.lung_mesh ? resolveAsset(findings.assets.lung_mesh) : null
  const nod = findings?.assets.nodule_mesh ? resolveAsset(findings.assets.nodule_mesh) : null
  const [ready, setReady] = useState(0)
  const nodesRef = useRef(new Map<string, THREE.Vector3>())
  const bumpReady = useCallback(() => setReady((r) => r + 1), [])
  const handleNodes = useCallback((m: Map<string, THREE.Vector3>) => {
    nodesRef.current = m
  }, [])
  const focusRef = useRef(false)
  const [layers, setLayers] = useState<Layer[]>([])
  const [hidden, setHidden] = useState<Record<ToggleLayer, boolean>>({ vessels: false, skeleton: false })
  const [orbit, setOrbit] = useState(true)
  // The canvas stays transparent until the camera has snapped home for this study, then fades in.
  const [shown, setShown] = useState<string | null>(null)
  if (!findings || !lung || !nod)
    return <div className="grid h-full place-items-center text-[11px] text-white/50">No 3D assets for this study</div>
  // Demand frameloop: GL-on-EGL translation is CPU-bound on GB10, so a 60 fps loop burns a core.
  // CameraControls renders continuously only during interaction/tweens, then returns to demand.
  const visible = shown === findings.study_uid
  // Focus target: the selected nodule, else the assessment's driver, else the first one placed.
  const focusId =
    [selected, findings.assessment?.driver_nodule_id].find((id) => id && findings.nodules.some((n) => n.nodule_id === id && n.center_mm)) ??
    findings.nodules.find((n) => n.center_mm)?.nodule_id
  return (
    <div className="relative h-full">
      <div className="h-full" style={{ opacity: visible ? 1 : 0, transition: visible ? "opacity 0.4s ease-out" : "none" }}>
        <Canvas camera={{ fov: 35, near: 1, far: 5000, position: [0, 0, 600] }} gl={{ antialias: true }} dpr={1} frameloop={paused ? "never" : "demand"}>
          <color attach="background" args={["#0b0d10"]} />
          <ambientLight intensity={1.2} />
          <directionalLight position={[200, 400, 600]} intensity={1.6} />
          <directionalLight position={[-300, -200, -400]} intensity={0.5} />
          <Lung url={lung} onReady={bumpReady} onLayers={setLayers} hidden={hidden} focusRef={focusRef} />
          <Nodules url={nod} selected={selected} onSelect={onSelect} onReady={bumpReady} onNodes={handleNodes} nodules={findings.nodules} />
          <Controls findings={findings} selected={selected} command={command} ready={ready} nodesRef={nodesRef} paused={!!paused} focusRef={focusRef} onHomed={setShown} orbit={orbit} />
        </Canvas>
      </div>
      <div className="absolute right-2.5 top-2 flex gap-1">
        {focusId && (
          <button
            onClick={() => viewerBus.emit({ command: "show_nodule", study_uid: findings.study_uid, nodule_id: focusId })}
            className="flex h-6 items-center gap-1 rounded-md bg-white/5 px-1.5 text-[11px] text-white/60 hover:bg-white/10 hover:text-white"
            aria-label="Focus nodule"
          >
            <Crosshair className="size-3.5" /> Focus nodule
          </button>
        )}
        <Toggle size="sm" pressed={orbit} onPressedChange={setOrbit} className={TOGGLE_CLASS} aria-label="Auto-orbit">
          <Rotate3d className="size-3.5" /> Orbit
        </Toggle>
        {TOGGLES.filter((l) => layers.includes(l)).map((l) => (
          <Toggle
            key={l}
            size="sm"
            pressed={!hidden[l]}
            onPressedChange={(on) => setHidden((h) => ({ ...h, [l]: !on }))}
            className={cn(TOGGLE_CLASS, "capitalize")}
            aria-label={`Show ${l}`}
          >
            {l}
          </Toggle>
        ))}
      </div>
      {layers.length > 0 && (
        <div className="pointer-events-none absolute left-3 top-2.5 font-mono text-[10px] text-white/40">Mesh layers · {layers.join(" · ")}</div>
      )}
    </div>
  )
}
