# T12 - repair allocation under budget

200 synthetic evaluation segments, 1000 networks per traffic regime, paired across every alpha and budget. Detection per class at Model B's recall on locked india_test; condition through vision_density -> deduct_value -> vision_estimated_pci. **False alarms are not modelled.**

| role | alpha | tau-hat | false alarms/img | recall (linear / alligator / pothole) |
|---|---|---|---|---|
| headline | 0.5 | 0.117 | 0.433 | 0.3645 / 0.6448 / 0.5254 |
| sensitivity | 0.1 | 0.001 | 31.198 | 0.8692 / 0.9575 / 0.9007 |
| sensitivity | 0.3 | 0.029 | 2.328 | 0.5841 / 0.8069 / 0.7167 |

## Headline, alpha 0.5

| regime | budget | policy | benefit vs oracle | worst-20 share |
|---|---|---|---|---|
| uniform_traffic | 10% | oracle | 100.0% | 0.5% |
| uniform_traffic | 10% | nominal | 95.2% | 2.2% |
| uniform_traffic | 10% | robust | 95.7% | 1.4% |
| uniform_traffic | 10% | greedy | 68.5% | 39.2% |
| uniform_traffic | 10% | random | 76.4% | 9.3% |
| uniform_traffic | 20% | oracle | 100.0% | 1.9% |
| uniform_traffic | 20% | nominal | 95.6% | 7.9% |
| uniform_traffic | 20% | robust | 96.2% | 5.9% |
| uniform_traffic | 20% | greedy | 75.7% | 81.0% |
| uniform_traffic | 20% | random | 79.4% | 19.1% |
| uniform_traffic | 30% | oracle | 100.0% | 5.3% |
| uniform_traffic | 30% | nominal | 96.0% | 17.5% |
| uniform_traffic | 30% | robust | 96.6% | 14.4% |
| uniform_traffic | 30% | greedy | 81.3% | 96.7% |
| uniform_traffic | 30% | random | 81.2% | 29.0% |
| uniform_traffic | 40% | oracle | 100.0% | 11.8% |
| uniform_traffic | 40% | nominal | 96.4% | 30.6% |
| uniform_traffic | 40% | robust | 96.9% | 27.3% |
| uniform_traffic | 40% | greedy | 86.0% | 99.6% |
| uniform_traffic | 40% | random | 82.9% | 39.3% |
| uniform_traffic | 50% | oracle | 100.0% | 21.8% |
| uniform_traffic | 50% | nominal | 96.7% | 45.9% |
| uniform_traffic | 50% | robust | 97.2% | 42.9% |
| uniform_traffic | 50% | greedy | 89.9% | 99.9% |
| uniform_traffic | 50% | random | 84.5% | 49.4% |
| varying_traffic | 10% | oracle | 100.0% | 66.4% |
| varying_traffic | 10% | nominal | 97.8% | 65.2% |
| varying_traffic | 10% | robust | 98.1% | 64.9% |
| varying_traffic | 10% | greedy | 87.9% | 64.9% |
| varying_traffic | 10% | random | 30.3% | 9.6% |
| varying_traffic | 20% | oracle | 100.0% | 88.1% |
| varying_traffic | 20% | nominal | 98.0% | 89.6% |
| varying_traffic | 20% | robust | 98.3% | 88.8% |
| varying_traffic | 20% | greedy | 90.2% | 96.1% |
| varying_traffic | 20% | random | 39.9% | 19.9% |
| varying_traffic | 30% | oracle | 100.0% | 96.0% |
| varying_traffic | 30% | nominal | 98.2% | 97.0% |
| varying_traffic | 30% | robust | 98.4% | 96.7% |
| varying_traffic | 30% | greedy | 91.9% | 98.7% |
| varying_traffic | 30% | random | 47.8% | 30.0% |
| varying_traffic | 40% | oracle | 100.0% | 98.7% |
| varying_traffic | 40% | nominal | 98.4% | 99.1% |
| varying_traffic | 40% | robust | 98.6% | 99.0% |
| varying_traffic | 40% | greedy | 93.3% | 99.4% |
| varying_traffic | 40% | random | 54.8% | 39.9% |
| varying_traffic | 50% | oracle | 100.0% | 99.7% |
| varying_traffic | 50% | nominal | 98.5% | 99.7% |
| varying_traffic | 50% | robust | 98.7% | 99.7% |
| varying_traffic | 50% | greedy | 94.6% | 99.6% |
| varying_traffic | 50% | random | 61.9% | 50.0% |

## Robust minus nominal, paired over networks

