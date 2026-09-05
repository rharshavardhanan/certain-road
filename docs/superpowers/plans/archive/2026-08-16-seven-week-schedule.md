# The schedule — 4 partitions, 7 weeks, 2026-08-18 → 2026-10-05

**Revised 2026-08-17 · supersedes the 8-week timeline in D025 · hardware brought into
scope per D047**

```
Tue 2026-08-18 → Mon 2026-10-05 = 48 days ≈ 7 weeks
```

## The four partitions

| # | Weeks | Dates | Partition |
|---|---|---|---|
| **P1** | 1–2 | **Aug 18–31** | **Research core** — `assess` → `calibrate`, the coverage table, detector frozen. *(Result 1)* |
| **P2** | 3–4 | **Sep 1–14** | **Decision layer + validation** — rater session, `rsl`, knapsack, policy-impact figure. *(Results 2 & 3)* |
| **P3** | 5–7 | **Sep 15–Oct 5** | **Edge deployment** — Jetson bring-up, camera + GPS, `ingest`, ONNX/TensorRT, real capture drive. |
| **P4** | 1–7 | **Aug 18–Oct 5** | **Dashboard + thesis, written continuously alongside P1–P3, never left to the end.** |

P1 + P2 + P3 = 2 + 2 + 3 = 7 weeks of dedicated time. **P4 is not a phase, it is a
discipline** — there is no spare week at the end to write in, so the write-up accumulates
as each result lands.

## The one structural decision that makes this survivable

**Thesis results are frozen before the deployment demo is attempted.** All three results
are complete by **Sep 14**. If the edge work stalls, arrives broken, or proves impossible,
the cost is the *deployment chapter* — never the thesis.

**Hardware arriving Aug 18 does not move P3 earlier; it moves the *risky discovery* work
earlier.** The two are different. P3's deliverables still need a frozen detector and a
finished pipeline, so they stay in weeks 5–7. But everything that can fail *independently*
of the pipeline — flashing, runtimes, camera driver, GPS, the export path — is pulled into
a bounded parallel track in weeks 1–4, because a Jetson integration problem found on Sep 15
has no recovery time and the same problem found on Aug 19 has five weeks of it.

### The parallel hardware track — weeks 1–4, bounded

**Hard rule: this runs in a fixed timebox — one half-day per week, plus unattended
downloads/flashes — and never displaces P1 or P2.** If a task exceeds its box, park it and
carry it into P3. Hardware is a notorious focus thief; the coverage table is the degree.

| Week | Parallel hardware task | Why it cannot wait |
|---|---|---|
| 1 | **Day-1 verification** (below). Flash JetPack, NVMe + OS, boot to desktop. | If the board or camera is wrong, five weeks of the plan is fiction and you need to know immediately. |
| 1–2 | Install the on-device runtime: NVIDIA's torch wheel, or ONNX Runtime / TensorRT alone. | The classic Jetson yak-shave. JetPack↔torch wheel pinning eats days and eats them unpredictably. |
| 2 | **Prove the export path end-to-end with the *current* `multicountry_v8s` weights** — ONNX → TensorRT engine → one inference on-device. | Proves the pipeline mechanically. When the detector freezes Aug 31 you re-run a known-good path instead of debugging one. |
| 2–3 | CSI camera capturing frames; u-blox NEO-6M over UART, NMEA parsed to a track. | Both are fully independent of the model and of every pipeline stage. |
| 3 | **Pilot capture drive** — 20 minutes of road, video + GPS track, however rough. | Surfaces mounting, vibration, exposure and time-sync problems while there is still time. Also produces the real data `ingest` must be built against. |
| 3–4 | **Build `ingest`** against the pilot capture, on the Mac. | It is a pure software stage, upstream of `detect`, needing no detector at all — it only needs one real video and one real GPS track. |

By Sep 15, P3 then starts from *"the hardware works and `ingest` exists"* rather than
*"open the box"*, which is what converts P3 from three weeks of building into three weeks
of integrating — with slack for the first time in this schedule.

