# RSA pipeline — Muse 2 EEG vs TRIBE v2 predictions

Validates TRIBE v2's cortical-response predictions against real EEG from the
same person watching the same stimuli, using Representational Similarity
Analysis.

Each stage runs independently and writes plain files. You can re-run any
stage without repeating earlier ones.

## Pipeline

```
1. capture_screenshots.py   URL → 6 PNGs + manifest.json
2. run_experiment.py        pygame + muselsl → eeg.csv + events.csv
3. run_tribe.py             POST screenshots → tribe_features.npz
4. extract_eeg_features.py  eeg.csv + events.csv → muse_features.npz
5. rsa.py                   muse + tribe features → report.json + plots
```

## Setup (one time)

```bash
cd tribeux/app-lab/rsa
pip install -r requirements.txt
playwright install chromium
```

Pair your Muse 2 over Bluetooth.

## Running the protocol per site

```bash
URL="https://stripe.com"

# 1. Capture stimuli
python 1_capture_screenshots.py "$URL"
# → data/stripe.com/screenshots/01.png .. 06.png
# → data/stripe.com/manifest.json

# 2. Run the experiment. Two terminals:
#    Terminal A:
muselsl stream
#    Terminal B (wait ~5s for LSL to advertise):
python 2_run_experiment.py data/stripe.com
# → data/stripe.com/eeg.csv, events.csv   (~6 min of recording)

# 3. Get TRIBE's predictions for the same stimuli.
#    Real endpoint (once the Colab notebook exposes ngrok):
export TRIBE_ENDPOINT="https://abc123.ngrok.io/predict"
python 3_run_tribe.py data/stripe.com
#    OR mock (for dev / before Colab is up):
python 3_run_tribe.py data/stripe.com --mock

# 4. Extract EEG features per screenshot
python 4_extract_eeg_features.py data/stripe.com
# → data/stripe.com/muse_features.npz  (6 × 18)

# 5. RSA
python 5_rsa.py data/stripe.com
# → data/stripe.com/report.json, rdm_muse.png, rdm_tribe.png, rdm_scatter.png
```

Repeat stages 1–5 for three sites total (plan locks n=3).

## Dry-run without the Muse

Stage 2 supports `--skip-eeg` to preview the stimulus presentation without
recording anything. Good for verifying timings and seeing what the fullscreen
stimulus looks like.

```bash
python 2_run_experiment.py data/stripe.com --skip-eeg --seed 42
# ESC to abort
```

Stages 4 and 5 need a real EEG recording. For smoke-testing stage 5 alone
you can write a synthetic `muse_features.npz` (see the identity test in
the build log).

## Protocol (locked)

Per site:

- 6 screenshots × 3 repeats = 18 trials, randomised within each of 3 blocks
- Each trial: 2s fixation → 12s stimulus → 6s rest on neutral grey
- ~6 minutes per site, ~20 minutes for the full 3-site design

Feature extraction:

- Muse: theta / alpha / beta / gamma bandpower × 4 channels + 2 asymmetry
  indices = 18 features per screenshot (averaged across 3 trial repeats)
- TRIBE: whatever activation vector the model emits (D = 115 in mock)

RSA:

- RDM per system = 1 − pairwise correlation, (6×6) per site
- Spearman on upper-triangle vectors (15 pairs per site)
- Permutation test: 1000 shuffles of screenshot labels on the TRIBE side
- Output: `r`, `p_parametric`, `p_permutation`

## File layout

```
rsa/
├── 1_..5_*.py                 pipeline stages
├── data/{site_slug}/          everything for one site
│   ├── screenshots/01..06.png
│   ├── manifest.json
│   ├── eeg.csv                (from stage 2)
│   ├── events.csv             (from stage 2)
│   ├── tribe_features.npz     (from stage 3)
│   ├── muse_features.npz      (from stage 4)
│   ├── report.json            (from stage 5)
│   └── rdm_{muse,tribe,scatter}.png
└── requirements.txt
```

## Known risks (from the plan)

1. **Low r doesn't mean TRIBE is wrong** — Muse 2 is 4 scalp electrodes;
   TRIBE predicts whole-cortex fMRI. Report honestly; don't cherry-pick.
2. **TRIBE endpoint availability** — `3_run_tribe.py` caches; re-runs only
   if the .npz is missing or `--force` is passed.
3. **EEG artefacts** — trials exceeding ±500 µV peak-to-peak are rejected.
   With 3 repeats per screenshot there's headroom; if all 3 are lost for
   one screenshot, stage 4 errors out.
4. **6 points → 15 pairs per site** — limited power. Pool across 3 sites
   for the aggregate r over 18 screenshots / 153 pairs. See the planned
   `6_aggregate.py` (TODO).
