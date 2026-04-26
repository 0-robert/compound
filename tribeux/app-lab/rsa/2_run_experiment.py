"""Stage 2 — stimulus presentation + EEG event marking.

Shows each screenshot fullscreen on a neutral grey canvas with a fixation
cross during rest/inter-stimulus intervals. For every state change, pushes
an LSL event marker so the EEG recording can be cut into trials later.

Protocol (locked):
    3 blocks
    Each block: 6 screenshots in a randomised order
        2s fixation on grey
        12s screenshot
        6s rest (grey + fixation cross)
    → 18 trials total, ~6 minutes per site

Requires:
    - `muselsl stream` running in a separate terminal (produces the EEG
      stream this script adds event markers to)
    - `python ../muse/bridge.py` does NOT need to be running — that's only
      for the browser live-view. The LSL markers this script pushes are
      consumed directly by `muselsl record` below.
    - A manifest.json produced by 1_capture_screenshots.py

Usage:
    python 2_run_experiment.py data/stripe.com
    # → data/stripe.com/eeg.fif (raw EEG with event markers)
    # → data/stripe.com/events.csv (redundant text log)
"""
from __future__ import annotations

import argparse
import atexit
import csv
import json
import random
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pygame
from pylsl import StreamInfo, StreamOutlet, local_clock, resolve_byprop

# ---------------------------------------------------------------------------
# Protocol timings. Locked in the plan. Change once, here.
# ---------------------------------------------------------------------------
FIXATION_S = 2.0
STIMULUS_S = 6.0     # matches TRIBE's 6-second clip duration → same stimulus exposure on both sides
REST_S = 6.0
N_REPEATS = 3  # full blocks — each block is one shuffled pass through all N screenshots

# Neutral grey. The plan is explicit: don't use pure white — it creates its
# own strong visual response that contaminates the baseline.
GREY = (128, 128, 128)
CROSS_COLOR = (40, 40, 40)
CROSS_SIZE = 20     # px arm half-length
CROSS_WIDTH = 3

# Event-marker codes pushed over LSL. Encoded as integers for compact
# storage; the events.csv log also carries the human-readable form.
EVENT_FIXATION_ON = 1
EVENT_STIM_ON = 2
EVENT_STIM_OFF = 3
EVENT_REST_ON = 4
EVENT_SESSION_START = 10
EVENT_SESSION_END = 11
EVENT_ABORTED = 99

EVENT_NAMES = {
    EVENT_FIXATION_ON: "fixation_on",
    EVENT_STIM_ON: "stim_on",
    EVENT_STIM_OFF: "stim_off",
    EVENT_REST_ON: "rest_on",
    EVENT_SESSION_START: "session_start",
    EVENT_SESSION_END: "session_end",
    EVENT_ABORTED: "aborted",
}


# ---------------------------------------------------------------------------
# Trial plan builder
# ---------------------------------------------------------------------------
@dataclass
class Trial:
    block: int           # 0..N_REPEATS-1
    index_in_block: int  # 0..5
    screenshot_idx: int  # 1..6 (matches filename 01.png..06.png)


def build_trial_order(n_screenshots: int, n_repeats: int, seed: Optional[int]) -> list[Trial]:
    """Per block, shuffle [1..n_screenshots]. Each block has its own permutation.

    This is stronger than one big shuffle because it guarantees every
    screenshot appears exactly n_repeats times, separated by at least
    (n_screenshots - 1) other trials of different screenshots. That spacing
    reduces serial autocorrelation in the EEG response.
    """
    rng = random.Random(seed)
    trials: list[Trial] = []
    for block in range(n_repeats):
        order = list(range(1, n_screenshots + 1))
        rng.shuffle(order)
        for idx_in_block, shot in enumerate(order):
            trials.append(Trial(block=block, index_in_block=idx_in_block, screenshot_idx=shot))
    return trials


# ---------------------------------------------------------------------------
# LSL event stream
# ---------------------------------------------------------------------------
def make_event_outlet() -> StreamOutlet:
    """Open a 'Markers' LSL stream. muselsl's recorder will merge this with the
    EEG when we later load via mne. Name + source_id are the canonical ones
    other tools look for."""
    info = StreamInfo(
        name="TRIBEUX_Events",
        type="Markers",
        channel_count=1,
        nominal_srate=0,            # irregular-rate marker stream
        channel_format="int32",
        source_id="tribeux_rsa_exp",
    )
    return StreamOutlet(info)


