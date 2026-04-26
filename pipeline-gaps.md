# TribeUX pipeline — gap audit (server + UI)

Read against `continue_pipelinework.txt` and the current state of `main`
(commit `6103b0d`). This file picks up where §5 of the handoff left off
— it focuses on **gaps that are not already in §5** plus a couple that
are mentioned but mis-stated.

---

## A. Blockers (will hard-fail on a fresh clone)

### A1. `urltovideo/` is empty in this repo
- `tribeux-server/tribeux_server/render.py:22-27` does
  `sys.path.insert(0, repo_root/"urltovideo")` and then
  `from url_to_video import URLRecorder, VideoEditor`.
- On a fresh clone of `0-robert/compound` the `urltovideo/` directory
  contains zero files (verified with `ls -la urltovideo/` → `total 8`,
  just `.` and `..`). The handoff doc calls it "Local Python package
  the user wrote… has its own .git and venv" — i.e. it lives on your
  Mac but is not committed here.
- With `AnalyzeRequest.use_real_render: bool = True` (server-side
  default, `schemas.py:224`), the encode stage will throw
  `ImportError: No module named 'url_to_video'` on every fresh clone.
- The error bubbles to `pipeline.run_pipeline`'s outer try/except
  (`pipeline.py:278-285`), so the job is marked failed cleanly — but
  the demo never works for anyone but you.

**Fix options (pick one):**
1. Commit `urltovideo/` into this repo (subtree).
2. Make it a `git submodule` pointing at its own repo.
3. Publish it as a package and add it to `tribeux-server/pyproject.toml`.
4. Wrap the import in a try/except inside `render.render_url` and fall
   back to `frames.capture_frames(url, use_real_render=True)` (which
   uses Playwright directly, no urltovideo needed) when missing.

### A2. Frontend always sends `use_real_render: false` — server-side default flip is a no-op
- `continue_pipelinework.txt:120-122` claims the workaround is the
  server flipping `use_real_render` default to `True`.
- **That workaround does not actually work.** `tribeux/app/src/lib/api.js:21`
  defines `startAnalysis(url, { useRealRender = false } = {})` and
  `:26` always serialises the field:
  `body: JSON.stringify({ url, use_real_render: useRealRender })`.
  `Demo.jsx:44` calls `useAnalysis(urlFromQuery)` with no second
  argument, so `useRealRender` is `false` and the body is
  `{"url":"…","use_real_render":false}`.
- Pydantic respects the explicit `false`, not the schema default.
  Result: the live render / urltovideo / `/score` path is
  **unreachable from the UI today**. Every job runs in sample mode.
- This contradicts the handoff doc's claim that A1 is masked. It isn't.

**Fix:** either flip the FE default to `true`, or omit the field
entirely when `useRealRender === false` so the server default applies.
Recommend the former + a `?live=0` query param escape hatch.

### A3. No `.env` is committed; the server reads keys silently and degrades to mocks
- `tribeux-server/tribeux_server/main.py:12-15` loads `.env` from
  `tribeux-server/.env` then `<repo-root>/.env`. Neither exists in
  this clone.
- `claude_analyst.py:48-51`: `MOCK_CLAUDE` defaults to `"1"` AND falls
  back to mock if `ANTHROPIC_API_KEY` is missing.
- `inference.py:46-49`: `_use_real_tribe()` returns `False` whenever
  `TRIBE_INFERENCE_URL` is unset.
- Net effect on a fresh clone with no `.env`: every job is mock-Claude
  + stub-TRIBE. There is no banner anywhere telling the operator this.

**Fix:** the server should emit a one-shot startup log and a `mode`
field in `/api/health` so the FE can warn when running in pure-mock
mode. (Cheap to add: see C2.)

---

## B. Server-side gaps (live mode reliability)

### B1. Live `/score` failure is invisible to the CLI panel
- `inference.py:118-119`:
  ```python
  except Exception as exc:
      print(f"[inference] live /score failed, falling back to stub: {exc!r}", file=sys.stderr)
  ```
  This goes to **stderr only**. The pipeline keeps running and the
  user sees `tribev2.live · POST /score …` followed by `v1 headline
  cohort_z = …` with the canned numbers. There is no SSE log line
  saying the live call failed.
