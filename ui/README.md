# Spark MD UI

Electron 44 + React 19 + Vite 8 + Tailwind v4 + shadcn, offline. Spec: `docs/build/08-ui.md`;
build record and verification log: `docs/build/08-ui-status.md`.

## Install (offline kit)

```bash
export npm_config_cache=/path/to/spark-md/nodehouse/npm-cache npm_config_offline=true ELECTRON_CACHE=/path/to/spark-md/nodehouse/electron-cache
npm ci --no-audit --no-fund
node node_modules/electron/install.js   # Electron 44 has no postinstall
```

## Run

- **Mac dev**: `scripts/start-dev.sh` in the repo root → mock worker on `127.0.0.1:8101`, Vite on
  `:5173` with `/api` proxied. `SPARKMD_UI_URL=http://127.0.0.1:5173/ npx electron .`
- **Event box / worker-served**: `npx vite build`, then the worker serves `ui/dist` at
  `http://127.0.0.1:8100/` and `SPARKMD_UI_URL=http://127.0.0.1:8100/ npx electron .` (default).
  The UI always speaks to the worker same-origin, so it is never routed through `10.77.0.1`.
- **Electron on Linux (aarch64)**: fix the SUID sandbox once —
  `sudo chown root:root node_modules/electron/dist/chrome-sandbox && sudo chmod 4755 …`.

The main process cancels any request that is not loopback / `10.77.0.1`, denies popups and
permissions, and turns off spellcheck (no dictionary download). Builds strip the only CDN string
drei would emit (`gstatic` Draco decoder; our glbs are uncompressed).

## Checks

```bash
npx tsc -b && npx vite build
node tools/smoke.mjs 8097 /tmp/shots          # CDP E2E against the real electron/main.cjs
WIDTH=1440 HEIGHT=900 node tools/dom.mjs      # layout geometry
```

`tools/smoke.mjs` proxies `/api` to `WORKER_URL` (default `127.0.0.1:8100`) or
`MOCK_URL=http://127.0.0.1:8101` for the mock; it prints a JSON report and writes screenshots.

## Mock (item M of 08)

`mock/server.mjs` is a stdlib deterministic worker: the 00 v0.8 routes the UI needs, SSE with
`id:` frames, a scripted time machine (`/api/demo/drop|replay|reset`), fail-closed proposals, both
409 approve meanings, and generated `.glb`/PNG placeholder assets. `MOCK_PORT` (8101),
`MOCK_SPEED` (1 = real time). Placeholder numbers only.

For agent W's worker in fake-imaging mode, `scripts/dev-fixtures.sh <SPARKMD_HOME>` copies the same
placeholder glbs and key-slice metadata into its cache so the viewer has assets.

## Boundaries

- The UI holds no medical logic: it formats worker numbers, never computes a mean, growth, VDT or
  category. Confirm sends `{long_mm, short_mm, by}`; Approve is a mouse click (`e.detail === 0` is
  ignored) and a 409 counts as success only when `already_approved === true`.
- "Research demo, not for clinical use" is on screen (footer) on every page.
- Voice (09) is a placeholder: `/api/asr` + `/api/tts` client calls exist; capture/playback come with 09.
