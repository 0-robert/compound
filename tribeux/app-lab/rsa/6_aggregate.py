"""Stage 6 — cross-site aggregate RSA.

Concatenates the per-site feature matrices across multiple sites and runs
RSA on the pooled data. With 3 sites × 6 screenshots = 18 rows, the RDM has
153 upper-triangle pairs vs only 15 per site — so the aggregate gives us
real statistical power.

Output:
    data/aggregate/report.json         pooled r, p, per-site r for context
    data/aggregate/rdm_muse.png        18×18 heatmap, grouped by site
    data/aggregate/rdm_tribe.png       18×18 heatmap
    data/aggregate/rdm_scatter.png     153-point scatter
    data/aggregate/per_site_bars.png   per-site r side-by-side

Usage:
    python 6_aggregate.py data/stripe.com data/airbnb.com data/linear.app
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import spearmanr

# Reuse the exact same math as stage 5 — importing avoids drift between
# the two reports.
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "rsa", Path(__file__).with_name("5_rsa.py")
)
_rsa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rsa)

rdm_from_features = _rsa.rdm_from_features
upper_tri = _rsa.upper_tri
permutation_p = _rsa.permutation_p


def load_site(site_dir: Path) -> tuple[np.ndarray, np.ndarray, str]:
    """Returns (muse_feats, tribe_feats, site_label). Fails loudly if any
    required file is missing — cross-site analysis is all-or-nothing, we
    don't silently drop sites."""
    muse = np.load(site_dir / "muse_features.npz", allow_pickle=True)["features"]
    tribe = np.load(site_dir / "tribe_features.npz", allow_pickle=True)["features"]
    manifest = json.loads((site_dir / "manifest.json").read_text())
    label = manifest.get("url", site_dir.name)
    if muse.shape[0] != tribe.shape[0]:
        raise SystemExit(
            f"[agg] {site_dir.name}: Muse has {muse.shape[0]} rows, "
            f"TRIBE has {tribe.shape[0]}. Aborting."
        )
    return muse, tribe, label


