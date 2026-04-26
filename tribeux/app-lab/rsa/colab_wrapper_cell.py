"""Colab cell to turn the TribeUX notebook into an HTTP endpoint.

Paste this as a NEW cell at the BOTTOM of `tribeux_pipeline.ipynb`. It
assumes every previous cell has run and `model` (TribeModel) is in scope.

What it does:
  - Accepts POST /predict with a `screenshot` PNG file upload
  - Writes it to a temp file
  - Builds a 12-second static video (1 frame looped at 24 fps) via ffmpeg
    so TRIBE has a proper video tensor and not a single-frame degenerate
  - Calls model.get_events_dataframe + model.predict
  - Returns JSON: {features: [20484 floats, time-averaged],
                   raw_shape: [T, 20484],
                   construct_scores: {attention, self_relevance, reward, disgust, overall},
                   model: "tribe-v2", duration_s: 12.0}
  - Logs every request so the Colab cell output is the server's access log

Why 12 seconds:
  - TRIBE v2 output rate = 1 / fMRI TR = 1/2s = 0.5 Hz.
  - Hemodynamic lag ≈ 5s baked into TRIBE's targets.
  - 12s clip → ~5 TR points after lag; enough to time-average into a
    stable feature vector.
  - Matches the human-side experiment protocol (12s static screenshot
    per trial) 1:1. Same stimulus, same duration, both sides.

Expose via ngrok, copy the URL into:
    export TRIBE_ENDPOINT=https://xxxxx.ngrok.io/predict
on your laptop, then run `3_run_tribe.py` without --mock.
"""
# ============================================================================
# Install server deps (idempotent)
# ============================================================================
import subprocess, sys
_pip_pkgs = ["flask", "flask-cors", "pyngrok"]
subprocess.run([sys.executable, "-m", "pip", "install", "-q", *_pip_pkgs], check=True)

# ============================================================================
# Imports
# ============================================================================
import os
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, request
from flask_cors import CORS
from pyngrok import ngrok

# The notebook's prior cells define `model`, `destrieux_map`, `destrieux_labels`,
# `ROI_CONSTRUCTS`, `ALL_CONSTRUCTS`, `POSITIVE_CONSTRUCTS`, `NEGATIVE_CONSTRUCTS`,
# `zscore_vertices`, `roi_series`, `agg_pos`, `agg_neg`. We consume them.

# ============================================================================
# Config
# ============================================================================
STATIC_VIDEO_SECONDS = 6.0     # shorter clip → halves V-JEPA2 VRAM (fits in T4's ~14 GB)
STATIC_VIDEO_FPS = 24          # typical movie fps; TRIBE's V-JEPA2 frontend works with this
VIDEO_RESOLUTION = 256         # CNeuroMod "stimulus film" resolution; also speeds V-JEPA2 >30×
PORT = 5000

# Free the V-JEPA2 activation cache between requests so a prior /predict
# doesn't leave memory pinned for the next one. The Colab T4 has just
# enough headroom for one clip at a time.


