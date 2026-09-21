# T1 — findings

Authored companion to `raw_audit.md`, which is generated and overwritten on
every run of `scripts/audit_raw.py`.

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

Only **Norway** exceeds T2's `max_side: 1280`, so it is the only country T2
resizes — 8,161 images. Confirmed in T2: `resized: {'Norway': 8161}`.

## Visual QA

Eight annotated images per country, boxes drawn from the source XML with no
conversion in between, tiled into `qa/_montage_<country>.jpg`. All fifty-six
were viewed.

**Box geometry is correct in every country.** No transposed axes, no
pixel/normalised mix-up, no systematic offset — which is what this step exists to
rule out, since the count tables would look identical if it were wrong.

| country | what the frames look like |
|---|---|
| India | Dashcam, 720x720, bonnet in frame on some; D40 sits tightly on real potholes and patches, D20 on broken shoulder. One grey `D01` box appears — a dropped class. |
| Japan | Dashcam, 600x600; grey `D44`/`D50` boxes are road-marking classes, correctly dropped. Contains the one zero-width box in the whole dataset. |
| Norway | Ultra-wide 16:9 winter scenes; boxes align but are small relative to a 4040px frame, so they shrink sharply under the 1280 resize. |
| United_States | **Google Street View imagery — every frame carries a "© Google" watermark.** Elevated viewpoint, not a dashcam. Almost entirely D00/D10. |
| Czech | Dashcam through a windscreen with a hexagonal mesh artifact occluding the top ~20% of every frame. Dominated by D10. |
| China_MotorBike | Near-nadir close-up from a motorbike, 512x512; road surface fills the frame. `Repair` boxes present and correctly dropped. |
| China_Drone | **Top-down aerial.** Geometrically unlike any vehicle camera; no inverse-perspective mapping to a road-level view exists for it. |

Three of these matter beyond T1:

- **United_States is Street View** — a provenance and licensing fact, not just a
  domain one. State it wherever US results are reported.
- **China_Drone is aerial.** Legitimate training data for crack appearance, but
  T13's IPM geometry has no meaning for it.
- **Czech's windscreen artifact** is a fixed occlusion in every frame, so a model
  trained on Czech sees it as background rather than as noise.

## Resolution of the Japan label discrepancy

D055 recorded that Japan's `alligator_crack` converts to 6,198 against a
reference of 6,199, and left the cause to this audit. **Found:**

```
Japan_001265   D20   xmin=198.0 ymin=474.0 xmax=198.0 ymax=475.0   (width 0)
```

Zero width, one pixel tall — the only degenerate box in all 38,385 annotations.
The converter drops it correctly. Raw 6,199 and converted 6,198 are both right
and differ by exactly this box. T2 independently reproduced it:
`rejected_boxes: {"degenerate_box": 1}`.

No action needed beyond recording it.

## Note on the QA renders

`qa/` is gitignored — 21 MB of JPEGs that `scripts/qa_raw.py` reproduces exactly
(`SEED = 0` picks the same eight frames per country every run).
