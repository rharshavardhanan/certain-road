# The MuJoCo survey demo

A live demonstration of the survey pipeline. A camera vehicle drives a seeded, simulated road
at 20 km/h. The real detectors find the damage, and the real survey code scores each 50 m
segment as the vehicle drives. The run ends on a result screen comparing the survey with the
road's ground truth. This is a demonstration, not T13's closed-loop simulation and not a
field result (D087).

## Run it

You need the trained weights under `models/` (the paths in `configs/eval/video.yaml`) and
the texture photos in `data/raw/trial_textures/`. Both are gitignored.

```bash
uv run python -m sim.mujoco.demo --preset poor --seed 0
```

It draws the road in **look v2**, with 3D potholes, surface marks and harsher light (D092).
`--look v1` runs the simulator exactly as it was at the `demo-v1` tag, as the fallback. This
opens one 1920×1080 window, drives the road and ends on the result screen, which stays
until a key is pressed. Esc or q during the drive stops it early.

| Flag | Effect |
|---|---|
| `--preset good\|moderate\|poor\|mixed\|random` | The kind of road. `random` draws from india_train's damage mix in `results/T2/split_audit.json` |
| `--seed N` | The same seed gives the same road, byte for byte |
| `--look v1\|v2` | v2 (default): 3D potholes, repair patches, oil stains, dust, trees and their shadows. v1: the `demo-v1` simulator, unchanged |
| `--record out.mp4` | Also records the screen in real time, then holds the result screen for 10 s |
| `--headless` | No window. With `--record`, renders a recording without a display |
| `--budget-frac 0.3` | Repair budget as a share of the cost of repairing every segment |
| `--end-only` | Redraws the result screen of an earlier run, without driving again |
| `--screenshot f.png --at 196` | One camera frame at 196 m along the road |

On the Jetson Orin Nano it runs on CUDA at about 0.2× real time, after a scene build of
about 220 s; `scripts/fetch_trial_textures.py` rebuilds the texture photos there from their
public sources (D094). On an Apple Silicon Mac the drive runs at about 0.6× real time: a 527 m road takes about
2.5 minutes. Each run writes these files to `runs/mujoco/<preset>_seed<seed>_v2/` (v1: no suffix):
`ground_truth.json`, `detections.jsonl` (every frame), `survey.json` (segments and the drift
trace), `drive_summary.json`, `end.json` and `end_screen.png`.

## What is real and what is simulated

| Real: the project's own code and models | Simulated |
|---|---|
| Model P (potholes) and Model B (cracks), never summed (D082) | The road, from a seeded generator with clustered damage |
| ByteTrack, and D075's 3-of-5 confirmation imported from `scripts/eval_video.py` | The surface, from CC BY photos at real-world sizes, with perspective and scene lighting |
| `core.geometry`'s IPM, which places boxes on the ground | The camera's motion blur, pitch and roll noise, sensor noise and JPEG |
| `certain_road.survey`: footprints, distress, deducts, vision-estimated PCI, bands and segments | The ground truth, which is exact because the road was generated |
| `certain_road.survey.allocation`: the optimiser and worst-first | |
| D078's drift martingale, fed exactly as `model.val` scored india_val | |

The simulator places, renders and counts. It does not score anything itself, and tests check
that its numbers are certain_road.survey's (`tests/test_mujoco_survey.py`,
`tests/test_mujoco_evaluate.py`).

## Reading the screens

**Live, top left: camera.** What the models saw. Boxes take the class colour, and turn green
once their track is confirmed. The dashed line is the 12 m gate. The outlined strip is D006's
survey ROI, the 5 m of the driving lane 3–8 m ahead, which lights up at each 5 m sample.

**Top right: survey map.** The road in plan, to scale along its length. Confirmed damage is
placed by the IPM. Each 50 m segment fills with its band colour when it completes.

**Bottom left: counters.** Distance, segments scored, confirmed tracks per class, and the
segment in progress so far.

**Bottom right: drift.** D078's CUSUM log-wealth for Model B against its india_val reference,
one point per sample, with the alarm threshold.

**Result screen.** Every segment's vision-estimated and reference PCI, and which segments each
plan repairs. Both plans are scored on D079's two objectives: the true benefit repaired, and
how many of the true worst 3 segments get repaired. Detection is scored against the ground
truth: recall per class, and false alarms per km.

## Known behaviour

These are results to report, not defects. None was tuned away.

- **The drift monitor fires on clean road (D089).** 97% of india_val frames contain damage.
  On a clean road B sees almost nothing, which looks unfamiliar against that bag. The monitor
  fires on low confidence, so a stretch getting worse pulls it down. The mixed preset's
  moment is therefore the caption announcing the drop in band.
- **Class confusion lowers the vision estimate (D089).** Model P fires on alligator patches,
  and B can label one crack both linear and alligator.
- **The reference PCI uses the same geometry as the estimate.** It is the ground truth
  projected into each sample and scored by the same code. A perfect detector reproduces it
  exactly.