### Day-1 verification — three things that can invalidate P3

Check these on Aug 18, before anything else. Each has a cheap check and an expensive
discovery-in-week-5.

1. **Which board is it — Orin Nano, or the legacy 2019 Jetson Nano?** `cat
   /etc/nv_tegra_release` and `lsb_release -a`. The legacy Nano is EOL at JetPack 4.6 /
   Ubuntu 18.04 / **Python 3.6** / CUDA 10.2 with 4 GB RAM — it cannot run a modern
   ultralytics stack and the deployment story would have to change completely. The Orin
   Nano (JetPack 5/6) is the board this plan assumes.
2. **Does the camera sensor actually have a driver?** JetPack ships official support for
   **IMX219** and **IMX477**. The Raspberry Pi Camera Module 3's **IMX708 is not officially
   supported on Jetson** — third-party drivers exist but it is not plug-and-play. Verify
   with `v4l2-ctl --list-devices` on day 1; if it does not enumerate, switch to an
   IMX219/IMX477 module immediately rather than fighting a driver in September.
3. **A TensorRT engine cannot be built on the Mac.** Engines are specific to the device,
   the TensorRT version and the compute capability. `model.export(format="engine")` must
   run **on the Jetson**. Plan the export step as an on-device task, not a laptop one.

### What actually ships to the edge — and why the architecture already allows it

The project pins Python 3.12 (`requires-python = ">=3.12,<3.13"`). **JetPack does not ship
Python 3.12** — JetPack 6 is Ubuntu 22.04 / Python 3.10. So `uv sync` of the whole project
on the Jetson is not the deployment path, and should not be attempted.

It does not need to be. Stage isolation (D003) means the edge device only has to produce
the two artifacts the rest of the pipeline consumes:

```
Jetson:  camera + GPS → [ ingest ] → frames.parquet
                      → [ detect ] → detections.parquet     (TensorRT engine, no torch needed)
                                   ↓  copy two files
Mac:     [ assess ] → [ calibrate ] → [ rsl ] → [ optimize ] → [ report ]
```

Only `ingest` and `detect` need to run on-device, against a TensorRT engine and a
Parquet writer — a far smaller dependency surface than the full project, and one that
tolerates Python 3.10 without touching the pin. **This is the stage-isolation contract
paying for itself**, and it is worth showing a mentor as a design consequence rather than
a workaround.

---

## Week by week

### P1 · Research core — Aug 18–31

| Week | Dates | Work |
|---|---|---|
| 1 | Aug 18–24 | `assess`: ROI, `vision_density`, `apparent_severity`, deduct curves, iterative CDV. *Runs 3 + 4 finish overnight, unattended.* |
| 2 | Aug 25–31 | Evaluation segments (`K=15`), split conformal, `q̂`, **coverage table**. Candidate benchmarking. ⛔ **Detector freezes Aug 31.** |

**Day 1 (Aug 18), before any code:** close blocker 1 (PCI→RSL citation, or select
`mode: pci_only`), close blocker 2 (ASTM D6433 deduct curves), **book the three raters for
week 3**, and **place the hardware order** — see the procurement gate below.

**Done when:** the coverage table reports empirical coverage against 86–94% at α = 0.1 and
a stated `q̂` against the ≤ 7.5 PCI-point target. **This is the thesis go/no-go.**

### P2 · Decision layer + validation — Sep 1–14

| Week | Dates | Work |
|---|---|---|
| 3 | Sep 1–7 | **Rating session** — 3 raters × ~1 h, 50 stratified segments, blind. Fleiss' κ as ceiling. `rsl` stage (curve inversion, config-only). |
| 4 | Sep 8–14 | DP knapsack, treatment/cost/benefit, `rsl_lo` must-fix. Dual run → **policy-impact figure**. |

**Done when:** κ reported both ways (model-vs-human and human-vs-human), and the two-axis
policy-impact figure exists — reallocation % and unfunded-critical-km, point policy vs
interval policy.