- This is the same class of bug we fixed for the Claude analyst's
  `[live call failed → mock]` summary string, but the fix didn't
  apply here.
- §5[3] in the handoff calls out the 404-glitch but only proposes
  logging "raw response body to stderr", which doesn't help — stderr
  is invisible to the UI.

**Fix:** plumb a logger into `inference.run_tribe_inference` (pass
`log` callable from `pipeline.run_pipeline`) and emit
`log("tribe", f"live /score failed → stub fallback: {exc}")` so the
operator sees it inline.

### B2. Live Claude failure has the same blind-spot
- `claude_analyst.analyze` returns the mock with summary
  `[live call failed → mock] {exc}` but `findings.model` still says
  `"mock-claude-deterministic"`. The `claude` stage CLI line reads
  `mock-claude-deterministic (mock) · 3 anomaly · 3 patch` — same
  exact line you'd see if `MOCK_CLAUDE=1` was deliberately set. There
  is no separate signal that a *live attempt happened and failed*.
- Same fix as B1: log the exception with the existing `log("claude",
  …)` callable, not as a baked-in summary prefix.

### B3. `_run_domtree` and `_apply_patch_live` have no timeout
- Both fall back gracefully on `Exception` (good), but if Playwright
  hangs waiting on `wait_until="networkidle"` against a slow site,
  the job hangs indefinitely. SSE keeps emitting keepalives; the user
  has no way to cancel.
- `analyze.py` defaults to no timeout. Recommend `asyncio.wait_for(
  ..., timeout=60)` in `_run_domtree`, and propagating
  `timeout=30_000` into `apply_patch`.

### B4. `render._full_screenshot` does a SECOND Playwright launch
- `render.py:67-81` opens its own browser to grab the full-page PNG
  for the report's "before" image — separate from the
  `urltovideo.URLRecorder` Playwright instance.
- §5[9] in the handoff acknowledges this. Worth fixing now: have
  `URLRecorder.record_scroll` return the full-page PNG alongside the
  video, save ~10s/request and one Playwright cold start.

### B5. `render.py:67` `_full_screenshot` returns `None` on failure → no screenshot in the report
- Frontend `Report.jsx` will then render with `screenshot_v1_data_url
  = null`. There's no fallback to the `tribedomtree` screenshot
  (`full_screenshot_v1` is overwritten on `:176` only when urltovideo
  succeeds and produces one).
- Fix: keep both — only overwrite if the urltovideo screenshot is
  non-null (`pipeline.py:176` already does this with `or`). The bug
  is that `render._full_screenshot` *can fail silently* AND
  `_run_domtree` is skipped if `use_real_render=False`. So in mixed
  failure modes the report ends up with no "before" image.

### B6. `pipeline.py:166` — `v1_frames` is referenced before definition on the failure path
- `v1_frames` is assigned inside both branches of the encode stage
  (`:175` for live, `:180` for sample). If `render.render_url` throws
  before `:175`, `v1_frames` is never bound and the next stage's
  `await inference.run_tribe_inference(url, v1_frames, …)` will
  `UnboundLocalError`.
- Outer `try/except` catches it, but the user sees a useless
  `NameError: v1_frames` instead of the original render exception.
- Fix: `v1_frames: list[Frame] = []` outside the `with stage("encode")`
  block, and guard the `tribe` stage with `if not v1_frames: skip`.

### B7. URL normalization
- `Demo.jsx:43` defaults `urlFromQuery = params.get('url') || 'stripe.com'`
  — no protocol. `URLRecorder.record_scroll` may or may not normalize
  scheme depending on its impl.
- Fix in one place — `pipeline.run_pipeline`'s entry: prepend
  `https://` if missing, reject obviously bad inputs with an early
  `log("error", ...)` + clean fail (so the SSE shows it).

### B8. `JobStore` never expires jobs
- `tribeux-server/tribeux_server/jobs.py` keeps every job and its
  full `Report` in memory forever. With live mode each Report carries
  base64-encoded PNG frames + before/after screenshots — easily
  several MB per job.
- Fix: TTL eviction on `store.get` + a max-size LRU. ~20 lines.

