# Trial textures: sources, licences and leak audit

Audited 2026-10-05. Recorded in `docs/DECISIONS.md` as D086.

## Sources and licences

All 49 images are CC BY 4.0. Credit both datasets wherever a render from them is shown or
published. They are not the user's own photos.

- **QR4Change**: Maske Y., Jakate S., Thakare C., Lokhande S. (2025). *Urban Civic Issues
  Image Dataset: Potholes and Garbage.* Mendeley Data V2, doi:10.17632/zndzygc3p3.2. Pune,
  India. Supplies the 18 potholes.
- **BD-N6**: Hossain M.N., Aman N., Antor N.R., Tasnim N., Azam M.Z., et al. *Flexible
  Pavement Distress Image Dataset ... National Highway N6, Bangladesh,* Parts 1 and 2.
  Zenodo, doi:10.5281/zenodo.18072573 and doi:10.5281/zenodo.18114226. Supplies the 12
  linear cracks, 15 alligator cracks and 4 plain asphalt images.

The images arrived as `indian_road_textures.zip` and are stored flat here, not under
`indian_road_textures/`.

## Did any model ever train on QR4Change or BD-N6?

**No.** Nothing in the repository names either dataset: not in `configs/`, `splits/`,
`kaggle/`, `scripts/`, `src/`, any notebook, or `docs/DECISIONS.md`. `docs/TASKS.md` does not
exist. The only exception is the simulator code written before this audit. No QR4Change
image exists anywhere under `data/` outside this folder. The Kaggle job configs and the
upload manifest do not name either dataset, and no split list contains a QR4Change filename
(`Img (N).jpg`).

The only Mendeley dataset in the decision log is a different one: `tp95cdvgm8`, the
water-pothole set rejected in D039. Training used RDD2022 (Models A and B) and BharatPotHole
(Model P): every one of the 9,689 entries in `data/yolo_pothole/p_train.txt` is `India__` or
`BharatPotHole`. The audit's remaining purpose is therefore copy and crop overlap with
`india_train`, `nonindia_train` and BharatPotHole `train`.

## Method

The method of record is unchanged.

- **Copies:** each texture's `dedupe.norm_vec` (D063/D066) is compared with all 4,622
  `india_train`, 24,508 `nonindia_train` and 5,067 BharatPotHole `train` images. Every pair
  at or above 0.93 is listed.
- **Crops**, which norm_vec cannot detect: ORB (3,000 features) with a ratio test and a RANSAC
  homography (5 px), against each texture's 20 nearest `india_train` and BharatPotHole images
  by norm_vec. A pair is flagged at 30 or more inliers.
- **Positive control:** 10 real crops of training images, each upscaled 4× to texture size,
  were matched against their own sources. Nine flagged, at 44–305 inliers. One low-texture
  crop scored 0. The crop check therefore catches most crops, not all. It also searches only
  each texture's 20 nearest images, so a crop whose source ranks lower would be missed.

## Result

- Pairs at or above 0.93: **none**. The maximum correlation is 0.8887 (`alligator_06`).
- Best crop-match inliers: at most **8**, against a flag line of 30. No pair was flagged.
- Every texture's status is CLEAN.

