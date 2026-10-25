# 10: Demo harness

Status: **draft (Oct 25).** Reset and drop routes are specified in 06 and 03; this spec adds the replay orchestrator, demo state, backlog build and seeding, the network monitor and the operator checklist. Of this, only the network-counter source was checked on a GB10 (sysfs on spark-2, Oct 25). Everything else is **unverified**.
Rebuild budget on the day: ~45 min (worker agent: replay, state, netstats; infra agent: backlog script). Estimate, unmeasured.

## Purpose and scope

Makes the three-minute story repeatable and honest: drop a patient's studies one timepoint at a time, wait for the humans (confirm, approve) rather than act for them, show what is live and what is cached, and prove that nothing leaves the box.

In: `POST /api/demo/replay`, `/stop`, `GET /api/demo/state`, SSE `demo_state`, the backlog layout and build script, background seeding, `GET /api/netstats` + SSE `net_stats`, the operator checklist.
Out: `demo/drop` and `demo/reset` (06 routes; behavior in 03 §Worker integration), UI banner and shortcuts (08), recording and editing (Joyce).
Cut first: background seeding, the connection counter, T2 in the replay.

## Interfaces

**Routes** (loopback only, like all `demo/*`; the sandbox cannot call them):

| Route | Body | Behavior |
| --- | --- | --- |
| `POST /api/demo/replay` | `{patient_id, timepoints?: ["T0","T1"], mode?: "live"\|"cached", speed?: 1, gap_s?: 3}` | Starts the orchestrator task for one patient (409 if one is running). Returns `{replaying:true, …state}`. |
| `POST /api/demo/stop` | – | Cancels the task at its next wait; leaves registry as is. |
| `GET /api/demo/state` | – | Current state (below). |
| `POST /api/demo/reset`, `POST /api/demo/drop` | see 06 | unchanged |
| `GET /api/netstats` | – | Counters (below). |

**`demo_state`** (08 pins the first four fields; the rest are **proposed additions**, 00 v0.7 when Ty agrees):

```json
{"replaying": true, "patient_id": "134503", "timepoint": "T1", "speed": 1,
 "mode": "live", "waiting_for": "confirm", "phase": "waiting_confirm"}
```

`waiting_for` ∈ `null | "confirm" | "agent" | "approve"`. `phase` ∈ `idle | dropping | analyzing | waiting_confirm | drafting | gap | done | stopped | failed`. SSE `demo_state` is sent on every phase change; the UI banner reads `phase` (replay colour) and shows `<speed>×` when `speed ≠ 1` and "cached results" when `mode = "cached"`.

**`net_stats`** (SSE every 2 s, and `GET /api/netstats`): `{tx_bytes, rx_bytes, since, interfaces:[{name, up, tx_bytes}], link_up}`. `tx_bytes` is the sum over **external** interfaces of (current − baseline), where the baseline is taken at worker start, at `demo/reset`, and on each transition of `link_up` from true to false.

## Dependencies

Stdlib only (`asyncio`, `pathlib`, `csv`) plus the worker (06) and intake (03). The backlog script needs `data/dicom/` and `data/nlst/` (prep data, present on the drive).

## Build steps

