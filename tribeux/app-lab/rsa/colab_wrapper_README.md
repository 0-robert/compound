# Exposing the TRIBE Colab notebook as an HTTP endpoint

`colab_wrapper_cell.py` is meant to be pasted as a **new final cell** at the
end of `tribeux_pipeline.ipynb`, turning the notebook into a live server
that `3_run_tribe.py` can POST to.

## Why this exists

TRIBE v2 needs a CUDA GPU (A100 ideally). Our laptop can't run it. The
notebook already runs on Colab; we just need a tunnel from our laptop to
the notebook's in-memory `model`. Flask + ngrok inside Colab = 15 lines
of glue, no docker, no deployment.

## Contract

**Request**

```
POST /predict
Content-Type: multipart/form-data
  screenshot: <PNG bytes>
```

**Response**

```json
{
  "features":         [float × 20484],
  "raw_shape":        [T, 20484],
  "first_tr_trimmed": true,
  "construct_scores": {
    "attention":      0.123,
    "self_relevance": 0.045,
    "reward":         0.210,
    "disgust":       -0.088,
    "overall":        0.466
  },
  "model":      "tribe-v2",
  "duration_s": 12.0,
  "elapsed_s":  34.1
}
```

The `features` vector is the time-averaged per-vertex cortical activation,
ready for RSA. The `construct_scores` piggy-back the notebook's existing
peak-end UX scoring — we use them for display in the demo UI but not for
RSA (4 dims is too low).

## Why 12 seconds per screenshot

From the TRIBE v2 paper + repo README:

- Training used CNeuroMod fMRI at **TR = 2 seconds** → TRIBE output is one
  activation vector per 2s of stimulus
- **5-second hemodynamic lag** is baked into TRIBE's targets
- V-JEPA2 video frontend operates at **30 fps**

At 12 seconds we get ~5 TR points after the hemodynamic onset; we drop the
first TR (onset ramp) and average the rest. This matches our human-side
experiment exactly: human looks at screenshot for 12s while Muse records,
TRIBE "looks" at a 12s static video of the same PNG. Same duration, same
stimulus content.

## Running it

### Setup (first time)

1. Open `tribeux_pipeline.ipynb` in Colab
2. Runtime → Change runtime type → **A100** (T4 works but slower)
3. Run every cell in order up through the smoke tests (cells 1–13)
4. Paste the contents of `colab_wrapper_cell.py` as a new final cell
5. Run that cell

### What you'll see

The cell prints something like:

```
══════════════════════════════════════════════════════════════════════
  TRIBE endpoint live: https://abc-123-xyz.ngrok-free.app/predict
  (health check:       https://abc-123-xyz.ngrok-free.app/health)

  On your laptop:
    export TRIBE_ENDPOINT=https://abc-123-xyz.ngrok-free.app/predict
    cd tribeux/app-lab/rsa
    python 3_run_tribe.py data/stripe.com
══════════════════════════════════════════════════════════════════════
```

### Use from your laptop

```bash
export TRIBE_ENDPOINT=https://abc-123-xyz.ngrok-free.app/predict
cd tribeux/app-lab/rsa
python 3_run_tribe.py data/stripe.com        # posts 6 PNGs
python 3_run_tribe.py data/airbnb.com
python 3_run_tribe.py data/linear.app
```

Each POST takes ~30s (A100) or ~60s (T4). Six screenshots × three sites ≈
10 min total.

## Quirks

- **Free Colab disconnects after ~90min idle.** If it dies mid-session,
  rerun the notebook from the top; the ngrok URL will change.
- **ngrok URL is ephemeral** unless you set `NGROK_AUTHTOKEN` as a Colab
  secret. Free ngrok rotates the domain each restart.
- **The first request warms caches** — video decoder init, ffmpeg probing,
  etc. Expect the first /predict to take a little longer.
- **Don't parallel-fire requests** — we don't use a threaded Flask worker,
  and `model.predict` isn't thread-safe in any case.

## Debugging

- `GET /health` returns `{"ok": true, "model": "tribe-v2"}` — useful to
  check the tunnel before sending big payloads
- The Colab cell output IS the server log — every request prints a line
- Exceptions print full tracebacks into the cell output so you can see
  what broke

## When the hackathon ends

Move the inference to a stable host (HF Spaces with T4, Modal,
RunPod Pod). The Flask route is unchanged; drop the ngrok line and point
your laptop at the public URL. Zero client changes needed.
