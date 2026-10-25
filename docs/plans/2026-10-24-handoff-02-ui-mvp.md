# Handoff 02: UI MVP (Track D, L7), Oct 24

**You build the throwaway UI MVP and turn what you learn into `docs/build/08-ui.md`.** The spec is the deliverable; the code is deleted tonight.

## Read first
1. `AGENTS.md` (non-negotiables, machines, build rule).
2. `docs/build/08-ui.md`: decisions, layout, pieces U0–U11, interfaces, tokens, gotchas. **Already agreed with Ty; don't re-litigate.**
3. `docs/build/00-architecture.md` §Worker API, §Findings payload, §Flows.
4. `nodehouse/README.md`: offline install.
5. `docs/spark-md-storyboard.md`: what has to be on screen.

## Where
- Code: `/mnt/ty-ubuntu/projects/spark-md-mvp/ui/` (laptop; create it). **Never inside `spark-md/`.** Copy files out of the CIFS mount to a local dir if `node_modules` is slow there.
- Laptop only for now. The real worker (L5) doesn't exist yet; build against your own mock (piece **M**).

## Setup (offline, as the event will be)
```bash
NH=/mnt/ty-ubuntu/projects/spark-md/nodehouse
export npm_config_cache=$NH/npm-cache npm_config_offline=true ELECTRON_CACHE=$NH/electron-cache
cp $NH/ui/{package.json,package-lock.json,components.json} <ui-dir>/ && cd <ui-dir> && npm ci
node node_modules/electron/install.js
OFFLINE=1 python3 -I $NH/serve_registry.py $NH/shadcn 4000 &   # stop it when done
REGISTRY_URL=http://127.0.0.1:4000/r npx --offline shadcn add -y -o <components from 08's list>
```
If you need a package that isn't in the kit, stop and tell Ty. Adding one means re-filling the cache on a Spark (see `nodehouse/README.md`).

## Do, in order (08 → Pieces)
P0 first: **U0** scaffold + Electron main → **M** mock worker (alongside U0–U1) → **U1** shell → **U2** data layer → **U3** worklist → **U4** agent log → **U5** study view → **U8** report sheet + Approve + EHR inbox. Then P1: U6 3D, U7 slices/compare, U9 ask. P2: U10, U11.

- **Design reference:** Ty's fabric app, `/mnt/ty-ubuntu/projects/fabric/apps/web/src/components/shell/` (`title-bar.tsx`, `tabs.tsx`, `app-shell.tsx`), `styles/globals.css`, `components/ui/sheet.tsx`, `components/weave/weave-screen.tsx`. **Read it for behaviour and look; rebuild, don't copy files** (build rule). Drop the aurora background and avatars.
- **Mock worker (M):** v0 routes from 00 + SSE `/api/events` emitting all 8 event types + a scripted time-machine replay (T0 then T1 for patient **134503**, following the triage flow in 00 §Flows 1) + placeholder `.glb` meshes and PNG slices. **Label every fixture number as a placeholder.** Don't edit `bench/fixture_worker.py` (Track C owns it).
- **Electron:** frameless, `spellcheck:false`, no updater, loads `SPARKMD_UI_URL` (default `http://127.0.0.1:8100/`). Laptop runs without sandbox tweaks; GB10 needs the `chrome-sandbox` fix (08 gotchas).
- **Pin down and write into 08 (and a change-log line in 00):** SSE payload shapes, `/api/ask` stream format, approve UX, Lung-RADS badge scale. Coordinate mapping (RAS mm → three.js) and key-slice naming must match Track B's B9 render output; check `docs/build/04-imaging-pipeline.md` / ask Ty.

## Done when
- P0 pieces work end to end against the mock at 1920×1080 in Electron; the time-machine replay plays through the UI.
- `08-ui.md` is filled per the template: build steps with verify commands, parameters, gotchas found, acceptance tests run, ≤30-line snippets (drag regions, title bar/sidebar alignment, SSE → query cache, camera move). No whole source files.
- Screenshots for Joyce (worklist, study view, approve → inbox) in `tmp/ui-screens/`.
- Status row "UI (L7/E3)" in `docs/plans/2026-10-24-prep-day-plan.md` updated.

## Don't
- Touch spark-2 or spark-1 (P0b, the WebGL check on GB10, is being done separately).
- Add CDNs, web fonts, remote assets, drei `<Environment preset>` or `<Text>` (they fetch from the network).
- Build past **20:30**. At the cut, write the unfinished pieces into 08 marked **unverified**.
