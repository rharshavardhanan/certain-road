# T2 — findings

Authored companion to `split_audit.md`, which is generated and overwritten
on every run of `scripts/build_pool.py`.

## Split fractions achieved

| split | images | share | target |
|---|---|---|---|
| india_train | 4,579 | 0.594 | 0.60 |
| india_val | 799 | 0.104 | 0.10 |
| india_cal | 1,205 | 0.156 | 0.15 |
| india_test | 1,123 | 0.146 | 0.15 |
| nonindia_val | 6,142 | 0.200 | 0.20 |

Within ~0.6pp of target. A salted hash cannot hit a fraction exactly — that is
the price of assignment being stable when the file set changes (D009), and it is
the right trade: a seeded shuffle hits the target precisely but reshuffles every
image the moment one file is added.

India sums to 7,706 images / 6,831 instances and non-India to 30,679 images,
both matching T1's raw audit exactly.

## The number that matters most

**India is 46.65% pothole by instance; non-India is 6.97%.** A 6.7x difference.

Model A trains only on non-India, so it sees potholes as roughly 1 instance in
14 and linear cracks as 3 in 4. India inverts that. This is the single largest
driver of the generalization gap T6 will measure, and it is a property of the
data, not of the model — no amount of training on non-India can fix it. It is
also why T7's Model B exists.

## Visual QA on the materialised pool

Five images from each of the nine splits, plus five Norway frames, rendered from
the **pool** files with boxes decoded from the **pool** labels —
`results/T2/qa_pool_{A,B}.jpg`. All fifty were viewed.

Boxes align correctly in every split. The check that mattered is Norway:
its images were resized 4040x2035 -> 1280x645, and the boxes still land on the
cracks, confirming that normalised labels survived the only resize in the build.

The India/non-India contrast is visible without reading the table — Indian frames
are dominated by orange `alligator_crack` across broken shoulders and red
`pothole`, non-India by green `linear_crack` on otherwise sound pavement.

## Naming

Pool files are `<Country>__<stem>`, per T2. RDD2022 stems already begin with the
country, so this reads `India__India_000259`. The repetition is deliberate: one
prefix rule covers RDD2022, BharatPotHole (T9) and Chennai (T15) alike, so the
leakage tests stay a plain string check across all three sources.

---

# D061 — near-duplicate audit (added after the first split)

**A real leak was found and closed.** The India split now holds zero same-scene
pairs across the train/held-out boundary.

## What the leak was

dHash at Hamming <= 6 flagged 1,321 India cross-split pairs. Inspection showed
most were false positives — Indian dashcam frames share a strong global layout
(road centred, sky in the top third, vegetation flanking), and a 64-bit hash of a
9x8 thumbnail cannot tell two such frames apart. Two images, `India_000129` and
`India_000135`, appeared against many different partners: low-information "hub"
frames close to everything.

But ranking those pairs by 128x128 pixel correlation found a genuine problem at
the top. The closest pairs are **the same physical location seconds apart** —
identical stacked concrete pipes and pylons, the same building with the same blue
signboard and the same parked red car, the same white SUV on the same stretch.
Not the same file; the same place.

That is as contaminating as a byte-identical duplicate. A detector trained on one
frame has effectively seen the other, so a held-out score computed over them is
not held out.

**An initial reading of this was wrong.** Checking for correlation > 0.98 found
nothing and suggested no leak. That threshold tests for *identical frames*; a
true duplicate scores ~0.999. The leak here is *same-scene*, which tops out
around 0.97 — inside the noise of a 0.98 bar, and just as damaging.

## Threshold, calibrated rather than assumed

| correlation | verdict on inspection |
|---|---|
| 0.955 – 0.975 | unambiguously the same location |
| 0.935 – 0.955 | same location (same bridge girders, same hoarding, same vehicle) |
| 0.915 – 0.935 | ambiguous — same corridor, further apart |
| 0.895 – 0.915 | different scenes sharing a composition |

**0.93** was chosen. The error is asymmetric: grouping too eagerly costs a
slightly lumpier split, while grouping too little leaves the India claim
inflated.

## A bug in the audit itself

The audit hashed with PIL/LANCZOS and the grouper with cv2/INTER_AREA — two
different dHash implementations. The audit therefore flagged pairs the grouper
had never considered, and after the first regrouping 19 same-scene pairs still
crossed the boundary. Both now share one implementation in
`perception/dataset/dedupe.py`, and the grouping prefilter is deliberately looser
than the audit's (Hamming 12 vs 6) so that anything the audit can flag was
already considered for grouping.

A duplicate detector that disagrees with itself is worse than none, because it
reports success.

## Result

| | before | after |
|---|---|---|
| same-scene pairs crossing India splits | 19+ | **0** |
| max cross-boundary pixel correlation | 0.9716 | 0.9297 |
| scene groups held together | — | 253 |
| India images in a group | — | 1,602 of 7,706 |

The largest group is 771 images and landed **entirely in `india_train`**
(16.7% of it); no group of any size touches val, cal or test. Split fractions
came out *closer* to target than the ungrouped hash: 59.99 / 10.01 / 15.00 /
15.00 against 60 / 10 / 15 / 15.

`test_no_scene_group_spans_india_splits` makes this permanent.

**Non-India duplicates are reported as a count only** (3,964 flagged), per D061:
they inflate validation optimism and so affect early stopping, but they cannot
reach the India sets the headline claim is measured on.