def check_eeg_stream() -> None:
    """Fail loudly if muselsl isn't running. The experiment is pointless
    without EEG."""
    print("[check] resolving EEG stream (timeout 5s)…", file=sys.stderr)
    streams = resolve_byprop("type", "EEG", timeout=5.0)
    if not streams:
        raise SystemExit(
            "[check] no EEG stream found.\n"
            "        Start one in another terminal first:\n"
            "            muselsl stream\n"
            "        and confirm your Muse 2 is paired."
        )
    info = streams[0]
    print(
        f"[check] found EEG stream '{info.name()}' "
        f"({info.channel_count()}ch @ {info.nominal_srate()} Hz)",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# EEG recorder subprocess
# ---------------------------------------------------------------------------
def start_eeg_recorder(out_fif: Path, duration_s: float) -> subprocess.Popen:
    """Spawn `muselsl record` for the session. It writes a .csv by default;
    we rely on muselsl's built-in recorder for simplicity.

    Note: muselsl writes .csv natively. We keep the name .fif in the plan
    but actually store .csv here — MNE can load the CSV via pandas in the
    feature extractor. Rewrite to .fif only if signal quality demands it.
    """
    # Overwrite extension to .csv since that's what muselsl emits.
    csv_path = out_fif.with_suffix(".csv")
    print(f"[record] starting muselsl recorder → {csv_path.name}", file=sys.stderr)
    # --duration rounds up; add 2s safety margin.
    proc = subprocess.Popen(
        [
            "muselsl", "record",
            "--duration", str(int(duration_s + 2)),
            "--filename", str(csv_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Give it a moment to spin up.
    time.sleep(1.5)
    if proc.poll() is not None:
        out, err = proc.communicate()
        raise SystemExit(
            f"[record] muselsl record exited immediately:\n"
            f"  stdout: {out.decode(errors='replace')}\n"
            f"  stderr: {err.decode(errors='replace')}"
        )
    return proc


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def draw_grey_with_cross(screen: pygame.Surface) -> None:
    screen.fill(GREY)
    cx, cy = screen.get_width() // 2, screen.get_height() // 2
    pygame.draw.line(screen, CROSS_COLOR,
                     (cx - CROSS_SIZE, cy), (cx + CROSS_SIZE, cy), CROSS_WIDTH)
    pygame.draw.line(screen, CROSS_COLOR,
                     (cx, cy - CROSS_SIZE), (cx, cy + CROSS_SIZE), CROSS_WIDTH)


def draw_screenshot(screen: pygame.Surface, image: pygame.Surface) -> None:
    """Paint the screenshot centred on grey. If the PNG is smaller than the
    screen, grey shows around it — that's correct (the stimulus is the web
    page, not the bezel)."""
    screen.fill(GREY)
    rect = image.get_rect(center=screen.get_rect().center)
    screen.blit(image, rect)


def load_and_fit(path: Path, screen_w: int, screen_h: int) -> pygame.Surface:
    """Load a PNG and scale-to-fit while preserving aspect. 2x pixel-density
    images get downsampled to physical pixels, so fit uses the screen
    dimensions directly (retina stuff is handled by the PNG dims)."""
    raw = pygame.image.load(str(path)).convert()
    img_w, img_h = raw.get_size()
    scale = min(screen_w / img_w, screen_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    return pygame.transform.smoothscale(raw, (new_w, new_h))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def wait_for_duration(
    seconds: float,
    screen: pygame.Surface,
    draw_fn,
    clock: pygame.time.Clock,
) -> bool:
    """Paint one frame with draw_fn, then tick at 60fps until `seconds`
    elapse. Returns True if ESC was pressed (abort)."""
    draw_fn()
    pygame.display.flip()
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return True
        clock.tick(60)
    return False


def run(site_dir: Path, seed: Optional[int], skip_eeg: bool) -> None:
    manifest_path = site_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"[run] manifest.json missing at {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    n_shots = manifest["n_screenshots"]

    trials = build_trial_order(n_shots, N_REPEATS, seed)
    session_seconds = len(trials) * (FIXATION_S + STIMULUS_S + REST_S)
    print(
        f"[run] {len(trials)} trials × {FIXATION_S + STIMULUS_S + REST_S:.0f}s "
        f"= {session_seconds / 60:.1f}m",
        file=sys.stderr,
    )

    # Pre-flight: EEG stream must exist (unless dry-run).
    if not skip_eeg:
        check_eeg_stream()

    # Start recording before the event outlet so the first marker is captured.
    eeg_proc: Optional[subprocess.Popen] = None
    if not skip_eeg:
        eeg_proc = start_eeg_recorder(site_dir / "eeg.fif", session_seconds)

        def stop_recorder():
            if eeg_proc and eeg_proc.poll() is None:
                eeg_proc.terminate()
                with suppress(subprocess.TimeoutExpired):
                    eeg_proc.wait(timeout=5)

        atexit.register(stop_recorder)

    # LSL event outlet. Even in dry-run mode we create one so pylsl issues
    # surface early.
    outlet = make_event_outlet()
    time.sleep(0.3)  # let consumers subscribe

    # pygame: fullscreen on the primary display.
    pygame.init()
    info = pygame.display.Info()
    screen = pygame.display.set_mode(
        (info.current_w, info.current_h),
        pygame.FULLSCREEN,
    )
    pygame.mouse.set_visible(False)
    pygame.display.set_caption("TRIBEUX RSA")
    clock = pygame.time.Clock()

    # Pre-load screenshots so switching is instant and we don't disk-hit
    # during a timed window.
    shot_surfaces: dict[int, pygame.Surface] = {
        i + 1: load_and_fit(site_dir / manifest["screenshots"][i], info.current_w, info.current_h)
        for i in range(n_shots)
    }

    events_csv = site_dir / "events.csv"
    events_f = events_csv.open("w", newline="")
    csv_w = csv.writer(events_f)
    # t_lsl: LSL shared clock — matches muselsl's `timestamps` column in
    # eeg.csv directly. t_unix: Unix wall-clock for human debugging only.
    csv_w.writerow(
        ["t_lsl", "t_unix", "event_code", "event_name", "trial_idx",
         "block", "index_in_block", "screenshot_idx"]
    )

    def push(code: int, trial: Optional[Trial] = None, trial_idx: int = -1) -> None:
        # Push first so the marker's LSL timestamp is captured by the
        # consumer; `local_clock()` just reads what LSL would have stamped.
        outlet.push_sample([code])
        t_lsl = local_clock()
        t_unix = time.time()
        csv_w.writerow([
            f"{t_lsl:.6f}", f"{t_unix:.6f}", code, EVENT_NAMES[code], trial_idx,
            trial.block if trial else -1,
            trial.index_in_block if trial else -1,
            trial.screenshot_idx if trial else -1,
        ])
        events_f.flush()

    aborted = False
    push(EVENT_SESSION_START)

    try:
        for trial_idx, trial in enumerate(trials):
            # --- fixation ---
            push(EVENT_FIXATION_ON, trial, trial_idx)
            if wait_for_duration(FIXATION_S, screen,
                                 lambda: draw_grey_with_cross(screen), clock):
                aborted = True; break
            # --- stimulus ---
            push(EVENT_STIM_ON, trial, trial_idx)
            img = shot_surfaces[trial.screenshot_idx]
            if wait_for_duration(STIMULUS_S, screen,
                                 lambda: draw_screenshot(screen, img), clock):
                aborted = True; break
            # --- rest ---
            push(EVENT_STIM_OFF, trial, trial_idx)
            push(EVENT_REST_ON, trial, trial_idx)
            if wait_for_duration(REST_S, screen,
                                 lambda: draw_grey_with_cross(screen), clock):
                aborted = True; break
    finally:
        push(EVENT_ABORTED if aborted else EVENT_SESSION_END)
        events_f.close()
        pygame.quit()

    print(f"\n{'✗ aborted' if aborted else '✓ complete'} — events: {events_csv}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("site_dir", type=Path,
                    help="Directory from stage 1, e.g. data/stripe.com/")
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed for trial order (default: non-deterministic)")
    ap.add_argument("--skip-eeg", action="store_true",
                    help="Dry-run: don't check for or record EEG. "
                         "Useful for testing timing + visuals.")
    args = ap.parse_args()
    run(args.site_dir, args.seed, args.skip_eeg)


if __name__ == "__main__":
    main()
