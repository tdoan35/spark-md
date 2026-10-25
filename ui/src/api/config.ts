/**
 * The UI always talks to the worker over loopback. On the event box the page is served by the
 * worker itself (same origin), on the Mac dev server the `SPARKMD_UI_TARGET` proxy rewrites the
 * host — so a same-origin relative path is correct in both, and never routes through 10.77.0.1
 * (the agent's address, which gets 403 on confirm/approve). The Electron main process also only
 * allows loopback hosts.
 */
export const API_BASE = ""
