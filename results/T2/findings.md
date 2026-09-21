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