> 📌 **Sep 7 is immovable.** Three people's calendars cannot be compressed by working
> harder. Book them on Aug 18.

### P3 · Edge deployment — Sep 15–Oct 5

Assumes the weeks 1–4 parallel track landed: board flashed, runtime installed, export path
proven, camera and GPS capturing, `ingest` built against a pilot drive. P3 is therefore
**integration and demonstration, not bring-up**.

| Week | Dates | Work |
|---|---|---|
| 5 | Sep 15–21 | Export the **frozen** detector → ONNX → TensorRT **on-device**, down the path already proven in week 2. **On-device latency benchmark** — mean/p50/p95, with the power mode (7 W / 15 W / 25 W) recorded, against the MPS numbers already measured. |
| 6 | Sep 22–28 | Enclosure mount, camera pod and compute box. **The real capture drive.** `ingest` + `detect` run on-device end to end, emitting `frames.parquet` and `detections.parquet`. |
| 7 | Sep 29–Oct 5 | Full frozen pipeline over the real capture on the Mac; **dashboard from genuinely captured road**. Final thesis assembly. |

**Done when:** a real drive produces `frames.parquet` with genuine GPS-derived
`cum_dist_m` and `segment_id`, the frozen detector runs on-device with a measured latency
number and a stated power mode, and the dashboard renders that drive.

**If the parallel track did *not* land**, P3 absorbs the bring-up and weeks 6–7 compress to
a single demonstration attempt — recoverable, but this is exactly the slack the parallel
track exists to create.

### P4 · Dashboard + thesis — continuous, Aug 18–Oct 5

Dashboard (synthetic network, Decision Replay) is built incrementally against whatever
artifacts exist; each result is written up the week it lands. **Submit Oct 5.**

---

## What 3 weeks of hardware costs

The pre-hardware plan already had zero buffer. Three weeks of edge work is paid for by:

| Cut | Was | Status |
|---|---|---|
| Synthetic distribution-shift sweep | Result 4 | **Cut** (D025's own designated first cut) |
| Sensitivity analysis (±20% ROI, cutpoints) | D029 | **Cut** |
| A dedicated dashboard week | week 5 | **Folded into P4**, built incrementally |
| A dedicated write-up week | week 7 | **Folded into P4**, written continuously |

**Never cut:** the validation study (D027) and the coverage table. They are the only
evidence the central quantity means anything, and Result 1 respectively.

## Hard dates

| Date | Gate | If missed |
|---|---|---|
| **Aug 18** | Blockers 1+2 closed · raters booked · **Jetson day-1 verification: board, camera driver, runtime** | P1 blocked on curves; an unusable board or camera stays undiscovered |
| **Aug 25** | Export path proven on-device with current weights | Week-5 export becomes debugging, not a re-run |
| **Aug 31** | Coverage table exists · **detector frozen** | Thesis go/no-go — escalate same day |
| **Sep 7** | Rating session complete · camera + GPS capturing | No recovery — more time cannot fix the raters |
| **Sep 14** | Policy-impact figure exists · **all three results locked** · `ingest` built | Do not start P3; finish P2 first |
| **Oct 5** | Submit | — |

## Hardware fallback — now an integration gate, not a procurement one

With the board in hand on Aug 18, the procurement risk is closed. What remains is
integration risk, and the day-1 verification list decides it. **Trigger the fallback the
moment any of these is true:**

- the board is a legacy Jetson Nano rather than an Orin Nano;
- no camera driver enumerates and no supported module is obtainable within a week;
- the on-device runtime is not working by **Sep 7**.

**Fallback:** P3 reverts to D025's degraded chapter — ONNX export and latency benchmark on
MPS, a simulated GPS track driving `ingest` over recorded dashcam video, architecture
documented rather than demonstrated. The thesis is unaffected because all three results
are frozen on Sep 14. **Make the call by Sep 7, while five weeks of the parallel track
have already told you the answer** — not in October.
