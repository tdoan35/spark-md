# UI (desktop app) — status line, rebuild notes, verification log

Append-only log for agent U. Keeps `08-ui.md` untouched except its status line; this file is the
day's build record (what exists in `ui/`, what was verified, what is unverified).

## Status

- **G1 (11:00 target) met**: shell renders fixtures from the mock worker on `127.0.0.1:8101`.
- **Real worker (06) switch done early**: the same UI runs against agent W's worker
  (`sparkmd/app.py`, `SPARKMD_FAKE_IMAGING=1`) on `127.0.0.1:8100`; contract v0.8 respected
  (confirm sends `{long_mm, short_mm, by}`; 409 already-approved treated as success; growth label
  uses `prior.growth_per_12mo_mm` + `growth_normalized`).
- **Unverified**: real MONAI/VISTA imaging + B9 assets on the GB10 (the worker here runs fake
  imaging with placeholder `.glb`s), Electron on Linux/aarch64 (`chrome-sandbox` fix), voice (09),
  fps on the box with the real mesh.

## What is in `ui/`

| Area | File | Notes |
| --- | --- | --- |
| Contract | `src/api/types.ts` | Frozen types for 00 v0.8 (approve 409 union, confirm result, findings with `prior.growth_per_12mo_mm`). |
| Client | `src/api/client.ts` | Same-origin `API_BASE` (page served by the worker on the box, Vite proxy on the Mac), `approve()` resolves 409 only when `already_approved === true`, `ask()` parses our own `delta/tool/done/error` SSE frames over POST. |
| Data | `src/api/{keys,hooks,sse,use-sse,viewer-bus}.ts` | QueryClient `staleTime 5 s`, no focus refetch, no retry on 4xx; one `EventSource`; handlers write payloads into the cache or invalidate; `study_updated` + `worklist_changed{status}` both refetch the study. |
| Shell | `src/shell/*` | 32 px title bar (menu, sidebar toggle, search, back/forward, tabs, `+`, theme, window controls), 240 px sidebar, 12 px main surface, 28 px footer with the research disclaimer and "Local only · Air-gapped" + System link. Hash router. |
| Pages | `src/pages/*` | Worklist (priority/Lung-RADS/status pills, animated reorder, Drop next scan + Reset), study (viewer-first, agent rail, inspector, longitudinal strip), EHR inbox, System (net monitor). |
| Study | `src/pages/study.tsx` | Header one row: patient · CT · timepoint · day · priority; review state; "Needs confirmation" pill; Review & approve opens the sheet. Inspector toggle (PanelRight) collapses to 0 px. Nodule rows: proposed A7 diameter, detector-box cross-check, editable long/short (prefilled), Confirm (worker computes mean), Edited tag, re-confirm. |
| Agent log | `src/components/agent-log.tsx` | Latest note, tool events with expandable payload, stick-to-bottom with "N new events ↓". |
| Report | `src/components/report-sheet.tsx` | 480 px sheet, radiology + PCP tabs, approver input focused on open (not the Approve button), mouse-only Approve (`e.detail === 0` ignored), 409/403 inline errors. |
| Viewer | `src/components/viewer/*` | 3D (R3F + `useGLTF(url,false,false)` + CameraControls), CT slice carousel (coverflow, wheel/arrows/scrubber, bracket in `box_px` pixel space), Compare (prior | Δ/VDT | current), extras panel, chat rail (fixed phrases fire `POST /api/viewer/command` before the agent answers). |
| Mock | `mock/server.mjs`, `mock/fixtures.mjs` | stdlib, deterministic; hero 134503 T0/T1/T2 + two rows; scripted replay; fail-closed proposal at T2; approve 409 both meanings; SSE with `id:`; generated glb/PNG assets. |
| Dev tools | `tools/smoke.mjs`, `tools/dom.mjs`, `scripts/start-dev.sh`, `scripts/dev-fixtures.sh` | CDP E2E over the real `electron/main.cjs`; layout probe; mock-backed Vite dev; placeholder 3D assets for the fake-imaging worker. |

## Contract notes found while wiring

- **Asset URLs**: worker key slices are `/api/studies/<uid>/assets/key_axial_<nodule_id>.png`
  (the UI rewrites `name`/`url` accordingly when the name lacks the nodule id); the mock names
  stacks `stack_{i}` zero-padded, the worker uses the raw index — both work via `url_pattern` +
  `index_digits`.
- **Reports button**: the header shows "Review & approve" for any draft (either kind); the sheet
  has both tabs. With no agent hooked, the fake worker writes no reports — the sheet still opens
  from an approved set ("View approved reports").
- **No confirm tool**: the UI is the only confirmer; the worker classifies non-loopback callers as
  agent (403).

## Verification (Oct 25, Mac, real Electron 44.5.1)

| Check | Result |
| --- | --- |
| `npm ci` + `node node_modules/electron/install.js` | 607 packages, Electron 44.5.1 binary |
| `npx tsc -b` / `vite build` | clean; main 813 kB, lazy `lung-3d` 1,039 kB; **0 gstatic/CDN strings** in the bundle (build plugin blanks drei's Draco decoder URL) |
| 3D on the Mac | WebGL2 via `use-angle=metal`; canvas 966×842 in the well (ANGLE Metal M2) |
| Smoke vs mock (speed 3) | worklist 5 rows → study → slices (5 imgs) → compare → chat phrase streams + viewer move → confirm T0 (LR 2) → drop T1 → confirm (LR 3, "+1.2 mm/12 mo · normalized", VDT) → Approve (mouse) → inbox row; 0 non-loopback requests; 0 console errors |
| Smoke vs worker (`SPARKMD_FAKE_IMAGING=1`, `SPARKMD_FAKE_SEED=1`, placeholder glbs via `scripts/dev-fixtures.sh`) | study auto-analyze → proposals → Confirm sends `{long, short, by}` → LR 4A from the worker's rules; 3D canvas live; 0 non-loopback requests |
| 1440×900 | no page overflow (`scrollHeight == innerHeight`), no horizontal scroll; grid 838 + 352 px |
| Approve from a non-loopback caller | worker 403 (`api/reports/.../approve`) — covered by 06's contract test |

Captures: `/tmp/sm-mock/*.png`, `/tmp/sm-worker/*.png` (not committed).

## Open / unverified

- Real imaging assets (B9): node names must equal `nodule_id`; `key_slices[].url` naming above.
- Electron on the event box: `chrome-sandbox` chown/chmod (nodehouse README); confirm `use-angle`
  flag choice there (`gl-egl` is pinned for arm64; the Mac needed `metal`).
- Voice (09): the mic button is a placeholder; `/api/asr` + `/api/tts` client calls are ready.
- Chat rail resize maths uses a fixed 380 px inspector offset; re-check at ≤1550 px where the
  inspector is 352 px.
