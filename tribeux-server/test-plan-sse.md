# PR #8 — Live SSE + Checkpoints in Demo CLI

## What's being tested
The Demo CLI panel was previously fed by frontend polling of `GET /api/jobs/{id}` with simple log lines. PR #8 replaces that with `GET /api/jobs/{id}/events` (SSE) and bracketed stage `Checkpoint` events. The CLI now renders **logs + begin/end checkpoint markers** as the server emits them.

A broken implementation would either:
- show no checkpoint markers (only flat log lines) — proves checkpoints aren't fed through, OR
- show all events at once at the end (polling/buffered) — proves it isn't streaming, OR
- crash on hard-reload of `/report?job=…` — proves SSE replay-on-subscribe doesn't work for finished jobs.

## Primary flow
**Landing → Demo (live SSE) → Report → deep-link reload**

### Step 1 — Submit a URL
- Action: type `stripe.com` in the URL input on `/`, press Enter
- Expect: navigate to `/demo?url=stripe.com`, CLI panel becomes visible

### Step 2 — Verify live SSE arrival in the CLI
- Take screenshots at ~2s intervals for the first ~10s of the run
- **Pass criteria** — *each must hold, in this order*:
  1. The CLI starts almost empty with at most the boot prompt + `▸ render` checkpoint + a few render log lines (NOT all stages already filled in)
  2. Successive screenshots show *more* lines than the previous, with new stages appearing one at a time (`▸ encode`, `▸ tribe`, `▸ project`, `▸ benchmark`, `▸ claude`, `▸ frames`, `▸ compose`)
  3. Closed stages show `✓ <stage>` in green-ish color, with an elapsed measurement (e.g. `· 1.40s`)
  4. A blinking caret (▮) is visible at the bottom of the CLI while the job is running
- **Fail signature**: all 9 stages appear in one frame (would mean buffered batch render); or no `▸`/`✓` glyphs (would mean checkpoints aren't being emitted/rendered)

### Step 3 — Verify Report renders from SSE result
- After ~13s the page auto-routes to `/report?job=<id>`
- **Pass criteria**:
  - 4 axis rows with z-values matching the server's `samples/site_1.json` (`+0.19`, `+0.94`, `+0.57`, `+0.40`)
  - `(mock claude)` tag in the headline
  - Starburst shows `+20%`
- This is a regression check — the SSE refactor must not have broken the Report payload shape.

### Step 4 — Verify SSE replay-on-subscribe (deep-link reload) + no dup
- Action: Copy the `/report?job=<id>` URL from address bar, hard-reload (Ctrl+Shift+R)
- **Pass criteria**:
  - Page rehydrates with the same axes + findings (no `Loading findings…` stuck state, no console error).
  - **No duplication**: in DevTools Network tab, only ONE `/api/jobs/<id>/events` connection is opened (and its readystate goes to `2 (CLOSED)` shortly after `done`). Wait 10s and confirm no further `/events` reconnect requests appear.
  - This is the regression check for PR #9: before the fix, the `done` handler was a no-op so EventSource auto-reconnected indefinitely and each reconnect appended the entire buffered transcript again.
- **Fail signature**: `Loading findings…` indefinitely, or multiple `/events` requests in network tab (would prove the dup-on-reconnect bug is back), or visible duplicated stage labels in any UI surface that shows the transcript.

## Source-of-truth references
- SSE endpoint: `tribeux-server/tribeux_server/main.py:46-93`
- Subscriber + replay: `tribeux-server/tribeux_server/jobs.py:73-106`
- Stage checkpoints: `tribeux-server/tribeux_server/jobs.py:188-209` + pipeline at `tribeux-server/tribeux_server/pipeline.py:128-264`
- EventSource client: `tribeux/app/src/lib/api.js:35-50`
- Job state reducer: `tribeux/app/src/lib/useAnalysis.js:12-47`
- CliStream component: `tribeux/app/src/Demo.jsx:286-377`
- Checkpoint CSS: `tribeux/app/src/App.css:682-708`

## Mode
Mock-Claude (default), sample-render (no Playwright). No secrets needed.
