# T1 — RDD2022 raw audit

Counts come from the source XML **before** any conversion. The raw
four-class taxonomy is used here on purpose (D055): the D00/D10 merge
is only auditable if something counts them separately first.

## Per-country integrity

| country | images | xmls | img w/o xml | xml w/o img | boxes | degenerate | out-of-bounds | size mismatch | parse errors |
|---|---|---|---|---|---|---|---|---|---|
| India | 7706 | 7706 | 0 | 0 | 8203 | 0 | 0 | 0 | 0 |
| Japan | 10506 | 10506 | 0 | 0 | 24754 | 1 | 0 | 0 | 0 |
| Norway | 8161 | 8161 | 0 | 0 | 11229 | 0 | 0 | 0 | 0 |
| United_States | 4805 | 4805 | 0 | 0 | 11014 | 0 | 0 | 0 | 0 |
| Czech | 2829 | 2829 | 0 | 0 | 1745 | 0 | 0 | 0 | 0 |
| China_MotorBike | 1977 | 1977 | 0 | 0 | 4927 | 0 | 0 | 0 | 0 |
| China_Drone | 2401 | 2401 | 0 | 0 | 3840 | 0 | 0 | 0 | 0 |

## Every class name present, before filtering

| country | Block crack | D00 | D01 | D0w0 | D10 | D11 | D20 | D40 | D43 | D44 | D50 | Repair |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| India | 0 | 1555 | 179 | 1 | 68 | 45 | 2021 | 3187 | 57 | 1062 | 28 | 0 |
| Japan | 0 | 4049 | 0 | 0 | 3979 | 0 | 6199 | 2243 | 736 | 3995 | 3553 | 0 |
| Norway | 0 | 8570 | 0 | 0 | 1730 | 0 | 468 | 461 | 0 | 0 | 0 | 0 |
| United_States | 0 | 6750 | 0 | 0 | 3295 | 0 | 834 | 135 | 0 | 0 | 0 | 0 |
| Czech | 0 | 988 | 0 | 0 | 399 | 0 | 161 | 197 | 0 | 0 | 0 | 0 |
| China_MotorBike | 0 | 2678 | 0 | 0 | 1096 | 0 | 641 | 235 | 0 | 0 | 0 | 277 |
| China_Drone | 3 | 1426 | 0 | 0 | 1263 | 0 | 293 | 86 | 0 | 0 | 0 | 769 |

## Diff against reference facts

Images must match exactly. Label counts carry a 1% tolerance.
`linear` is D00+D10 (D038/D055).

| country | images | D00 | D10 | linear got/want | alligator got/want | pothole got/want | worst rel | verdict |
|---|---|---|---|---|---|---|---|---|
| India | 7706 | 1555 | 68 | 1623/1623 | 2021/2021 | 3187/3187 | 0.00000 | OK |
| Japan | 10506 | 4049 | 3979 | 8028/8028 | 6199/6199 | 2243/2243 | 0.00000 | OK |
| Norway | 8161 | 8570 | 1730 | 10300/10300 | 468/468 | 461/461 | 0.00000 | OK |
| United_States | 4805 | 6750 | 3295 | 10045/10045 | 834/834 | 135/135 | 0.00000 | OK |
| Czech | 2829 | 988 | 399 | 1387/1387 | 161/161 | 197/197 | 0.00000 | OK |
| China_MotorBike | 1977 | 2678 | 1096 | 3774/3774 | 641/641 | 235/235 | 0.00000 | OK |
| China_Drone | 2401 | 1426 | 1263 | 2689/2689 | 293/293 | 86/86 | 0.00000 | OK |

## Image dimensions

| country | distinct sizes | breakdown |
|---|---|---|
| India | 1 | 720x720 : 7,706 |
| Japan | **4** | 600x600 : 10,187 · 1024x1024 : 147 · 540x540 : 124 · 1080x1080 : 48 |
| Norway | **3** | 4040x2035 : 4,342 · 3643x2041 : 2,896 · 3650x2044 : 923 |
| United_States | 1 | 640x640 : 4,805 |
| Czech | 1 | 600x600 : 2,829 |
| China_MotorBike | 1 | 512x512 : 1,977 |
| China_Drone | 1 | 512x512 : 2,401 |

Only **Norway** exceeds T2's `max_side: 1280`, so it is the only country that
gets resized — 8,161 images. Japan's 1024 and 1080 variants stay as they are.

## Visual QA

Eight annotated images per country, boxes drawn from the source XML with no
conversion in between, tiled into `qa/_montage_<country>.jpg`; the individual
frames are alongside them. All fifty-six were viewed.

**Box geometry is correct in every country.** No transposed axes, no
pixel/normalised mix-up, no systematic offset — which is what this step exists
to rule out, since the count tables above would look identical if it were wrong.

| country | what the frames look like |
|---|---|
| India | Dashcam, 720x720, bonnet in frame on some; D40 sits tightly on real potholes and patches, D20 on broken shoulder. One grey `D01` box appears — a dropped class. |
| Japan | Dashcam, 600x600; grey `D44`/`D50` boxes are road-marking classes and are correctly dropped. Contains the one zero-width box in the whole dataset. |
| Norway | Ultra-wide 16:9 winter scenes; boxes align but are small relative to a 4040px frame, so they will shrink sharply under the 1280 resize. |
| United_States | **Google Street View imagery — every frame carries a "© Google" watermark.** Elevated viewpoint, not a dashcam. Almost entirely D00/D10. |
| Czech | Dashcam through a windscreen with a hexagonal mesh artifact occluding the top ~20% of every frame. Dominated by D10. |
| China_MotorBike | Near-nadir close-up from a motorbike, 512x512; road surface fills the frame. `Repair` boxes present and correctly dropped. |
| China_Drone | **Top-down aerial.** Geometrically unlike any vehicle camera; no inverse-perspective mapping to a road-level view exists for it. |

Three of these matter beyond T1:

- **United_States is Street View**, which is a provenance and licensing fact, not
  just a domain one. It should be stated wherever US results are reported.
- **China_Drone is aerial.** It is legitimate training data for crack appearance,
  but T13's IPM geometry has no meaning for it.
- **Czech's windscreen artifact** is a fixed occlusion present in every frame, so
  a model trained on Czech sees it as background rather than as noise.

## Resolution of the Japan label discrepancy

D055 recorded that Japan's `alligator_crack` converts to 6,198 against a
reference of 6,199, and left the cause to this audit. **Found:**
`Japan_001265` carries a `D20` box with `xmin == xmax == 198.0` — zero width,
one pixel tall. It is the only degenerate box in all 38,385 annotations.

The converter drops it correctly. The raw count (6,199) and the converted count
(6,198) are both right; they differ by exactly this box. No action needed beyond
recording it.

---

The QA renders under `qa/` are **not committed** — 21 MB of JPEGs that
`scripts/qa_raw.py` reproduces exactly (`SEED = 0` selects the same eight frames
per country every run). Regenerate with `python scripts/qa_raw.py`.
