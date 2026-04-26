"""Stage 1 — website screenshot capture.

Given a URL, produces 6 equally-spaced full-viewport screenshots covering the
entire scrollable page, plus a manifest.json that makes the capture fully
reproducible.

The screenshots become the stimuli for both:
  - the pygame experiment that shows them to the human (module 2)
  - the TRIBE runner that predicts cortical activation for each (module 3)

Because both sides consume the same PNG files with the same indices, there's
no stimulus-alignment problem downstream.

Usage:
    playwright install chromium   # one time
    python 1_capture_screenshots.py https://airbnb.com
    # → data/airbnb.com/screenshots/01.png .. 06.png
    # → data/airbnb.com/manifest.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

# Fixed across all sites — RSA needs the same number of rows per matrix so
# the pooled aggregate works. 3 screenshots gives a small but valid RDM
# (3 choose 2 = 3 pairs per site; enough to spot obvious pattern agreement
# when pooled across 3 sites = 9 screenshots = 36 pairs).
N_SCREENSHOTS = 3

# Desktop baseline. Change once, here, not in three places.
VIEWPORT_W = 1440
VIEWPORT_H = 900

# Wait for network idle plus a brief settle so CSS animations finish before
# we snap. Network-idle alone doesn't catch CSS animations or lazy-loaded
# imagery triggered by scroll.
SETTLE_MS = 600


def site_slug(url: str) -> str:
    """Turn a URL into a filesystem-safe directory name.

    Using the hostname keeps it human-readable. Strip www., trailing dots,
    and anything that's not a letter/digit/dot/dash.
    """
    host = urlparse(url).netloc or url
    host = re.sub(r"^www\.", "", host).lower()
    host = re.sub(r"[^a-z0-9.\-]", "_", host)
    return host or "site"


def capture(url: str, out_dir: Path) -> dict:
    """Navigate to url, take 6 viewport screenshots at evenly-spaced scroll
    positions, return a manifest dict.

    The scroll range is clamped: if the page is shorter than 6 viewports, all
    screenshots are collapsed to the visible portion (we DO NOT zoom out to
    fake length). That's honest — a short page just has 6 near-identical
    screenshots, and the RDM will reflect that.
    """
    shots_dir = out_dir / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    scroll_positions: list[int] = []
    captured_at = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=2,  # retina — sharper PNGs for the stimulus
        )
        page = context.new_page()

        print(f"[capture] navigating to {url}", file=sys.stderr)
        page.goto(url, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(SETTLE_MS)

        # Full page height in CSS pixels. Re-query after a tiny scroll because
        # some pages (Airbnb, Stripe) only hydrate heavy content after the
        # first user interaction — an 80px scroll counts as that for most.
        page.evaluate("window.scrollTo({ top: 80, behavior: 'instant' })")
        page.wait_for_timeout(200)
        page.evaluate("window.scrollTo({ top: 0, behavior: 'instant' })")
        page.wait_for_timeout(200)

        page_height = page.evaluate("document.body.scrollHeight")
        max_scroll = max(0, page_height - VIEWPORT_H)
        print(
            f"[capture] page_height={page_height}px, max_scroll={max_scroll}px",
            file=sys.stderr,
        )

        for i in range(N_SCREENSHOTS):
            frac = i / (N_SCREENSHOTS - 1)  # 0, 0.2, 0.4, 0.6, 0.8, 1.0
            y = round(max_scroll * frac)
            scroll_positions.append(y)

            page.evaluate(f"window.scrollTo({{ top: {y}, behavior: 'instant' }})")
            # Let any IntersectionObservers fire.
            page.wait_for_timeout(250)

            out_path = shots_dir / f"{i + 1:02d}.png"
            page.screenshot(path=str(out_path), full_page=False)
            print(f"[capture] {out_path.name} @ y={y}px", file=sys.stderr)

        browser.close()

    return {
        "url": url,
        "captured_at_unix": captured_at,
        "n_screenshots": N_SCREENSHOTS,
        "viewport": {"w": VIEWPORT_W, "h": VIEWPORT_H},
        "device_scale_factor": 2,
        "page_height_px": page_height,
        "max_scroll_px": max_scroll,
        "scroll_positions_px": scroll_positions,
        "screenshots": [f"screenshots/{i + 1:02d}.png" for i in range(N_SCREENSHOTS)],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("url", help="Target URL, e.g. https://airbnb.com")
    ap.add_argument(
        "--out-root",
        type=Path,
        default=Path(__file__).parent / "data",
        help="Where to write data/{slug}/ (default: ./data/)",
    )
    args = ap.parse_args()

    url = args.url
    if not urlparse(url).scheme:
        url = "https://" + url

    slug = site_slug(url)
    out_dir = args.out_root / slug

    if out_dir.exists():
        print(
            f"[capture] {out_dir} already exists — overwriting screenshots",
            file=sys.stderr,
        )

    manifest = capture(url, out_dir)
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"\n✓ {manifest['n_screenshots']} screenshots → {out_dir}")
    print(f"  manifest: {manifest_path}")


if __name__ == "__main__":
    main()
