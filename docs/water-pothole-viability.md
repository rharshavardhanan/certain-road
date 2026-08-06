# Water-pothole dataset — viability verdict

**Source:** Mendeley `tp95cdvgm8`, "An Annotated Water-Filled, and Dry Potholes Dataset
for Deep Learning Applications" (title per the Mendeley dataset page's own metadata —
see below), `Potholes.zip` (290,505,592 bytes, ≈291 MB)
**Assessed:** 2026-08-07
**Verdict:** NO-GO

## What ships

The archive contains more than the brief anticipated: alongside `IMG/`, `XML/`, `TXT/`
it also ships `ReadMe.txt` and two dashcam videos (`Dashcam-Front.mp4`,
`Dashcam-Rear.mp4`, faces/plates blurred per the Mendeley page description) not used in
this assessment.

| Directory | Contents | Count |
|---|---|---|
| `IMG/` | images (`.jpg`) | 713 |
| `XML/` | PASCAL VOC annotations | 713 |
| `TXT/` | YOLO annotations | 713 |

Image files are highly heterogeneous in geometry: 66 distinct `(width, height)` pairs
across 713 images. The single most common size, `(549, 412)`, accounts for only 151
images (21%); a large second cluster sits at `(392, 806)` (131 images, 18%), and the
long tail is single- or few-image dimensions ranging from `(232, 412)` up to
`(806, 412)`. File size ranges 19.7–504.7 KB (mean 137.2 KB, median 75.1 KB), total
95.5 MB across all 713 images. This spread — many distinct aspect ratios, a `412`-pixel
dimension recurring across dozens of otherwise-different sizes — is consistent with
images resized/cropped from heterogeneous original sources rather than captured by one
fixed rig, but that is an inference from the numbers, not a visual confirmation.

## Class census

Run via `certain_road.detect.dataset.voc.class_census` over `data/raw/water_potholes/XML/`:

| Class | Boxes |
|---|---|
| `pothole` | 1156 |
| `o` | 1 |
| **total** | **1157** |

`o` is a single-box annotation artifact (`XML/Pothole-487.xml`), almost certainly a
truncated/mistyped label rather than a distinct class — it is not treated as one.
Excluding it, the entire annotated vocabulary is one class: `pothole`.

## Are the potholes water-filled?

**This cannot be answered by this investigation.** The steps available here — file
counts, image dimensions, size distribution, and the class vocabulary — are not a
substitute for looking at the images, and per this task's own constraints, no image
content was visually inspected and no fraction is estimated or guessed.

What the available evidence does show:

- The bundled `ReadMe.txt` (the file physically inside `Potholes.zip`, the artifact
  D032 relied on) says nothing about water content at all. Verbatim, in full:

  > Dataset Content:
  > - IMG -> Dataset Images.
  > - XML -> Pascal VOC XML Format Annotations.
  > - TXT -> YOLO TXT Format Annotations.
  > - Potholes.zip -> Dataset images and annotation files in compressed format.
  >
  > Note: train.txt and valid.txt files are to be generated based on the location of
  > the dataset files within the training environment.
  >
  > Video:
  > - Potholes.mp4 ->  A short outdoor-recorded video to assess the frame rate of the
  > detection.

  (This ReadMe even describes a `Potholes.mp4` that does not exist in the extracted
  archive — the actual videos are `Dashcam-Front.mp4` and `Dashcam-Rear.mp4` — so the
  ReadMe is not fully in sync with what ships.)

- Only the Mendeley dataset page's own title and description — fetched separately from
  the public API, not from anything inside the zip — assert water content: the dataset
  is named *"An Annotated Water-Filled, and Dry Potholes Dataset for Deep Learning
  Applications."* That is a claim about the collection's intent, made outside the
  data package itself.

- The annotation vocabulary provides **no way to test that claim computationally**:
  there is exactly one object class, `pothole`. If "water-filled" versus "dry" were a
  labelled experimental condition, it would be reasonable to expect it encoded as
  separate classes or an attribute field. It is not. Every box, wet or dry, collapses
  to the same `pothole` label.

**Limitation, stated plainly:** this assessment could not visually verify what fraction
of the 713 images are genuinely water-filled versus dry, and no percentage is claimed
or guessed here. A human must open `data/raw/water_potholes/IMG/` and confirm the
water content directly before this dataset is relied on for anything. What can be said
without looking is that the annotations carry no signal that would let the *pipeline*
distinguish wet from dry even if a human confirms wet potholes are present — any
water/dry split would have to be built by hand, image by image, which is additional
un-budgeted work beyond this timeboxed spike.

## Class compatibility

Our class set is now three classes: `linear_crack` (RDD2022 `D00`+`D10` merged per
ASTM D6433, D038), `alligator_crack` (`D20`), `pothole` (`D40`). This dataset's entire
annotated vocabulary is `pothole` only.

Consequence, concretely: reference PCI computed on this dataset would be **pothole-only
reference PCI** — every evaluation segment built from it would have zero
`linear_crack` and zero `alligator_crack` boxes by construction, regardless of what a
human labeler might see in the raw image. Vision-estimated PCI on the same images would
also be pothole-only, since the detector cannot report a class this dataset never
represents. A shift comparison against RDD2022-calibrated coverage would therefore be
exercising only one of three deduct curves — the comparison is not apples-to-oranges in
the sense of comparing different quantities, but it is a narrower comparison than the
primary RDD2022-based results, testing detector robustness on one damage type instead
of the pipeline's full class mix.

## Decision

**NO-GO** — the synthetic corruption sweep (D031) carries the shift experiment
alone, as D025 anticipated. Reasoning:

1. The central premise this dataset would need to deliver — a genuine water-filled vs.
   dry distribution shift — is unverifiable by any means available in this timeboxed
   spike, and the one piece of hard evidence available (the annotation vocabulary) cuts
   against it: a single undifferentiated `pothole` class is what a dataset collected
   incidentally near water would produce, and is indistinguishable in the data from a
   deliberately-curated water/dry split. There is no way to tell which without a human
   opening 713 images, which is out of scope for this spike.
2. Independent of (1), the dataset is single-class, so any use narrows the comparison
   to the pothole contribution only, at the cost of extra pipeline complexity to keep
   the two evaluations aligned.
3. At 713 images it is small relative even to RDD2022's already-reduced India subset
   (7,706 annotated training images, D032/D036) — not obviously worth the added
   complexity for a secondary, optional experiment.

This does not block or delay any other week-1 or week-2 work. The synthetic corruption
sweep remains the primary — and, per this verdict, sole — distribution-shift experiment
for the thesis, exactly as D025 and D031 already planned for if this spike came back
negative.