| Texture | Resolution | Dataset | Max corr | Best inliers | In a training split | Status |
|---|---|---|---:|---:|---|---|
| `1_potholes_india_pune/potholes_01.jpg` | 2250x3000 | QR4Change (Pune) | 0.5188 | 0 | N | CLEAN |
| `1_potholes_india_pune/potholes_02.jpg` | 2250x3000 | QR4Change (Pune) | 0.7178 | 5 | N | CLEAN |
| `1_potholes_india_pune/potholes_03.jpg` | 2250x3000 | QR4Change (Pune) | 0.4129 | 6 | N | CLEAN |
| `1_potholes_india_pune/potholes_04.jpg` | 2250x3000 | QR4Change (Pune) | 0.4471 | 4 | N | CLEAN |
| `1_potholes_india_pune/potholes_05.jpg` | 2250x3000 | QR4Change (Pune) | 0.4404 | 0 | N | CLEAN |
| `1_potholes_india_pune/potholes_06.jpg` | 2250x3000 | QR4Change (Pune) | 0.6197 | 5 | N | CLEAN |
| `1_potholes_india_pune/potholes_07.jpg` | 2250x3000 | QR4Change (Pune) | 0.6942 | 6 | N | CLEAN |
| `1_potholes_india_pune/potholes_08.jpg` | 2250x3000 | QR4Change (Pune) | 0.7191 | 4 | N | CLEAN |
| `1_potholes_india_pune/potholes_09.jpg` | 2250x3000 | QR4Change (Pune) | 0.6460 | 8 | N | CLEAN |
| `1_potholes_india_pune/potholes_10.jpg` | 2250x3000 | QR4Change (Pune) | 0.4981 | 4 | N | CLEAN |
| `1_potholes_india_pune/potholes_11.jpg` | 2250x3000 | QR4Change (Pune) | 0.4635 | 8 | N | CLEAN |
| `1_potholes_india_pune/potholes_12.jpg` | 2250x3000 | QR4Change (Pune) | 0.6554 | 6 | N | CLEAN |
| `1_potholes_india_pune/potholes_13.jpg` | 2250x3000 | QR4Change (Pune) | 0.4204 | 4 | N | CLEAN |
| `1_potholes_india_pune/potholes_14.jpg` | 2250x3000 | QR4Change (Pune) | 0.5280 | 5 | N | CLEAN |
| `1_potholes_india_pune/potholes_15.jpg` | 2250x3000 | QR4Change (Pune) | 0.5837 | 5 | N | CLEAN |
| `1_potholes_india_pune/potholes_16.jpg` | 2250x3000 | QR4Change (Pune) | 0.3698 | 6 | N | CLEAN |
| `1_potholes_india_pune/potholes_17.jpg` | 2250x3000 | QR4Change (Pune) | 0.5008 | 4 | N | CLEAN |
| `1_potholes_india_pune/potholes_18.jpg` | 2250x3000 | QR4Change (Pune) | 0.6001 | 6 | N | CLEAN |
| `2_linear_cracks/linear_01.jpg` | 3000x2250 | BD-N6 (Bangladesh) | 0.8100 | 5 | N | CLEAN |
| `2_linear_cracks/linear_02.jpg` | 2484x2276 | BD-N6 (Bangladesh) | 0.8312 | 5 | N | CLEAN |
| `2_linear_cracks/linear_03.jpg` | 2788x2288 | BD-N6 (Bangladesh) | 0.8479 | 5 | N | CLEAN |
| `2_linear_cracks/linear_04.jpg` | 2532x2448 | BD-N6 (Bangladesh) | 0.8276 | 0 | N | CLEAN |
| `2_linear_cracks/linear_05.jpg` | 2781x2448 | BD-N6 (Bangladesh) | 0.7613 | 4 | N | CLEAN |
| `2_linear_cracks/linear_06.jpg` | 3000x2250 | BD-N6 (Bangladesh) | 0.3778 | 4 | N | CLEAN |
| `2_linear_cracks/linear_07.jpg` | 3000x2250 | BD-N6 (Bangladesh) | 0.4144 | 5 | N | CLEAN |
| `2_linear_cracks/linear_08.jpg` | 3000x2250 | BD-N6 (Bangladesh) | 0.4931 | 5 | N | CLEAN |
| `2_linear_cracks/linear_09.jpg` | 3000x2250 | BD-N6 (Bangladesh) | 0.5345 | 0 | N | CLEAN |
| `2_linear_cracks/linear_10.jpg` | 3000x2250 | BD-N6 (Bangladesh) | 0.5807 | 4 | N | CLEAN |
| `2_linear_cracks/linear_11.jpg` | 3000x2250 | BD-N6 (Bangladesh) | 0.6145 | 5 | N | CLEAN |
| `2_linear_cracks/linear_12.jpg` | 3000x2250 | BD-N6 (Bangladesh) | 0.7676 | 0 | N | CLEAN |
| `3_alligator_cracks/alligator_01.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.5534 | 5 | N | CLEAN |
| `3_alligator_cracks/alligator_02.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.5444 | 4 | N | CLEAN |
| `3_alligator_cracks/alligator_03.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.5738 | 0 | N | CLEAN |
| `3_alligator_cracks/alligator_04.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.7301 | 0 | N | CLEAN |
| `3_alligator_cracks/alligator_05.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.6144 | 6 | N | CLEAN |
| `3_alligator_cracks/alligator_06.jpg` | 2259x3000 | BD-N6 (Bangladesh) | 0.8887 | 0 | N | CLEAN |
| `3_alligator_cracks/alligator_07.jpg` | 3000x2259 | BD-N6 (Bangladesh) | 0.7727 | 6 | N | CLEAN |
| `3_alligator_cracks/alligator_08.jpg` | 2259x3000 | BD-N6 (Bangladesh) | 0.8258 | 4 | N | CLEAN |
| `3_alligator_cracks/alligator_09.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.8413 | 0 | N | CLEAN |
| `3_alligator_cracks/alligator_10.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.6581 | 0 | N | CLEAN |
| `3_alligator_cracks/alligator_11.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.7741 | 5 | N | CLEAN |
| `3_alligator_cracks/alligator_12.jpg` | 3000x2250 | BD-N6 (Bangladesh) | 0.8267 | 0 | N | CLEAN |
| `3_alligator_cracks/alligator_13.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.5376 | 0 | N | CLEAN |
| `3_alligator_cracks/alligator_14.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.6659 | 5 | N | CLEAN |
| `3_alligator_cracks/alligator_15.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.6549 | 5 | N | CLEAN |
| `4_plain_asphalt/plain_01.jpg` | 1688x3000 | BD-N6 (Bangladesh) | 0.2133 | 0 | N | CLEAN |
| `4_plain_asphalt/plain_02.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.5218 | 0 | N | CLEAN |
| `4_plain_asphalt/plain_03.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.2678 | 0 | N | CLEAN |
| `4_plain_asphalt/plain_04.jpg` | 2250x3000 | BD-N6 (Bangladesh) | 0.8208 | 4 | N | CLEAN |

**Context, not a reason to pass anything:** the textures are 1,688–3,000 px on their long
side. `india_train` is 720×720, and BharatPotHole is 640×640. A texture is baked onto the
road plane and seen through a 1280×720 perspective camera, so it is a different object from
a training image.

## Credits file, verbatim

```
Indian road textures for RoadSight MuJoCo sim
Collected 2026-10-04. All images CC BY 4.0 - credit the dataset authors below if you publish.
Images re-encoded to max 3000 px long side, JPEG q90, EXIF stripped.

