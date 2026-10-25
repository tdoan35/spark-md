# UI handoff (agent U, Oct 25 ~13:10)

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
- V: real `/api/asr` + `/api/tts` on :8100, then re-run the voice E2E against it.

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
