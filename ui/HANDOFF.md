# UI handoff (agent U, Oct 25 ~12:40)

## Done (all committed, `git log -- ui`)
- Box bring-up: Node 22.23.4 in `~/.local/node-v22.23.4-linux-arm64` (PATH line in `~/.bashrc`/`~/.profile`), offline `npm ci`, Electron 44 from nodehouse; GB10 GPU via `use-angle=gl-egl` on linux arm64.
- Real worker (:8100) verified: worklist, hero T0 study, Needs-confirmation panel (G2).
- Confirm: sends `{long_mm, short_mm, by}`; refetches after each confirm (worker sends SSE only after the last).
- Approve: 409 = success only when `already_approved === true`, else the worker's reason; sheet closes only via X/Esc;
  keyboard Approve shows a toast (mouse only by design); every click logs `[sparkmd] approve click detail=… report=…`.
- EHR inbox renders the delivered PCP letter from outbox `payload`; radiology approve = "Signed and filed" (no outbox).
- Net monitor (System page) built to 10's `net_stats`; shows "—" (never a fake 0 B) until `/api/netstats` answers.
- Replay banner: `<speed>×` badge, "cached results" when `mode = "cached"`, reads `/api/demo/state` on load.
- Placeholder caption only when `findings.placeholder`; agent-log history parses `payload_json`.
- Mock (`mock/server.mjs`) matches the worker's outbox (pcp_letter only, `payload`) and replay `mode`.

## Waiting
- W: `GET /api/netstats` + SSE `net_stats` (404 at 12:35). Then check System page + sparkline.
- V: push-to-talk contract (`/api/asr`, `/api/tts` client stubs exist in `src/api/client.ts`; capture/playback not built).
- I: real `lung_mesh` / `nodule_mesh` / `slice_stack`. Until then 3D shows "No 3D assets"; slices tab shows the real key slice.

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
