"""RESULTS.md is generated; these pin the properties that make it trustworthy.

Every number must trace to a file, so every table is followed by its source. A
missing input is a "not run" row, not an omitted section. Two statements depend on
files outside `results/` — whether D082 has been written, and who annotated the
video ground truth — and both are read from those files, never typed in, so the
report cannot go stale when they change.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from make_report import build_report  # noqa: E402

STAMP = {"utc": "2026-10-03 00:00 UTC", "commit": "abc1234"}
SECTIONS = (
    "Data audit",
    "Model A",
    "Model A vs Model B",
    "External",
    "Conformal",
    "Drift",
    "Allocation",
    "Simulation",
    "Edge",
    "Video",
    "Decision log",
)


def tables_and_what_follows(report: str) -> list[str]:
    """For each markdown table, the first non-empty line after it."""
    lines = report.splitlines()
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith("|"):
            while i < len(lines) and lines[i].startswith("|"):
                i += 1
            nxt = next((ln for ln in lines[i:] if ln.strip()), "")
            out.append(nxt)
        else:
            i += 1
    return out


def test_an_empty_results_tree_builds_with_every_section_and_not_run_rows(tmp_path):
    report = build_report(tmp_path, STAMP)
    for s in SECTIONS:
        assert f"## {s}" in report, s
    assert report.count("| not run |") >= 10
    assert "results/T13" in report and "results/T14" in report and "results/T15" in report


def test_every_table_is_followed_by_its_source(tmp_path):
    report = build_report(tmp_path, STAMP)
    follows = tables_and_what_follows(report)
    assert follows, "no tables rendered"
    assert all(f.startswith("Source:") for f in follows), [
        f for f in follows if not f.startswith("Source:")
    ]


def test_the_real_report_also_puts_a_source_under_every_table():
    root = Path(__file__).resolve().parents[1]
    report = build_report(root, STAMP)
    follows = tables_and_what_follows(report)
    assert len(follows) > 10
    assert all(f.startswith("Source:") for f in follows)


def write_decisions(root: Path, rows: list[str]) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs/DECISIONS.md").write_text(
        "| ID | Decision | Status |\n|---|---|---|\n" + "\n".join(rows) + "\n"
    )


def test_d082_is_reported_missing_until_it_is_written(tmp_path):
    write_decisions(
        tmp_path, ["| D081 | video | Accepted |", "| D083 | T16 dashboard | Accepted |"]
    )
    report = build_report(tmp_path, STAMP)
    assert "D082 is cited but not yet written" in report
    assert "D083" in report

    write_decisions(
        tmp_path,
        [
            "| D081 | video | Accepted |",
            "| D082 | potholes from P, cracks from B | Accepted |",
            "| D083 | T16 dashboard | Accepted |",
        ],
    )
    report = build_report(tmp_path, STAMP)
    assert "D082 is cited but not yet written" not in report
    assert "potholes from P, cracks from B" in report
    # Who took D083 stays true after D082 lands, so the note must not vanish with it.
    assert "D083 was taken by the session that ran T10–T17" in report


def test_the_video_annotator_comes_from_the_ground_truth_file(tmp_path):
    gt = tmp_path / "configs/eval/gt/clip_x.csv"
    gt.parent.mkdir(parents=True)
    gt.write_text(
        "# Potholes in clip_x\n# Annotator: Claude (AI), 2026-09-28, one pass.\n"
        "start_s,end_s,note\n"
    )
    v = tmp_path / "results/video/clip_x"
    v.mkdir(parents=True)
    (v / "gt_score.json").write_text(
        json.dumps(
            {
                "gt": {"path": "configs/eval/gt/clip_x.csv", "potholes": 3},
                "window_s": [0, 60],
                "models": {
                    m: {
                        "potholes": 3,
                        "hit": h,
                        "tracks_in_window": 4,
                        "duplicates": 0,
                        "false_alarms": f,
                        "false_alarms_per_min": f,
                        "median_frames_per_hit": 10.0,
                    }
                    for m, h, f in (("B", 1, 1), ("P", 2, 5))
                },
                "caveats": ["One annotator."],
            }
        )
    )
    report = build_report(tmp_path, STAMP)
    assert "Claude (AI), 2026-09-28, one pass." in report
    assert "| B | 1 of 3 |" in report and "| P | 2 of 3 |" in report
