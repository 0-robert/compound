"""Stage 5 — Representational Similarity Analysis.

Compares two feature matrices (Muse EEG vs TRIBE predictions) in a
space-agnostic way: for each, compute the pairwise dissimilarity matrix
(RDM), then correlate the upper triangles.

Why this method: the two systems measure fundamentally different things.
Muse gives 4-channel scalp potentials; TRIBE predicts whole-cortex fMRI
activation. RSA sidesteps this — we never align the two in a common
physical space. Instead we ask: "Does screenshot 1 differ from screenshot
3 in the same way for Muse as it does for TRIBE?" The answer is a number
between -1 and 1.

Output:
    report.json         — headline numbers (r, p_perm, p_parametric)
    rdm_muse.png        — 6×6 heatmap
    rdm_tribe.png       — 6×6 heatmap
    rdm_scatter.png     — upper-triangle pairs

Usage:
    python 5_rsa.py data/stripe.com
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
from scipy.stats import spearmanr, zscore


N_PERMUTATIONS = 1000


def rdm_from_features(features: np.ndarray) -> np.ndarray:
    """1 - pearsonr between every pair of rows.

    features: (N, D). Returns (N, N) symmetric matrix, diagonal zero.

    Pearson over feature vectors (not voxels) is the standard choice —
    it's scale-invariant within each row, so differing magnitudes between
    Muse bandpower and TRIBE activations don't bias the distance.
    """
    # Row-wise z-score so corrcoef is well-defined even if one row happens
    # to be a constant (edge case — never hit in practice).
    feats = zscore(features, axis=1, nan_policy="raise")
    # corrcoef → (N, N) correlation matrix.
    corr = np.corrcoef(feats)
    return 1.0 - corr


def upper_tri(m: np.ndarray) -> np.ndarray:
    """Return the upper triangle as a 1-D vector (excludes diagonal)."""
    n = m.shape[0]
    iu = np.triu_indices(n, k=1)
    return m[iu]


def permutation_p(
    rdm_a: np.ndarray,
    rdm_b: np.ndarray,
    observed_r: float,
    n_permutations: int,
    rng: np.random.Generator,
) -> float:
    """Two-tailed? No — we test the alternative 'RDMs are MORE similar than
    chance', which is one-tailed. p = fraction of null r ≥ observed.

    We permute labels on ONE side (rows/cols of rdm_b) and recompute.
    This preserves RDM structure but destroys the label alignment between
    the two systems — the correct null.
    """
    n = rdm_b.shape[0]
    null_rs = np.empty(n_permutations, dtype=np.float64)
    for i in range(n_permutations):
        perm = rng.permutation(n)
        shuffled = rdm_b[perm][:, perm]
        r, _ = spearmanr(upper_tri(rdm_a), upper_tri(shuffled))
        null_rs[i] = r
    # Add 1 to numerator + denominator → Phipson & Smyth 2010.
    return float((1 + np.sum(null_rs >= observed_r)) / (1 + n_permutations))


def plot_rdm(rdm: np.ndarray, title: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(4.2, 4))
    im = ax.imshow(rdm, cmap="magma", vmin=0, vmax=2)
    n = rdm.shape[0]
    ax.set_xticks(range(n), [str(i + 1) for i in range(n)])
    ax.set_yticks(range(n), [str(i + 1) for i in range(n)])
    ax.set_xlabel("screenshot")
    ax.set_ylabel("screenshot")
    ax.set_title(title)
    plt.colorbar(im, ax=ax, label="1 - corr")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def plot_scatter(rdm_a: np.ndarray, rdm_b: np.ndarray, out_path: Path) -> None:
    a = upper_tri(rdm_a)
    b = upper_tri(rdm_b)
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.scatter(a, b, alpha=0.8, s=36, edgecolors="none")
    ax.set_xlabel("Muse RDM (1 - corr)")
    ax.set_ylabel("TRIBE RDM (1 - corr)")
    ax.set_title("Upper-triangle pairs")
    ax.grid(True, linestyle=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("site_dir", type=Path)
    ap.add_argument("--permutations", type=int, default=N_PERMUTATIONS)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    site_dir: Path = args.site_dir

    muse = np.load(site_dir / "muse_features.npz", allow_pickle=True)
    tribe = np.load(site_dir / "tribe_features.npz", allow_pickle=True)

    muse_feats = muse["features"]
    tribe_feats = tribe["features"]
    if muse_feats.shape[0] != tribe_feats.shape[0]:
        raise SystemExit(
            f"[rsa] row-count mismatch: Muse has {muse_feats.shape[0]} "
            f"screenshots, TRIBE has {tribe_feats.shape[0]}. "
            f"One of the stages failed."
        )

    rdm_muse = rdm_from_features(muse_feats)
    rdm_tribe = rdm_from_features(tribe_feats)

    r, p_param = spearmanr(upper_tri(rdm_muse), upper_tri(rdm_tribe))
    rng = np.random.default_rng(args.seed)
    p_perm = permutation_p(rdm_muse, rdm_tribe, r, args.permutations, rng)

    # Save artefacts.
    plot_rdm(rdm_muse, "Muse RDM", site_dir / "rdm_muse.png")
    plot_rdm(rdm_tribe, "TRIBE RDM", site_dir / "rdm_tribe.png")
    plot_scatter(rdm_muse, rdm_tribe, site_dir / "rdm_scatter.png")

    manifest = json.loads((site_dir / "manifest.json").read_text())
    report = {
        "site": manifest["url"],
        "n_screenshots": int(muse_feats.shape[0]),
        "spearman_r": float(r),
        "spearman_p_parametric": float(p_param),
        "spearman_p_permutation": p_perm,
        "n_permutations": int(args.permutations),
        "muse_feature_dim": int(muse_feats.shape[1]),
        "tribe_feature_dim": int(tribe_feats.shape[1]),
        "ts_unix": time.time(),
    }
    (site_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n{'═' * 52}")
    print(f" SITE  {report['site']}")
    print(f" r     {r:+.3f}")
    print(f" p     {p_perm:.3f}  (permutation, n={args.permutations})")
    print(f" p     {p_param:.3f}  (parametric)")
    print(f"{'═' * 52}\n")
    print(f"Plots saved: rdm_muse.png  rdm_tribe.png  rdm_scatter.png")
    print(f"Full report: report.json")


if __name__ == "__main__":
    main()