1. **Backlog build script** (`scripts/build_backlog.py`, run once per box, not part of the worker): for each demo patient, for each study, order by `StudyDate` and symlink or copy `data/dicom/nlst/<pid>/<study>/` into `$SPARKMD_HOME/backlog/<pid>/T<rank>/`. Also write `day_offsets.csv` (03) from `nlst_picked_prsn.csv` and `nlst_neg_neg_pos.csv`. Use symlinks only if the drive is ext4; the exFAT drive drops them, so copy (about 2 GB for 5 heroes, unmeasured). *Verify:* `ls backlog/134503` → `T0 T1 T2`; the T0 study's `StudyDate` is the earliest.
2. **`GET /api/netstats`** (below, snippet 1). *Verify:* read twice while running `ping -c 5 <lan host>` on a physical iface; `tx_bytes` rises; `lo`, `spark0`, `docker0` and `tailscale0` do not count.
3. **Replay task** (snippet 2) as an `asyncio` task in the worker; every phase change writes `demo_state` and SSE. *Verify:* `POST /api/demo/replay {patient_id:"134503",timepoints:["T0","T1"]}` → state walks `dropping → analyzing → waiting_confirm`, stops there until a human confirms, then `drafting → gap → …`.
4. **Confirmation and approval are never automatic.** The replay waits. `waiting_for:"confirm"` shows the banner "Waiting for radiologist". Dry-run aid only: `SPARKMD_ALLOW_AUTOCONFIRM=1` plus `"autoconfirm": true` in the replay body confirms with the proposal values and writes `confirmed_by = "demo-harness"`; the UI shows that string and the agent log gets a `system` line. **Refuse it when `SPARKMD_RECORDING=1`.** Approve has no automatic path at all.
5. **Seeding** (optional): `POST /api/demo/reset` seeds the other cohort patients (controls, one LIDC case) by `ingest_study` + analysis to `awaiting_confirmation` only, in `cached` mode. They are not confirmed and have no reports. *Verify:* worklist shows several studies; only the hero ever moves past "Needs confirmation" in the demo.
6. **Operator checklist** (below) run before every take.

## Parameters

| Parameter | Value | Source |
| --- | --- | --- |
| Replay default timepoints | `["T0","T1"]` (T2 optional) | storyboard 0:35–1:20 |
| `gap_s` | 3 s between a finished timepoint and the next drop | proposed |
| Wait for agent drafts | up to 180 s, then continue with a warning | proposed; phase-2 cost unmeasured (07: ~30 s cold prefill) |
| Wait for confirm | unbounded; operator can `stop` | human gate |
| `net_stats` interval | 2 s | 08 |
| External interface rule | `/sys/class/net/<if>/device` exists | spark-2, Oct 25 (below) |
| `mode` | `live` computes; `cached` reuses `cache/<SeriesUID>/` | 03 step 8 |

External interface set on spark-2 (Oct 25, sysfs): physical (has `device`): `enp1s0f0np0`, `enP2p1s0f0np0` (both `up`), `enp1s0f1np1`, `enP2p1s0f1np1` (down), `enP7s7` (up), `wlP9s9` (down). Virtual (no `device`): `lo`, `docker0`, `br-*`, `veth*`, `spark0`, `tailscale0`. The event box may differ; re-check with the same loop.

## Gotchas

- **"0 bytes sent" is only true when the counters say so.** Counters cannot tell cloud from LAN. A powered link sends ARP, mDNS and DHCP chatter, so `tx_bytes` won't sit at zero with the cable in. The storyboard's unplug is what makes it honest: baseline resets on the link-down transition, and the monitor shows `link_up:false` and the bytes since. Show the real numbers; if they are not zero, say so and explain, don't hide them.
- **Remote sessions count as traffic.** SSH, RDP or Tailscale over a physical interface raises `tx_bytes` (spark-2: 105 GB lifetime on `enP7s7`). Record at the console, with no remote desktop and nobody logged in over the network.
- **Counters reset on reboot or driver reload**; a negative delta means reset: rebaseline silently and log it.
- **Event IDs stay monotonic across reset** (08). `reset` must not restart `agent_events.id` or the UI drops new log lines as duplicates.
- **Agent session context.** The OpenClaw prompt is ~60k tokens and the LLM context is 65,536 (02). A warm session that accumulates several studies and Q&A turns may overflow. Start each replay with a fresh agent session (new key per study) and measure how many turns fit. **Unverified.**
- **Cached runs are real earlier runs, not live ones.** In `cached` mode the log must say "results reused from earlier run" and the banner shows it. Recorded footage that mixes modes needs the label (AGENTS.md honesty rule); sped-up footage gets "2×".
- **Stage timing is unmeasured end to end.** Known pieces: detection ~7 s/series on GB10, conversion 0.1–0.6 s (04), the old one-run agent chain 74 s median (07), a ~30 s cold prefill on each fresh session (07). Time a full T0→T1 live replay before deciding whether the recording uses live, cached, or live-with-"2×".
- **Seeded studies must not be confirmed by the harness.** If every background study has a Lung-RADS badge, the worklist looks like a clinical product with unverified measurements.
- **Replay must not change the registry beyond `drop`** (no direct `status` writes); everything advances through the real worker paths.