def plot_grouped_rdm(
    rdm: np.ndarray,
    title: str,
    out_path: Path,
    site_boundaries: list[int],
    site_labels: list[str],
) -> None:
    """RDM with divider lines between sites so it's obvious which block is
    which. site_boundaries is cumulative screenshot counts; site_labels[i]
    belongs to the block ending at site_boundaries[i]."""
    fig, ax = plt.subplots(figsize=(5.2, 5))
    im = ax.imshow(rdm, cmap="magma", vmin=0, vmax=2)

    # Thin white lines between sites.
    for b in site_boundaries[:-1]:
        ax.axhline(b - 0.5, color="white", linewidth=1.2)
        ax.axvline(b - 0.5, color="white", linewidth=1.2)

    # Site labels at midpoints of each block.
    midpoints = []
    prev = 0
    for b in site_boundaries:
        midpoints.append((prev + b - 1) / 2)
        prev = b
    ax.set_xticks(midpoints, site_labels, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(midpoints, site_labels, fontsize=9)

    ax.set_title(title)
    plt.colorbar(im, ax=ax, label="1 - corr")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def plot_scatter(rdm_a: np.ndarray, rdm_b: np.ndarray, r: float,
                 out_path: Path) -> None:
    a = upper_tri(rdm_a)
    b = upper_tri(rdm_b)
    fig, ax = plt.subplots(figsize=(4.8, 4.8))
    ax.scatter(a, b, alpha=0.5, s=20, edgecolors="none")
    ax.set_xlabel("Muse RDM (1 - corr)")
    ax.set_ylabel("TRIBE RDM (1 - corr)")
    ax.set_title(f"Aggregate — Spearman r = {r:+.3f}")
    ax.grid(True, linestyle=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def plot_per_site_bars(per_site: dict[str, float], aggregate_r: float,
                       out_path: Path) -> None:
    labels = list(per_site.keys())
    values = [per_site[l] for l in labels]
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    bars = ax.bar(labels, values, color="#444")
    ax.axhline(aggregate_r, color="#c33", linewidth=2,
               label=f"aggregate r = {aggregate_r:+.2f}")
    ax.axhline(0, color="black", linewidth=0.6, linestyle=":")
    ax.set_ylabel("Spearman r")
    ax.set_title("Per-site vs aggregate")
    ax.set_ylim(-1, 1)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + (0.03 if v >= 0 else -0.08),
                f"{v:+.2f}", ha="center", fontsize=9)
    ax.legend(loc="lower right", fontsize=9)
    plt.xticks(rotation=25, ha="right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("site_dirs", nargs="+", type=Path,
                    help="Site directories, e.g. data/stripe.com data/airbnb.com")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).parent / "data" / "aggregate")
    ap.add_argument("--permutations", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    muse_blocks: list[np.ndarray] = []
    tribe_blocks: list[np.ndarray] = []
    per_site_r: dict[str, float] = {}
    site_labels: list[str] = []
    site_boundaries: list[int] = []
    running = 0

    for site_dir in args.site_dirs:
        muse, tribe, label = load_site(site_dir)
        muse_blocks.append(muse)
        tribe_blocks.append(tribe)
        site_labels.append(label)
        running += muse.shape[0]
        site_boundaries.append(running)

        # Per-site r for context. Upper-tri of a 6×6 has 15 pairs — so the
        # per-site p is noisy, we report r only.
        r, _ = spearmanr(upper_tri(rdm_from_features(muse)),
                         upper_tri(rdm_from_features(tribe)))
        per_site_r[label] = float(r)
        print(f"[agg] {label}: n={muse.shape[0]}  r={r:+.3f}")

    # Stack → big feature matrices across all sites.
    muse_all = np.concatenate(muse_blocks, axis=0)
    tribe_all = np.concatenate(tribe_blocks, axis=0)

    rdm_muse = rdm_from_features(muse_all)
    rdm_tribe = rdm_from_features(tribe_all)

    r, p_param = spearmanr(upper_tri(rdm_muse), upper_tri(rdm_tribe))
    rng = np.random.default_rng(args.seed)
    p_perm = permutation_p(rdm_muse, rdm_tribe, r, args.permutations, rng)

    # Plots.
    plot_grouped_rdm(rdm_muse, "Muse RDM — aggregate",
                     args.out / "rdm_muse.png", site_boundaries, site_labels)
    plot_grouped_rdm(rdm_tribe, "TRIBE RDM — aggregate",
                     args.out / "rdm_tribe.png", site_boundaries, site_labels)
    plot_scatter(rdm_muse, rdm_tribe, r, args.out / "rdm_scatter.png")
    plot_per_site_bars(per_site_r, r, args.out / "per_site_bars.png")

    report = {
        "sites": site_labels,
        "n_total_screenshots": int(muse_all.shape[0]),
        "aggregate_spearman_r": float(r),
        "aggregate_p_parametric": float(p_param),
        "aggregate_p_permutation": p_perm,
        "per_site_r": per_site_r,
        "n_permutations": args.permutations,
        "muse_feature_dim": int(muse_all.shape[1]),
        "tribe_feature_dim": int(tribe_all.shape[1]),
        "ts_unix": time.time(),
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n{'═' * 52}")
    print(f" AGGREGATE over {len(site_labels)} sites "
          f"({muse_all.shape[0]} screenshots)")
    print(f" r     {r:+.3f}")
    print(f" p     {p_perm:.3f}  (permutation, n={args.permutations})")
    print(f" p     {p_param:.3f}  (parametric)")
    print(f"{'═' * 52}\n")
    print(f"Outputs in {args.out}:")
    print("  rdm_muse.png  rdm_tribe.png  rdm_scatter.png  per_site_bars.png  report.json")


if __name__ == "__main__":
    main()
