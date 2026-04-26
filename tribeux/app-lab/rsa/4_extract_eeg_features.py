"""Stage 4 — EEG feature extraction per screenshot.

Reads the raw Muse recording and the events.csv from stage 2, cuts the EEG
into per-trial windows aligned to stim_on → stim_off, computes bandpower
features per channel per band, averages across the 3 repeats per screenshot.

Output is muse_features.npz of shape (N_SCREENSHOTS, 18) — ready to feed
directly into stage 5's RSA.

Feature vector per trial (18 dims):
    channels: TP9, AF7, AF8, TP10 (4)
    bands:    theta (4-8), alpha (8-13), beta (13-30), gamma (30-45) (4)
    → 16 bandpower features
    + log(alpha_AF8 / alpha_AF7)   frontal asymmetry (affective valence)
    + log(alpha_TP10 / alpha_TP9)  temporal asymmetry
    = 18 features

Artefact rejection: any trial where any channel's peak-to-peak exceeds
500 µV is flagged and excluded from the average for its screenshot. If
all 3 repeats for a screenshot are rejected, the extractor errors out —
you can't do RSA with a missing row.

Usage:
    python 4_extract_eeg_features.py data/stripe.com
    # → data/stripe.com/muse_features.npz
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import welch, butter, filtfilt


# Muse 2 nominal sample rate and channel order as muselsl writes it.
SR = 256.0
MUSE_CHANNELS = ["TP9", "AF7", "AF8", "TP10"]

# Frequency bands for the feature vector.
BANDS = {
    "theta": (4, 8),
    "alpha": (8, 13),
    "beta": (13, 30),
    "gamma": (30, 45),
}
BAND_NAMES = list(BANDS.keys())

# Artefact reject if peak-to-peak exceeds this. Motion and blinks blow past
# ±500 µV; clean EEG on forehead is typically ±50 µV.
REJECT_PP_UV = 500.0


def load_eeg_csv(path: Path) -> pd.DataFrame:
    """muselsl writes CSVs with a header: 'timestamps, TP9, AF7, AF8, TP10,
    Right AUX, Marker0…'. Column names are NOT guaranteed — recent versions
    change the casing — so we resolve columns by position not by name, and
    keep only the first 5 columns (timestamp + 4 EEG channels)."""
    if not path.is_file():
        raise SystemExit(f"[eeg] file not found: {path}\n"
                         f"      Did stage 2 complete cleanly?")
    df = pd.read_csv(path)
    if df.shape[1] < 5:
        raise SystemExit(f"[eeg] expected ≥5 columns, got {df.shape[1]}. "
                         f"Columns: {list(df.columns)}")
    # Rename first 5 columns defensively.
    df = df.iloc[:, :5].copy()
    # muselsl's record.py applies time_correction so column 0 ("timestamps")
    # arrives in Unix-epoch seconds, matching our events.csv `t_unix` column.
    df.columns = ["t_unix"] + MUSE_CHANNELS
    df = df.dropna(subset=["t_unix"]).reset_index(drop=True)
    return df


def bandpass_filter(signal: np.ndarray, sr: float,
                    lo: float = 1.0, hi: float = 45.0, order: int = 4) -> np.ndarray:
    """4th-order Butterworth, zero-phase via filtfilt. 1-45 Hz is the standard
    EEG band for task-related analyses — removes DC drift below 1 Hz and
    line-noise above 45 Hz."""
    nyq = sr / 2
    b, a = butter(order, [lo / nyq, hi / nyq], btype="band")
    return filtfilt(b, a, signal, axis=0)


def bandpower(signal: np.ndarray, sr: float, band: tuple[float, float]) -> float:
    """Mean PSD within the band using Welch. 2s windows (nperseg=int(2*sr))
    give ~0.5 Hz resolution — good enough to separate theta/alpha/beta."""
    nperseg = min(int(2 * sr), len(signal))
    freqs, psd = welch(signal, sr, nperseg=nperseg)
    lo, hi = band
    mask = (freqs >= lo) & (freqs < hi)
    return float(np.trapezoid(psd[mask], freqs[mask]))


def trial_features(trial_eeg: np.ndarray) -> np.ndarray:
    """trial_eeg: (n_samples, 4) — order TP9, AF7, AF8, TP10.
    Returns (18,) feature vector."""
    # Filter first so all downstream bandpowers share the same pass-band
    # shaping.
    filtered = bandpass_filter(trial_eeg, SR)
    feats: list[float] = []
    # 4 channels × 4 bands = 16 features
    for ch in range(4):
        for band in BAND_NAMES:
            feats.append(bandpower(filtered[:, ch], SR, BANDS[band]))
    # Frontal asymmetry: right minus left in log-alpha space.
    alpha_af7 = bandpower(filtered[:, 1], SR, BANDS["alpha"])
    alpha_af8 = bandpower(filtered[:, 2], SR, BANDS["alpha"])
    # Tiny epsilon to avoid log(0) when the channel was flat.
    eps = 1e-12
    feats.append(float(np.log((alpha_af8 + eps) / (alpha_af7 + eps))))
    # Temporal asymmetry.
    alpha_tp9 = bandpower(filtered[:, 0], SR, BANDS["alpha"])
    alpha_tp10 = bandpower(filtered[:, 3], SR, BANDS["alpha"])
    feats.append(float(np.log((alpha_tp10 + eps) / (alpha_tp9 + eps))))
    return np.asarray(feats, dtype=np.float32)


def is_artefact(trial_eeg: np.ndarray) -> bool:
    """True if any channel's FILTERED peak-to-peak exceeds threshold.

    We filter before measuring because Muse 2 raw signals carry large DC
    offsets (±1000 µV is normal baseline) that aren't actually artefacts —
    they're just the reference mismatch. Real artefacts (blinks, jaw-clench,
    movement) survive the 1-45 Hz bandpass.
    """
    filtered = bandpass_filter(trial_eeg, SR)
    pp = filtered.max(axis=0) - filtered.min(axis=0)
    return bool(np.any(pp > REJECT_PP_UV))


def slice_trial(df: pd.DataFrame, t_start: float, t_end: float) -> np.ndarray:
    """Return (n, 4) EEG samples with t_unix in [t_start, t_end].
    Both bounds are Unix epoch seconds: muselsl writes Unix timestamps in
    eeg.csv, and events.csv's t_unix is the same domain."""
    mask = (df["t_unix"] >= t_start) & (df["t_unix"] < t_end)
    return df.loc[mask, MUSE_CHANNELS].to_numpy()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("site_dir", type=Path)
    args = ap.parse_args()
    site_dir: Path = args.site_dir

    # Load data.
    events = pd.read_csv(site_dir / "events.csv")
    eeg_csv = site_dir / "eeg.csv"  # stage 2 writes .csv despite the --filename .fif hint
    df = load_eeg_csv(eeg_csv)

    print(
        f"[eeg] {len(df)} samples over "
        f"{df['t_unix'].iloc[-1] - df['t_unix'].iloc[0]:.1f}s",
        file=sys.stderr,
    )

    # Pair each stim_on with the matching stim_off. They share trial_idx.
    stim_ons = events[events["event_name"] == "stim_on"].sort_values("trial_idx")
    stim_offs = events[events["event_name"] == "stim_off"].set_index("trial_idx")

    by_screenshot: dict[int, list[np.ndarray]] = {}
    rejected = 0
    total = 0

    for _, row in stim_ons.iterrows():
        trial_idx = int(row["trial_idx"])
        if trial_idx not in stim_offs.index:
            print(f"[eeg] trial {trial_idx} has stim_on but no stim_off — skipping",
                  file=sys.stderr)
            continue
        # Both events.csv and muselsl's eeg.csv use Unix-epoch seconds.
        t0 = float(row["t_unix"])
        t1 = float(stim_offs.at[trial_idx, "t_unix"])
        shot = int(row["screenshot_idx"])

        trial_eeg = slice_trial(df, t0, t1)
        total += 1

        # Welch PSD needs a couple of seconds to estimate reliably. 3s × 256
        # Hz = 768 samples is our hard floor; the recorder sometimes starts
        # slightly late on trial 0, losing the first ~1.5s.
        if trial_eeg.shape[0] < 768:
            print(f"[eeg] trial {trial_idx} short ({trial_eeg.shape[0]} samples) — reject",
                  file=sys.stderr)
            rejected += 1
            continue

        if is_artefact(trial_eeg):
            pp = trial_eeg.max(axis=0) - trial_eeg.min(axis=0)
            print(f"[eeg] trial {trial_idx} artefact (pp={pp.max():.0f}µV) — reject",
                  file=sys.stderr)
            rejected += 1
            continue

        feat = trial_features(trial_eeg)
        by_screenshot.setdefault(shot, []).append(feat)

    # Average per screenshot.
    manifest = json.loads((site_dir / "manifest.json").read_text())
    n_shots = manifest["n_screenshots"]
    final = np.zeros((n_shots, 18), dtype=np.float32)

    missing: list[int] = []
    for shot in range(1, n_shots + 1):
        trials = by_screenshot.get(shot, [])
        if not trials:
            missing.append(shot)
            continue
        final[shot - 1] = np.mean(np.stack(trials, axis=0), axis=0)

    if missing:
        raise SystemExit(
            f"[eeg] screenshot(s) {missing} have ZERO usable trials. "
            f"Cannot produce a complete feature matrix for RSA."
        )

    out = site_dir / "muse_features.npz"
    meta = {
        "n_screenshots": n_shots,
        "feature_dim": final.shape[1],
        "total_trials": total,
        "rejected_trials": rejected,
        "accepted_per_screenshot": {
            str(s): len(by_screenshot.get(s, [])) for s in range(1, n_shots + 1)
        },
        "ts_unix": time.time(),
    }
    np.savez(out, features=final, meta=json.dumps(meta))
    print(f"\n✓ {final.shape} → {out.name} "
          f"({rejected}/{total} trials rejected)")


if __name__ == "__main__":
    main()