# ============================================================================
# PNG → static video (ffmpeg)
# ============================================================================
def png_to_static_video(png_path: Path, out_path: Path,
                        seconds: float = STATIC_VIDEO_SECONDS,
                        fps: int = STATIC_VIDEO_FPS,
                        resolution: int = VIDEO_RESOLUTION) -> None:
    """Loop a single PNG into an `seconds`-second H.264 video at a fixed
    square resolution.

    -loop 1: treat the PNG as an endless stream
    -framerate: fps at which TRIBE's video decoder will see frames
    -t: cap total duration
    -vf scale+crop: fit longer side to `resolution`, then center-crop to a
        square. Preserves aspect-ratio content without letterboxing;
        important because TRIBE's V-JEPA2 frontend was trained on square
        256×256 CNeuroMod frames and cost is quadratic in pixel count.
    -pix_fmt yuv420p: required for H.264 + broad decoder compatibility
    """
    scale_crop = (
        f"scale={resolution}:{resolution}:force_original_aspect_ratio=increase,"
        f"crop={resolution}:{resolution}"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1",
        "-framerate", str(fps),
        "-i", str(png_path),
        "-t", str(seconds),
        "-vf", scale_crop,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


# ============================================================================
# Inference (reuses notebook's _score_from_events logic, returns richer payload)
# ============================================================================
def tribe_predict(png_path: Path) -> dict:
    """Given a PNG, run the full TRIBE → construct pipeline. Returns a payload
    ready to JSON-serialize. Time-averages raw activations to a single
    (20484,) feature vector for RSA comparison."""
    t_start = time.time()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)
    try:
        png_to_static_video(png_path, video_path)

        events = model.get_events_dataframe(video_path=str(video_path))
        preds, _segments = model.predict(events=events)
        arr = np.asarray(preds, dtype=np.float32)  # (T, 20484)
        assert arr.ndim == 2 and arr.shape[1] == 20484, f"Bad TRIBE shape: {arr.shape}"

        # Feature vector for RSA: time-averaged per-vertex activation.
        # Drop the first TR (onset / hemodynamic ramp-up) if we have >=3
        # timesteps so the averaged feature reflects sustained response.
        if arr.shape[0] >= 3:
            feature_arr = arr[1:].mean(axis=0)
            trimmed = True
        else:
            feature_arr = arr.mean(axis=0)
            trimmed = False

        # Also compute the 4-construct scores so the demo UI can display them.
        z = zscore_vertices(arr)
        series = {name: roi_series(z, ROI_CONSTRUCTS[name]) for name in ALL_CONSTRUCTS}
        scores = {}
        for name in POSITIVE_CONSTRUCTS: scores[name] = agg_pos(series[name])
        for name in NEGATIVE_CONSTRUCTS: scores[name] = agg_neg(series[name])
        scores["overall"] = (scores["attention"] + scores["self_relevance"]
                             + scores["reward"] - scores["disgust"])
    finally:
        video_path.unlink(missing_ok=True)
        # Release V-JEPA2 activation cache so the next /predict has full VRAM.
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    return {
        "features": feature_arr.tolist(),
        "raw_shape": list(arr.shape),
        "first_tr_trimmed": trimmed,
        "construct_scores": scores,
        "model": "tribe-v2",
        "duration_s": STATIC_VIDEO_SECONDS,
        "resolution_px": VIDEO_RESOLUTION,
        "elapsed_s": round(time.time() - t_start, 3),
    }


# ============================================================================
# Flask app
# ============================================================================
app = Flask(__name__)
CORS(app)  # browsers pick this up if the Vite app ever calls directly


@app.get("/health")
def health():
    return jsonify({"ok": True, "model": "tribe-v2"})


@app.post("/predict")
def predict():
    if "screenshot" not in request.files:
        return jsonify({"error": "upload a PNG as form field 'screenshot'"}), 400
    f = request.files["screenshot"]
    print(f"[tribe] /predict  name={f.filename}  content_type={f.content_type}")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        f.save(tmp.name)
        png_path = Path(tmp.name)
    try:
        payload = tribe_predict(png_path)
        print(
            f"[tribe]   → T={payload['raw_shape'][0]}, "
            f"elapsed={payload['elapsed_s']}s, "
            f"overall={payload['construct_scores']['overall']:+.3f}"
        )
        return jsonify(payload)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
    finally:
        png_path.unlink(missing_ok=True)


# ============================================================================
# Kick off ngrok + Flask
# ============================================================================
# Set this from a Colab secret for stable URLs; fine to leave None for
# ephemeral tunnels that change each restart.
_ngrok_token = os.environ.get("NGROK_AUTHTOKEN")
if _ngrok_token:
    ngrok.set_auth_token(_ngrok_token)

public = ngrok.connect(PORT, "http")
print()
print("═" * 70)
print(f"  TRIBE endpoint live: {public.public_url}/predict")
print(f"  (health check:       {public.public_url}/health)")
print()
print("  On your laptop:")
print(f"    export TRIBE_ENDPOINT={public.public_url}/predict")
print("    cd tribeux/app-lab/rsa")
print("    python 3_run_tribe.py data/stripe.com")
print("═" * 70)

app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