### B9. CORS is `*` and there is no auth on `/api/analyze`
- `main.py:27-31`. Fine for localhost dev. If you ever expose this
  publicly (and the user has been pasting ngrok URLs around), an
  unauthenticated `POST /api/analyze` lets anyone burn your
  Anthropic credits + drive Playwright against arbitrary URLs.
- Even if not deploying yet — drop a `# SECURITY: localhost only`
  comment so future-you remembers.

### B10. Anthropic key surface area
- §5[5] in the handoff is right that the key has been pasted in
  chat. **Rotate it now** — https://console.anthropic.com/settings/keys.
- Belt-and-braces: the server doesn't currently log the key, but
  `print(f"[inference] live /score failed … {exc!r}", file=sys.stderr)`
  will dump request URLs from httpx. Fine for `/score` but if you
  ever switch the stub-fallback path to do anything with the
  Anthropic SDK, audit before merging.

### B11. `screenshot_v1_data_url` / `screenshot_v2_data_url` are `Optional[str] = None` but `Report.jsx` doesn't gate on null
- `Report.jsx:264, 372-373, 382-383` reads these fields. If the
  pipeline produced no screenshot (B5), `<img src={null}>` renders an
  invisible/broken-image. Frontend should fall back to
  `result.frames[0].data_url` or a skeleton.

### B12. No tests on disk (handoff §5[8])
- The two passing tests in §4 (urltovideo render against
  `example.com`, claude_analyst live call) only exist as inline shell
  snippets in your transcript. Worth committing as
  `tribeux-server/tests/test_render_smoke.py` and
  `tests/test_claude_live.py` (gated on `ANTHROPIC_API_KEY`).
- Add a `make smoke` or `pytest -m smoke` target for fast end-to-end
  confidence.

---

## C. UI-side gaps