## Acceptance tests

| # | Test | Expect |
| --- | --- | --- |
| D1 | `reset` twice, then read SSE | `worklist_changed {reason:"reset"}` each time; `agent_events.id` keeps increasing |
| D2 | Replay 134503 `["T0","T1"]`, `mode:"live"`, confirm by click | phases advance only after each human action; T1 compare shows confirmed T0 as prior; no `confirmed_by` = `demo-harness` |
| D3 | Replay while one is running | 409 |
| D4 | `stop` mid-wait | `phase:"stopped"`, no further drops, registry untouched |
| D5 | Auto-confirm without env, and with `SPARKMD_RECORDING=1` | refused; with env only, confirmed with `demo-harness` shown in UI |
| D6 | `mode:"cached"` after one live run | log says reused; study reaches `awaiting_confirmation` in seconds |
| D7 | Approve attempted by the harness or via `/api/demo/*` | no such path; approve only by the UI click (06 403) |
| D8 | Net monitor while `ping` runs on a physical iface | `tx_bytes` rises; the same ping on `lo` doesn't move it |
| D9 | `ip link set <phys> down` (console, sudo) | `link_up:false`, baseline reset, bytes since stay near 0 |
| D10 | Full cold restart (reboot → start script → replay) | worklist returns, replay works from `backlog/` (feeds 11) |

None has been run.

## Measured performance

Only the interface scan above. No replay, seeding or netstats timing exists.

## Snippets

Network counters (external = has `device`; rebaseline on link-down or negative delta):

```python
def read_ifaces():
    out = []
    for d in Path("/sys/class/net").iterdir():
        if not (d / "device").exists():          # lo, docker0, veth*, spark0, tailscale0 have none
            continue
        out.append({"name": d.name,
                    "up": (d / "operstate").read_text().strip() == "up",
                    "tx": int((d / "statistics/tx_bytes").read_text()),
                    "rx": int((d / "statistics/rx_bytes").read_text())})
    return out

def sample(base):                                 # base: {name: (tx, rx)}
    ifs = read_ifaces(); tx = rx = 0
    for i in ifs:
        b = base.setdefault(i["name"], (i["tx"], i["rx"]))
        if i["tx"] < b[0] or i["rx"] < b[1]:      # counter reset
            base[i["name"]] = b = (i["tx"], i["rx"])
        tx += i["tx"] - b[0]; rx += i["rx"] - b[1]
    return {"tx_bytes": tx, "rx_bytes": rx, "link_up": any(i["up"] for i in ifs),
            "interfaces": [{"name": i["name"], "up": i["up"], "tx_bytes": i["tx"]} for i in ifs]}
```

Replay loop (waits for humans; never confirms or approves):

```python
async def replay(pid, tps, mode, gap_s):
    for tp in tps:
        set_state(phase="dropping", timepoint=tp); uid = ingest_from_backlog(pid, tp)   # 03
        set_state(phase="analyzing")
        await wait_status(uid, {"awaiting_confirmation", "failed"})
        if status(uid) == "failed": return set_state(phase="failed")
        set_state(phase="waiting_confirm", waiting_for="confirm")
        await wait_status(uid, {"analyzed", "reported", "approved"})          # human click
        set_state(phase="drafting", waiting_for="agent")
        await wait_reports(uid, timeout=180)                                  # warn, then continue
        set_state(phase="gap", waiting_for=None); await asyncio.sleep(gap_s)
    set_state(phase="done", replaying=False)
```

## Open / unverified

- Everything above except the sysfs scan: replay, state fields, seeding, auto-confirm guard, backlog build, cached-vs-live labelling.
- Whether the demo shows cache reuse or live runs; depends on a measured live T0→T1 time.
- Agent session context overflow across a replay.
- A connection counter (`ss` for non-loopback sockets owned by Spark MD processes) as a second, stronger "nothing leaves" signal. Not specified; first to cut.
- 00 v0.7: the `demo_state` additions and the new replay/stop routes, once Ty agrees.
- The storyboard still shows T0 → T1 without the confirm click; update with Joyce.