## Results, seed 0

All five presets, driven headless on 2026-10-05. Every road is 527 m: at seed 0 every preset
draws the same length. Recall is the share of instances in view that a confirmed track of the
right class hit. "Benefit, worst 3" is each plan's true benefit and how many of the true worst
3 damaged segments it repairs, at a 30% budget.

| Preset | Pothole recall | Alligator recall | Linear recall | False alarms/km, pothole · alligator · linear | Drift alarm | Optimiser: benefit, worst 3 | Worst-first: benefit, worst 3 |
|---|---|---|---|---|---|---|---|
| good | no instance | no instance | 0 of 2 | 0 · 0 · 0 | 65 m | 0, no damaged segment | 0, no damaged segment |
| moderate | 1 of 3 | 2 of 2 | 9 of 17 | 11.7 · 3.9 · 0 | 65 m | 8, 2 of 3 | 8, 2 of 3 |
| poor | 16 of 28 | 22 of 24 | 14 of 27 | 35.1 · 7.8 · 0 | 150 m | 50, 1 of 3 | 58, 2 of 3 |
| mixed | 5 of 16 | 17 of 18 | 1 of 10 | 29.3 · 3.9 · 0 | 65 m | 48, 1 of 3 | 48, 1 of 3 |
| random | 5 of 13 | 11 of 12 | 1 of 13 | 29.3 · 1.9 · 0 | 145 m | 43, 2 of 3 | 35, 1 of 3 |

What the table shows:

- **Alligator cracks are found; potholes and linear cracks are found about half the time or
  less.** Most pothole false alarms are Model P firing on alligator patches.
- **The drift alarm comes early on every road.** On good, moderate and mixed it fires at 65 m,
  in the clean opening stretch, and nowhere near mixed's bad stretch (D089).
- **The mixed preset's bad stretch shows as a band drop.** Segments 7–9 score 66, 65 and 55,
  against references of 76, 83 and 69. Segment 7 falls from Good to Fair, so its caption
  reads "down from Good".
- **Neither plan wins everywhere.** The optimiser beats worst-first on random, loses on poor,
  and ties on moderate and mixed. The optimiser's advantage depends on the vision estimate
  ranking the segments correctly, and on poor it does not.

Two runs of poor, seed 0, gave identical ground truth, segments, drift trace and end-screen
numbers (D090). A recording of that run is `runs/mujoco/poor_seed0.mp4`: 102 s, 1920×1080.

## Look v2 against v1, seed 0

v2 changes how the road is drawn and lit, never the road: the ground truth is identical, so
the two compare directly. Measured once after v2 was built, and not adjusted afterwards.

| Preset | Pothole recall, v1 → v2 | Alligator recall | Linear recall | Pothole false alarms/km | Drift alarm |
|---|---|---|---|---|---|
| good | no instance | no instance | 0/2 → 0/2 | 0 → 0 | 65 → 80 m |
| moderate | 1/3 → 2/3 | 2/2 → 2/2 | 9/17 → 10/17 | 11.7 → 7.8 | 65 → 80 m |
| poor | 16/28 → 15/28 | 22/24 → 21/24 | 14/27 → 15/27 | 35.1 → 43.0 | 150 m → none |
| mixed | 5/16 → 8/16 | 17/18 → 17/18 | 1/10 → 1/10 | 29.3 → 37.1 | 65 → 80 m |
| random | 5/13 → 4/13 | 11/12 → 11/12 | 1/13 → 2/13 | 29.3 → 25.4 | 145 → 150 m |

- **Realism did not make potholes easier to find.** Pooled over the four damaged roads,
  pothole recall is 27/60 under v1 and 29/60 under v2. That is within what one run per preset
  can resolve.
- **The new marks raised no false alarm.** On poor and mixed, in both looks, every confirmed
  pothole track that matched no pothole sits on an alligator patch or a linear crack. None
  sits on a tree shadow, a repair patch, an oil stain or bare road.
- **The drift alarm still comes in the clean opening stretch** on good, moderate and mixed
  (D089).

A recording of poor under v2 is `runs/mujoco/poor_seed0_v2.mp4`.

## Credits

The road surface comes from two CC BY 4.0 datasets, and every render shows this credit
(`docs/texture-provenance.md`). They are not the project's own photos.

- **QR4Change**: Maske Y., Jakate S., Thakare C., Lokhande S. (2025). *Urban Civic Issues
  Image Dataset: Potholes and Garbage.* Mendeley Data V2, doi:10.17632/zndzygc3p3.2. Supplies
  the potholes.
- **BD-N6**: Hossain M.N., Aman N., Antor N.R., Tasnim N., Azam M.Z., et al. *Flexible
  Pavement Distress Image Dataset ... National Highway N6, Bangladesh,* Parts 1 and 2. Zenodo,
  doi:10.5281/zenodo.18072573 and doi:10.5281/zenodo.18114226. Supplies the cracks and the
  plain asphalt.