DATASETS
[QR4Change] Maske Y., Jakate S., Thakare C., Lokhande S. (2025). Urban Civic Issues Image Dataset: Potholes and Garbage (QR4Change), Mendeley Data, V2. doi:10.17632/zndzygc3p3.2. Captured in Pune, Maharashtra, India. CC BY 4.0.
[BD-N6] Hossain M.N., Aman N., Antor N.R., Tasnim N., Azam M.Z., et al. Flexible Pavement Distress Image Dataset Featuring Alligator Cracks and Edge Failures from National Highway N6, Bangladesh, Parts 1 & 2. Zenodo. doi:10.5281/zenodo.18072573 and doi:10.5281/zenodo.18114226. Near-vertical smartphone shots, 50-64 MP originals. CC BY 4.0.

NOTE: potholes are Indian (Pune). Cracks and plain asphalt are from Bangladesh NH-N6 - the same bituminous (BC/DBM) construction as Indian NH/SH roads; no open Indian top-down crack set at usable resolution exists.

FILE MAP (output -> dataset / original file / size)
1_potholes_india_pune/potholes_01.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (1001).jpg / 2250x3000
1_potholes_india_pune/potholes_02.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (105).jpg / 2250x3000
1_potholes_india_pune/potholes_03.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (10).jpg / 2250x3000
1_potholes_india_pune/potholes_04.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (115).jpg / 2250x3000
1_potholes_india_pune/potholes_05.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (116).jpg / 2250x3000
1_potholes_india_pune/potholes_06.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (117).jpg / 2250x3000
1_potholes_india_pune/potholes_07.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (141).jpg / 2250x3000
1_potholes_india_pune/potholes_08.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (142).jpg / 2250x3000
1_potholes_india_pune/potholes_09.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (177).jpg / 2250x3000
1_potholes_india_pune/potholes_10.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (269).jpg / 2250x3000
1_potholes_india_pune/potholes_11.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (273).jpg / 2250x3000
1_potholes_india_pune/potholes_12.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (276).jpg / 2250x3000
1_potholes_india_pune/potholes_13.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (339).jpg / 2250x3000
1_potholes_india_pune/potholes_14.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (46).jpg / 2250x3000
1_potholes_india_pune/potholes_15.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (53).jpg / 2250x3000
1_potholes_india_pune/potholes_16.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (58).jpg / 2250x3000
1_potholes_india_pune/potholes_17.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (59).jpg / 2250x3000
1_potholes_india_pune/potholes_18.jpg  <-  QR4Change Pune (Mendeley 10.17632/zndzygc3p3.2) / Img (62).jpg / 2250x3000
2_linear_cracks/linear_01.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1355.jpg / 3000x2250
2_linear_cracks/linear_02.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1361.jpg / 2484x2276
2_linear_cracks/linear_03.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1363.jpg / 2788x2288
2_linear_cracks/linear_04.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1371.jpg / 2532x2448
2_linear_cracks/linear_05.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1379.jpg / 2781x2448
2_linear_cracks/linear_06.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1419.jpg / 3000x2250
2_linear_cracks/linear_07.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1421.jpg / 3000x2250
2_linear_cracks/linear_08.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1427.jpg / 3000x2250
2_linear_cracks/linear_09.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1435.jpg / 3000x2250
2_linear_cracks/linear_10.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1443.jpg / 3000x2250
2_linear_cracks/linear_11.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1459.jpg / 3000x2250
2_linear_cracks/linear_12.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator3195.jpg / 3000x2250
3_alligator_cracks/alligator_01.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator0101.jpg / 2250x3000
3_alligator_cracks/alligator_02.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator0201.jpg / 2250x3000
3_alligator_cracks/alligator_03.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator0301.jpg / 2250x3000
3_alligator_cracks/alligator_04.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator0501.jpg / 2250x3000
3_alligator_cracks/alligator_05.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator0601.jpg / 2250x3000
3_alligator_cracks/alligator_06.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1001.jpg / 2259x3000
3_alligator_cracks/alligator_07.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1201.jpg / 3000x2259
3_alligator_cracks/alligator_08.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1221.jpg / 2259x3000
3_alligator_cracks/alligator_09.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1387.jpg / 2250x3000
3_alligator_cracks/alligator_10.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1395.jpg / 2250x3000
3_alligator_cracks/alligator_11.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator1403.jpg / 2250x3000
3_alligator_cracks/alligator_12.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator2101.jpg / 3000x2250
3_alligator_cracks/alligator_13.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator3701.jpg / 2250x3000
3_alligator_cracks/alligator_14.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator3801.jpg / 2250x3000
3_alligator_cracks/alligator_15.jpg  <-  BD-N6 Part2 (Zenodo 10.5281/zenodo.18114226) / alligator3901.jpg / 2250x3000
4_plain_asphalt/plain_01.jpg  <-  BD-N6 Part1 (Zenodo 10.5281/zenodo.18072573) / good0251.jpg / 1688x3000
4_plain_asphalt/plain_02.jpg  <-  BD-N6 Part1 (Zenodo 10.5281/zenodo.18072573) / good1951.jpg / 2250x3000
4_plain_asphalt/plain_03.jpg  <-  BD-N6 Part1 (Zenodo 10.5281/zenodo.18072573) / good2551.jpg / 2250x3000
4_plain_asphalt/plain_04.jpg  <-  BD-N6 Part1 (Zenodo 10.5281/zenodo.18072573) / good3351.jpg / 2250x3000```