| regime | alpha | budget | identical choice | benefit diff [95% CI] | worst-20 diff [95% CI] |
|---|---|---|---|---|---|
| uniform_traffic | 0.5 | 10% | 5.3% | +3.8 [+3.5, +4.2] | -0.0080 [-0.0093, -0.0066] |
| uniform_traffic | 0.5 | 20% | 0.9% | +8.2 [+7.7, +8.7] | -0.0208 [-0.0228, -0.0187] |
| uniform_traffic | 0.5 | 30% | 0.2% | +12.6 [+12.0, +13.2] | -0.0306 [-0.0329, -0.0282] |
| uniform_traffic | 0.5 | 40% | 0.3% | +15.1 [+14.3, +15.8] | -0.0340 [-0.0367, -0.0313] |
| uniform_traffic | 0.5 | 50% | 0.0% | +15.7 [+14.8, +16.5] | -0.0301 [-0.0327, -0.0275] |
| uniform_traffic | 0.1 | 10% | 71.7% | +0.1 [+0.0, +0.1] | -0.0011 [-0.0015, -0.0006] |
| uniform_traffic | 0.1 | 20% | 58.3% | +0.3 [+0.2, +0.4] | -0.0015 [-0.0022, -0.0009] |
| uniform_traffic | 0.1 | 30% | 55.1% | +0.4 [+0.2, +0.5] | -0.0030 [-0.0040, -0.0021] |
| uniform_traffic | 0.1 | 40% | 54.9% | +0.4 [+0.3, +0.6] | -0.0034 [-0.0045, -0.0024] |
| uniform_traffic | 0.1 | 50% | 53.3% | +0.5 [+0.3, +0.6] | -0.0032 [-0.0045, -0.0020] |
| uniform_traffic | 0.3 | 10% | 28.2% | +1.4 [+1.2, +1.6] | -0.0025 [-0.0032, -0.0017] |
| uniform_traffic | 0.3 | 20% | 11.6% | +3.0 [+2.7, +3.3] | -0.0089 [-0.0103, -0.0075] |
| uniform_traffic | 0.3 | 30% | 6.7% | +4.4 [+4.1, +4.8] | -0.0136 [-0.0152, -0.0119] |
| uniform_traffic | 0.3 | 40% | 4.0% | +5.3 [+4.9, +5.6] | -0.0186 [-0.0206, -0.0166] |
| uniform_traffic | 0.3 | 50% | 4.0% | +5.9 [+5.5, +6.3] | -0.0182 [-0.0202, -0.0162] |
| varying_traffic | 0.5 | 10% | 35.9% | +6.4 [+4.5, +8.3] | -0.0030 [-0.0049, -0.0010] |
| varying_traffic | 0.5 | 20% | 17.0% | +10.1 [+8.4, +11.8] | -0.0074 [-0.0091, -0.0058] |
| varying_traffic | 0.5 | 30% | 5.4% | +12.1 [+10.3, +13.8] | -0.0040 [-0.0052, -0.0028] |
| varying_traffic | 0.5 | 40% | 3.6% | +13.7 [+12.0, +15.4] | -0.0014 [-0.0021, -0.0007] |
| varying_traffic | 0.5 | 50% | 2.3% | +14.3 [+12.7, +15.9] | +0.0000 [-0.0005, +0.0005] |
| varying_traffic | 0.1 | 10% | 91.1% | +0.0 [-0.1, +0.2] | -0.0011 [-0.0018, -0.0005] |
| varying_traffic | 0.1 | 20% | 82.1% | -0.0 [-0.2, +0.2] | -0.0014 [-0.0020, -0.0008] |
| varying_traffic | 0.1 | 30% | 77.1% | +0.2 [+0.0, +0.3] | -0.0007 [-0.0011, -0.0003] |
| varying_traffic | 0.1 | 40% | 73.2% | +0.2 [-0.0, +0.3] | -0.0005 [-0.0008, -0.0002] |
| varying_traffic | 0.1 | 50% | 69.6% | -0.0 [-0.1, +0.1] | -0.0001 [-0.0001, +0.0000] |
| varying_traffic | 0.3 | 10% | 66.7% | +1.9 [+1.1, +2.7] | -0.0030 [-0.0044, -0.0015] |
| varying_traffic | 0.3 | 20% | 48.7% | +2.1 [+1.3, +2.9] | -0.0035 [-0.0046, -0.0024] |
| varying_traffic | 0.3 | 30% | 33.7% | +2.7 [+1.9, +3.5] | -0.0027 [-0.0034, -0.0019] |
| varying_traffic | 0.3 | 40% | 27.7% | +3.4 [+2.6, +4.1] | -0.0009 [-0.0014, -0.0004] |
| varying_traffic | 0.3 | 50% | 22.9% | +3.1 [+2.3, +3.8] | -0.0006 [-0.0009, -0.0002] |

Generated by `scripts/exp_allocation.py` and overwritten on every run. `findings.md` is authored; decisions are in `docs/DECISIONS.md`.