### C1. POST /analyze error message is opaque
- `api.js:28`: `throw new Error('POST /api/analyze failed: 502')`.
  This is exactly the line you saw earlier ("Error: POST /api/analyze
  failed: 502" — verbatim). The body of the response is discarded.
- Fix:
  ```js
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`POST /api/analyze failed: ${res.status} ${body.slice(0,300)}`)
  }
  ```
  Also surface the upstream `502 Bad Gateway` pattern with a
  diagnostic — usually means uvicorn isn't on `:8000`.

### C2. No backend health check on mount
- `api.js:66-73` exports `ping()` but it's never called. A 1-second
  check on mount would let the FE show a "backend offline — is
  uvicorn running on :8000?" banner before the user clicks Scan.
- Bonus: extend `/api/health` to return mode flags
  (`mock_claude`, `mock_tribe`, `live_render_available`) and render
  them as discreet badges in the page header. Fixes A3's silent-mock
  blind spot.

### C3. `Demo.jsx:53` — `frames` only available after `result`
- `const frames = useMemo(() => job?.result?.frames || [], …)`. The
  pipeline emits `result` ONCE, at the very end. So during the live
  scan (~2 minutes), the 256² stimulus preview window is empty until
  the verdict beat — exactly the moment when the user least cares
  about it.
- Fix: emit frames **incrementally** as they're captured. Two options:
  1. Add `frame` SSE event in `pipeline.py` after each frame ffmpeg
     extraction (`render._extract_frames`). Cheap.
  2. Stream the urltovideo recording itself (HLS / WebRTC). Heavy.
  Option 1 is a 30-line change.

### C4. `useJob` has no error visibility for stale deep-links
- `useAnalysis.js:87-91`: if `/api/jobs/{id}/events` returns 404
  (job evicted, server restart), the `EventSource` `onerror` fires
  with no payload; `setError('stream closed')` is the only message.
  Generic + unhelpful.
- Fix: `useJob` should `fetch('/api/jobs/{id}')` first, surface a
  proper "job no longer exists" message, and offer a "Start over"
  CTA back to `/landing`.

### C5. EventSource auto-reconnect on transient backend death
- Browsers retry SSE every ~3s indefinitely. If uvicorn crashes
  mid-pipeline, the FE quietly reconnects forever. The user sees a
  paused CLI panel.
- Fix: track reconnect count in `useAnalysis`; after N attempts (5?)
  give up and surface "stream lost — reload?".

### C6. No URL-input validation
- `Landing.jsx` (probably; not pasted) hands a raw string off via
  router state. No `https://` enforcement, no obvious-typo check
  (e.g. "stripe..com"). Backend will fail eventually with a
  Playwright error that's hard to read.
- Fix: cheap URL parse in `startAnalysis`; reject early with a
  toast/inline error.

### C7. No "live mode" affordance
- Per A2, the FE never enables live mode. Even after fixing A2, the
  user has no way to opt out for offline/CI runs. Suggest a
  `?live=0` URL param honored by Demo and a tiny mode pill in the
  page header (`LIVE`/`SAMPLE`/`MOCK`).

### C8. No retry / abort UI
- After an error toast, the user's only option is to navigate back
  and start over. `useAnalysis.start(url)` is exported but not
  wired to a button. Two-line fix in Demo.jsx.

### C9. mockFixture.js may drift from schema
- `mockFixture.js` constructs a hard-coded `MOCK_REPORT` matching
  `Report` shape. If the schema gains/drops fields (e.g.
  `overall_predicted_uplift` was added recently), the mock mode
  breaks silently.
- Fix: `tribeux-server` could write a `mockFixture.json` from a
  `pytest --update-fixture` run; commit alongside the schema.
  Cheap insurance against drift.

### C10. `tribeux/app/.env` not in repo or `.env.example`
- `vite.config.js:12` reads `env.TRIBEUX_API_URL`. There is no
  `tribeux/app/.env.example` documenting that. New contributors
  won't know the var exists or that the proxy can be retargeted.
- Fix: commit `tribeux/app/.env.example`:
  ```
  # Vite proxy target for /api/*. Defaults to http://127.0.0.1:8000.
  TRIBEUX_API_URL=http://127.0.0.1:8000
  ```

---

## D. Already in handoff §5 (acknowledging, no action needed)

- §5[1] full E2E test against airbnb.com with live envs
- §5[2] click-through smoke
- §5[3] `/score` 404 glitch (also see B1)
- §5[4] v2 inference is still the stub-shifter
- §5[5] leaked Anthropic key (also see B10)
- §5[6] FE never passes use_real_render — handoff says "worked
  around"; that's wrong (see A2)
- §5[7] urltovideo packaging — also blocks A1
- §5[8] no tests on disk (also B12)
- §5[9] Playwright runs twice (also B4)

---

## E. Recommended sequence (3-PR ladder)

**PR 1 — make a fresh clone actually work end-to-end (closes A1, A2, A3, C2, C10).**
- Commit `urltovideo/` (or submodule it).
- Flip `api.js` `useRealRender` default to `true`; keep `?live=0` escape.
- Have `/api/health` return mode flags; FE renders a status pill.
- Ship `tribeux/app/.env.example`.
- ~150 LOC.

**PR 2 — surface live-mode failures in the CLI (closes B1, B2, B6, B11, C1, C3, C4).**
- Plumb `log` callable into `inference` and `claude_analyst`; emit
  fallback events.
- Pre-init `v1_frames` outside the encode `try`.
- Add `frame` SSE event so stimulus preview lights up live.
- `api.js` reads body on error; `useJob` checks `/api/jobs/{id}`
  first.
- Report.jsx falls back to `frames[0]` when screenshots are null.
- ~250 LOC.

**PR 3 — robustness + tests (closes B3, B7, B8, B12, C5, C6, C8).**
- Timeouts on Playwright stages; URL normalization at pipeline entry.
- `JobStore` LRU + TTL.
- Reconnect-attempt cap in `useAnalysis`.
- `tribeux-server/tests/` with two smoke tests + a `pytest -m smoke`
  marker.
- ~200 LOC.

Each PR is independently shippable; #1 unblocks everyone, #2 makes
debug sessions humane, #3 hardens for actual use.

---

## F. Out of scope but worth noting

- **v2 re-inference is still the stub-shifter** (§5[4]). If you want
  the patched DOM screenshot to flow back through `/score` for an
  actual second forward pass, that's a separate non-trivial change:
  pipeline.compose needs to render the patched page to mp4 (not just
  PNG) and POST again. Scope creep relative to "make it work".
- **`apply_patch` only patches one selector at a time, navigates per
  call** (in tribeux-domtree). With 3 patches that's 3 fresh
  navigations. If you ever do >5 patches per scan, batch them in a
  single page session.
