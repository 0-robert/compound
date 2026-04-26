# PR #9 — SSE Reconnect Dup + Lost-Error-Log Fixes — Test Report

**Verdict: all assertions passed.**
**Branch tested:** `devin/1777182737-sse-bugfixes` (merged into main mid-test).
**Mode:** mock-Claude (default), local dev (`uvicorn :8000` + `vite :5173`).
**Devin session:** https://app.devin.ai/sessions/93129ee2c1d240e8bd3ea24486234c59

## Summary

| Test | Result |
|---|---|
| It should stream pipeline state into the CLI panel live via SSE | passed |
| It should emit checkpoint markers with measured elapsed time | passed |
| It should auto-route to Report with correct axes/values | passed |
| It should not auto-reconnect EventSource after `done` (PR #9 dup fix) | passed |
| It should rehydrate Report after hard-reload (regression) | passed |

## Evidence — live SSE arrival

The Demo CLI grows progressively as the server emits events. A broken (polling/buffered) implementation would render all stages at once.

| t+0s — RENDER only | t+2.8s — through PROJECT |
|---|---|
| ![cli step 01](https://app.devin.ai/attachments/ce941698-a0f3-4cb2-bd31-db480c70565b/cli_step01.png) | ![cli step 04](https://app.devin.ai/attachments/aea69822-601d-4e57-8b6e-3620d9ce45af/cli_step04.png) |
| `RENDER · tribedomtree extracted 3 DOM unit(s)` + blinking `▮` caret | `PROJECT · destrieux mapping · attention/self/reward/disgust` |

| t+4.9s — through FRAMES | t+6.3s — DONE w/ elapsed |
|---|---|
| ![cli step 07](https://app.devin.ai/attachments/4050181e-a063-43e4-8e9f-2d4803d58b36/cli_step07.png) | ![cli step 09](https://app.devin.ai/attachments/4f5794f3-b5a4-4304-a710-dc4885e9e5fe/cli_step09.png) |
| `FRAMES · asked frames: [2,3,4,9,10,11,12]` | `✓ COMPOSE · TRIBEDOMTREE PATCH · v2 INFERENCE · 1.40S` then `✓ DONE · VERDICT` |

Captured progressively-growing log text per timestep:
```
t=0.0s  log_len=267   last: "RENDER | tribedomtree extracted 3 DOM unit(s)"
t=0.7s  log_len=470   last: "ENCODE | captured 13 frame(s)"
t=1.4s  log_len=706   last: "TRIBE | v1 headline cohort_z = att +0.19 · self +0.94 · reward +0.57 · disgust +0.40"
t=2.8s  log_len=872   last: "PROJECT | destrieux mapping · attention/self/reward/disgust"
t=3.5s  log_len=1046  last: "BENCHMARK | cohort n=30 · axes=attention,self_relevance,reward,disgust"
t=4.2s  log_len=1441  last: "CLAUDE | anomaly[reward] t=9-11 σ=0.63 | anomaly[disgust] t=11-12 σ=0.70"
t=4.9s  log_len=1598  last: "FRAMES | asked frames: [2, 3, 4, 9, 10, 11, 12]"
t=5.6s  log_len=2008  last: "COMPOSE | v2 headline cohort_z = att +0.19 · self +1.39 · reward +1.02 · disgust -0.15"
t=6.3s  log_len=2141  last: "✓ COMPOSE · TRIBEDOMTREE PATCH · v2 INFERENCE · 1.40S | DONE | overall predicted uplift +1.45σ"
t=7.0s  auto-routed to /report
```

## Evidence — PR #9 fix: EventSource closes on `done` (no reconnect → no dup)

Tracked every `/api/jobs/<id>/events` request via Playwright's `request` event:

```
EVENTS REQUESTS:
1) 05:56:52  /api/jobs/0f3f466d10eb/events   (Demo page useAnalysis hook — running)
2) 05:57:05  /api/jobs/0f3f466d10eb/events   (Report page useJob mounts on auto-route — replays)

-- HARD RELOAD of /report?job=0f3f466d10eb --

3) 05:57:06  /api/jobs/0f3f466d10eb/events   (one new useJob subscription on reload)

(waited 8s)
events requests after reload: 3 (delta from reload: 1)   <-- only ONE new request
```

Before the fix, `done` was a no-op so the browser auto-reconnected (`readyState` → `CONNECTING`, not `CLOSED`), `subscribe()` replayed the buffered transcript on each reconnect, and the reducer appended each replayed log/checkpoint to the existing arrays — duplicated transcript on every reconnect cycle (~5s).

After the fix: exactly one new connection per reload, no further reconnects in an 8s window.

| 🟢 Report renders correctly after hard-reload (no dup state) |
|---|
| ![report after reload](https://app.devin.ai/attachments/38235329-477c-4c29-841f-fe206557efed/report_after_reload.png) |
| h1 = `Worst axis vs cohort is \`disgust\`(mock claude)` — payload is intact, single-instance |

## Evidence — Report payload still correct (regression)

| Field | Expected | Observed | Result |
|---|---|---|---|
| h1 contains `Worst axis vs cohort is \`disgust\`` | yes | yes | pass |
| `(mock claude)` headline tag | yes | yes | pass |
| z-value `+0.19` (attention) on page | yes | yes | pass |
| z-value `+0.94` (self_relevance) on page | yes | yes | pass |
| z-value `+0.57` (reward) on page | yes | yes | pass |
| z-value `+0.40` (disgust) on page | yes | yes | pass |
| `+20` starburst | yes | yes | pass |

| 🟢 Report top |
|---|
| ![report top](https://app.devin.ai/attachments/eb06909f-af18-4a98-947f-e8452c682a8d/report_top.png) |

## Bug 2 (lost-error-log) — not directly exercised

The fix moves `log("error", ...)` before `jobs.store.fail()` so live SSE subscribers receive the message before the terminal `done` event closes their stream. Triggering this requires injecting an exception into the pipeline; the happy-path test above does not exercise it. The change is small and provably correct by inspection (`tribeux-server/tribeux_server/pipeline.py:265-272`). I did not add a synthetic exception path in test mode because doing so would have required modifying production code.
