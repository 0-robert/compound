"""Stage 3 — run TRIBE v2 on the six screenshots.

The plan is to POST each PNG to a TRIBE endpoint (hosted on Colab via ngrok)
and get back a predicted cortical-activation vector. Until that endpoint
exists, `--mock` produces synthetic deterministic feature vectors so the
rest of the pipeline (modules 4, 5) has real input to test against.

The mock is NOT random noise — it's a per-screenshot hash seeded RNG
producing a 115-dim vector. This way the same screenshot always maps to the
same mock "activation", which lets us verify stage 4/5 behave sensibly:
  - Mock Muse features correlate with themselves (RSA sanity check, r=1)
  - Mock TRIBE features are stable across runs

Once the real endpoint exists, set env var TRIBE_ENDPOINT and drop --mock.

Output:
    data/{site}/tribe_features.npz  (contains: features, meta)
        features: np.ndarray shape (N_SCREENSHOTS, D)
        meta: dict with provenance info

Usage:
    # real call (once the endpoint is up)
    export TRIBE_ENDPOINT=https://abc123.ngrok.io/predict
    python 3_run_tribe.py data/stripe.com

    # mock (for dev / testing downstream stages)
    python 3_run_tribe.py data/stripe.com --mock
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import requests


# Mock output dimensionality. 115 matches the Destrieux parcellation (roughly)
# and what TRIBE v2's Destrieux-ROI output would produce. If the real endpoint
# returns something else, we adapt — the RSA stage doesn't care about D.
MOCK_D = 115


def mock_features_for(png_path: Path) -> np.ndarray:
    """Deterministic fake activation vector seeded by the PNG's content hash.

    Properties:
      - Same PNG → same vector (reproducible)
      - Different PNG → different vector (non-degenerate RDM)
      - Magnitudes in ~N(0,1) so later z-scoring is a no-op
    """
    h = hashlib.sha256(png_path.read_bytes()).digest()
    seed = int.from_bytes(h[:8], "big")
    rng = np.random.default_rng(seed)
    return rng.standard_normal(MOCK_D).astype(np.float32)


def real_features_for(png_path: Path, endpoint: str) -> tuple[np.ndarray, dict]:
    """POST the PNG to TRIBE, return (feature_vector, response_metadata).

    Colab wrapper contract (see colab_wrapper_cell.py):
        POST endpoint with multipart file="screenshot", returns JSON:
          {
            "features":         [float, ... 20484 total],  # time-averaged
            "raw_shape":        [T, 20484],
            "first_tr_trimmed": bool,
            "construct_scores": {attention, self_relevance, reward, disgust, overall},
            "model":            "tribe-v2",
            "duration_s":       12.0,
            "elapsed_s":        float,
          }

    Inference is 20-60s per screenshot on an A100 so we give the request
    a long timeout. Fail loudly on bad payloads rather than silently
    drop construct scores — we want to know if the wrapper changed.
    """
    # Retry with backoff on transient failures — ngrok free-tier tunnels
    # sometimes return 5xx during long/heavy requests and recover a few
    # seconds later. Connection errors and timeouts get retried too.
    MAX_ATTEMPTS = 5
    BASE_DELAY = 10  # seconds, doubles each retry
    last_err: Optional[Exception] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(
            f"[tribe] POST {png_path.name} → {endpoint} "
            f"(attempt {attempt}/{MAX_ATTEMPTS})",
            file=sys.stderr,
        )
        try:
            with png_path.open("rb") as fh:
                resp = requests.post(
                    endpoint,
                    files={"screenshot": (png_path.name, fh, "image/png")},
                    # First inference on A100 is slow (V-JEPA2 warm-up + decoder
                    # init). Steady-state is ~30-60s. 20 min gives headroom for
                    # both without silently giving up.
                    timeout=1200,
                )
            if resp.status_code >= 500:
                last_err = requests.HTTPError(
                    f"{resp.status_code} {resp.reason} — "
                    f"body: {resp.text[:200]!r}"
                )
                print(f"[tribe]   → retryable HTTP {resp.status_code}",
                      file=sys.stderr)
            else:
                resp.raise_for_status()
                break  # success
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            print(f"[tribe]   → network error: {type(e).__name__}: {e}",
                  file=sys.stderr)

        if attempt < MAX_ATTEMPTS:
            delay = BASE_DELAY * (2 ** (attempt - 1))
            print(f"[tribe]   sleeping {delay}s before retry", file=sys.stderr)
            time.sleep(delay)
    else:
        raise RuntimeError(
            f"[tribe] failed after {MAX_ATTEMPTS} attempts — last error: {last_err}"
        )

    data = resp.json()
    if "features" not in data:
        raise RuntimeError(
            f"[tribe] response missing 'features' key. Got: {list(data)}"
        )
    vec = np.asarray(data["features"], dtype=np.float32)
    if vec.ndim != 1:
        raise RuntimeError(f"[tribe] expected 1-D features, got shape {vec.shape}")
    # Extract per-screenshot metadata for downstream display / QA.
    per_shot_meta = {
        "raw_shape": data.get("raw_shape"),
        "first_tr_trimmed": data.get("first_tr_trimmed"),
        "construct_scores": data.get("construct_scores"),
        "elapsed_s": data.get("elapsed_s"),
    }
    return vec, per_shot_meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("site_dir", type=Path)
    ap.add_argument("--mock", action="store_true",
                    help="Skip the HTTP call; generate deterministic mock "
                         "features seeded by each screenshot's content hash.")
    ap.add_argument("--force", action="store_true",
                    help="Re-run even if tribe_features.npz already exists. "
                         "By default we skip to save TRIBE compute.")
    args = ap.parse_args()

    site_dir: Path = args.site_dir
    manifest_path = site_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"[tribe] no manifest at {manifest_path}. "
                         f"Run stage 1 first.")
    manifest = json.loads(manifest_path.read_text())

    out_path = site_dir / "tribe_features.npz"
    if out_path.exists() and not args.force:
        print(f"[tribe] {out_path} exists — use --force to re-run.")
        return

    endpoint = os.environ.get("TRIBE_ENDPOINT")
    mode = "mock" if args.mock else ("real" if endpoint else None)
    if mode is None:
        raise SystemExit(
            "[tribe] TRIBE_ENDPOINT env var not set and --mock not given.\n"
            "        Either:\n"
            "          export TRIBE_ENDPOINT=https://your-ngrok.io/predict\n"
            "        or re-run with --mock for testing."
        )

    n = manifest["n_screenshots"]
    vectors: list[np.ndarray] = []
    per_screenshot_meta: list[dict] = []
    t0 = time.monotonic()

    for i in range(n):
        png_path = site_dir / manifest["screenshots"][i]
        if mode == "mock":
            vec = mock_features_for(png_path)
            shot_meta: dict = {"mock": True}
        else:
            vec, shot_meta = real_features_for(png_path, endpoint)
        vectors.append(vec)
        per_screenshot_meta.append(shot_meta)

    features = np.stack(vectors, axis=0)  # (N, D)
    meta = {
        "site": manifest["url"],
        "n_screenshots": n,
        "feature_dim": int(features.shape[1]),
        "per_screenshot": per_screenshot_meta,
        "mode": mode,
        "endpoint": endpoint if mode == "real" else None,
        "elapsed_s": round(time.monotonic() - t0, 3),
        "unix_ts": time.time(),
    }

    np.savez(out_path, features=features, meta=json.dumps(meta))
    print(
        f"✓ {features.shape} → {out_path.name} "
        f"({meta['mode']}, {meta['elapsed_s']}s)"
    )


if __name__ == "__main__":
    main()
