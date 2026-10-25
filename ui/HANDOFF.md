# UI handoff (agent U, Oct 25 ~14:00)

## Done (all committed, `git log -- ui`)
- 3D framing fixed on real anatomy (042e031): the bounding sphere skipped glb meshes nested under
  Groups, so home targeted (0,0,0)/r140 while the real lung sits at center (−17,−207,165) r206 — viewer
  was blank. Now: sphere over all meshes, re-home after load, flyTo prefers glb node bbox centre,
  warns if a node is >2 mm from center_mm (real T0: both nodes exact, RUL upper/screen-left =
  patient right, LLL lower/screen-right = patient left in anterior view). 61 fps, 0 non-loopback.
  Screenshot: /tmp/shots-realworker-fixed/02-study-3d.png. Probe: `node tools/realworker.mjs`
  (read-only vs the real worker — NEVER clicks Confirm/Approve; needs `--ozone-platform=headless`).
- Net monitor verified against the real worker (W shipped /api/netstats + SSE net_stats): System page
  shows live 96.65 MB sent / 38.28 MB recv, per-iface rows, sparkline over SSE frames, "Link up".
- Voice (09) UI done (0679ecf): hold mic or Space → same-origin worklet (`public/voice-capture-worklet.js`;
  **Electron refuses blob:-URL worklet modules**) → 16 kHz WAV → `/api/asr` (V's `src/voice/asr.ts`) →
  transcript bubble → submit; TTS speaks the answer after `done` via V's `src/voice/tts.ts` singleton,
  mute toggle (persisted `sparkmd-voice`), playback stops on capture/new question/Esc. E2E vs fake
  asr/tts + `--use-fake-device-for-media-stream`: WAV header verified 16 k/mono/s16, tts fires after
  done, 0 non-loopback. Real /api/asr+/api/tts on :8100 still pending (V); until then PTT toasts
  "unavailable", TTS stays silent. Real-mic test on the box display still to do.
- Mock G4 flow re-verified (smoke.mjs, private mock 8102): replay T0→T1, confirms, sheet, 121 req /
  0 non-loopback. Banner renders only during `/api/demo/replay` (plain "Drop next scan" doesn't set
  `replaying`) — use replay for the G4 rehearsal.

## For Ty (before 15:15 freeze)
- **Polish agent's `src/index.css` still drops `--radius: 0.625rem`** (replaced by `--win-radius`):
  every `rounded-sm/md/lg/xl` computes against an undefined var → all corners square in the current
  dist. Re-add the token in :root (I didn't touch their uncommitted file).
- `electron/main.cjs` (their file, uncommitted): I changed the permission handler to allow **only**
  `media` for allowed hosts — required for push-to-talk. Keep/commit it with their changes.
- `ui/src/pages/study.tsx` + `ui/src/components/risk-card.tsx` (another agent, uncommitted, in dist).

## Waiting
- G4 rehearsal 14:45 (real worker): banner + T1 assets check when T1 drops (T0 real assets verified).
- Real-mic + audible TTS check on the box display with Ty/Joyce (routes verified live).

## Perf fix (41ab657, measured on :1 with real GL)
- GPU process was ~100% CPU (continuous R3F loop; GL-on-EGL is CPU-bound). Now:
  idle `frameloop="demand"`, active controls/tweens use `"always"` with WebGL draws capped at
  30 Hz; rest/sleep returns to demand. `frameloop="never"` while the report sheet is open,
  `dpr={1}`, auto-rotate removed, sheet/dialog overlays + extras use plain scrims.
- Demand-mode regression fixed: `scene.updateMatrixWorld(true)` before bounds/node centres;
  explicitly start the render loop for home/focus and control events. Home settles in <1 s.
- Verified in the existing box window (CDP 9350, not headless): idle 0.4% GPU-process CPU;
  dragging 16.1%, median draw interval 33.4 ms / p95 34.6 ms; settled/repeated Reset 0%,
  sheet open 0.3% with zero canvas frames. No Confirm/Approve clicks.
- Proof: `/tmp/sparkmd-demand9350-fresh-t1-1s.png`, `/tmp/sparkmd-demand9350-sheet.png`;
  raw measurements `/tmp/sparkmd-demand9350-report.json`. Rebuilt `ui/dist`; Ty relaunches.
- NOTE for Ty: 08 deviations by the perf order — auto-rotate gone, overlays unblurred.
- Real voice chain verified on :8100: fake-device audio → real whisper.cpp (`command:null` on
  tone, correct), phrase chip → real agent answer → `/api/tts` (real Qwen3-TTS). Real-mic +
  audible playback still to check with Ty/Joyce on the box display.

## Run on the box
```bash
export PATH=~/.local/node-v22.23.4-linux-arm64/bin:$PATH npm_config_update_notifier=false
cd ~/spark-md-app/ui && npx tsc -b && npx vite build          # worker serves ui/dist at 127.0.0.1:8100
SPARKMD_UI_TARGET=http://127.0.0.1:8100 npx vite --host 127.0.0.1 --port 5173 --strictPort   # Mac: ssh -L 5173:127.0.0.1:5173 gb10
DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority npx electron .   # loads 127.0.0.1:8100; fallback --ozone-platform=x11
```
Headless test Electron: add `--ozone-platform=headless`, unset DISPLAY, use a private mock (`MOCK_PORT=8102 node mock/server.mjs`).
Never point tests at the real worker's confirm/approve; never touch W's window (CDP 9350).

## npm ci warning
`npm ci` replaces `node_modules/electron/dist/chrome-sandbox`; Ty must redo (sudo):
`sudo chown root:root …/chrome-sandbox && sudo chmod 4755 …/chrome-sandbox`. `--no-sandbox` is fallback only.

## Open risks
- Polish agent's uncommitted edits (`main.cjs`, `index.css`, `footer.tsx`, `sidebar.tsx`, `title-bar.tsx`) are in the
  current `ui/dist`. `index.css` drops `--radius`, which breaks every `rounded-sm/md/lg/xl`. Fix or revert before freeze.
- Human "Approved by" vs worker drafts mismatch: likely a mock behind the Mac's :5173. Real report IDs are hex, mock = `R1/R2`.
- W's window needs a reload (W's call) to pick up the fixes above.
- `pkill -f`/`grep [x]` patterns can match your own shell's command line; kill by PID.

## Time-machine video shots
- Compare now fetches the prior findings and matches `track_id` (not the first prior nodule):
  both real 512×512 key slices + pixel-space boxes, 6.5 → 10.4 mm, +3.9 mm / 357 days,
  worker `growing` label. Box-window shot: `/tmp/sparkmd-video/134503-t1-compare.png`.
- Physical-interface monitor shot: `/tmp/sparkmd-video/physical-interface-monitor.png`.
  Verified enP7s7/wlP9s9 have PCI device links; virtual interfaces excluded. NOT near-zero:
  524,118 bytes transmitted over a 10 s sample; ~289 MB cumulative since baseline. Do not
  reset/hide these numbers for the video. Ty must disconnect LAN and disable Wi-Fi for the
  unplugged/baseline-reset near-zero shot. No interface changes made by U.

## UI review corrections
- Slice overlays use stack metadata size or the loaded fallback image's natural dimensions;
  fallback fitting preserves non-square aspect ratios. Child viewer commands reject other UIDs.
- System counters retain their values but show "last known / stale" while SSE is down/connecting;
  cached link status is explicitly "Last known". Reconnection removes the stale label.
- Electron smoke verified 640×320 → 320×640 fallback changes and 800×400 stack boxes (zero
  pixel-centre error), foreign/current/changed-study command routing, and disconnect/reconnect.
  `tsc -b` + Vite build passed. Screenshot: `/tmp/sparkmd-review-stale-and-stack.png`.
