"""REPO-MAP.md is generated; these pin the extraction it stands on.

Five of its sections (pipeline, entry points, task status, what is left, how to
reproduce) are derived from one table: what each script reads and writes. A path
classified the wrong way corrupts all five silently, so the classification is
pinned here on the path shapes the scripts actually use. None of these tests runs
the full build, which runs pytest itself.
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from repo_map import (  # noqa: E402
    Status,
    decision_gaps,
    derive_status,
    drop_sections,
    first_sentence,
    matches,
    producer_of,
    script_io,
    sources_in,
    stale_lines,
)

SCRIPT = '''
"""T12 — demo."""
import json
import yaml

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
OUT = repo_root() / "results" / "T12"


def main():
    table = json.loads((repo_root() / "results/T10/conformal.json").read_text())
    k = CFG["allocation"]["worst_k"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "allocation.json").write_text(json.dumps(table))
    plt.savefig(OUT / "fig.png")
    for slug in ("a", "b"):
        (repo_root() / f"results/T5/{slug}_verification.json").write_text("x")
    r.need("Drift", "results/T11/drift.json")
'''


def test_joined_paths_are_classified_by_what_is_done_to_them():
    io = script_io(SCRIPT)
    assert io["writes"] == [
        "results/T12/allocation.json",
        "results/T12/fig.png",
        "results/T5/*_verification.json",
    ]
    assert io["reads"] == [
        "configs/project.yaml",
        "results/T10/conformal.json",
        "results/T11/drift.json",
    ]


def test_a_base_directory_is_neither_a_read_nor_a_separate_write():
    io = script_io(SCRIPT)
    assert "results/T12" not in io["reads"]
    assert "results/T12" not in io["writes"]


def test_a_directory_made_with_nothing_parsed_into_it_is_still_a_write():
    io = script_io('OUT = root / "runs" / "t4"\nOUT.mkdir(parents=True)\n')
    assert io["writes"] == ["runs/t4"]


def test_each_function_resolves_its_own_variables():
    io = script_io(
        "def report(root):\n"
        '    out = root / "results" / "RESULTS.md"\n'
        "    out.write_text('x')\n"
        "def other(root):\n"
        '    out = root / "results" / "T1" / "raw_audit.json"\n'
        "    return out.read_text()\n"
    )
    assert io["writes"] == ["results/RESULTS.md"]
    assert io["reads"] == ["results/T1/raw_audit.json"]


def test_a_variable_merely_named_like_a_root_is_not_the_repository():
    io = script_io(
        'def f(data_root, split):\n    return (data_root / split / "images").glob("*")\n'
    )
    assert io["reads"] == [] and io["writes"] == []


def test_wrappers_and_conditionals_do_not_hide_a_write():
    io = script_io(
        'LOCKED = repo_root() / "results" / "LOCKED"\n'
        'p.add_argument("--out", default=str(repo_root() / "results" / "T9"))\n'
        "def main(args):\n"
        "    d = args.out if args.self_test else LOCKED\n"
        '    (d / f"{args.model}.json").write_text("x")\n'
    )
    assert io["writes"] == ["results/LOCKED/*.json", "results/T9"]


def test_config_values_and_path_helpers_are_followed():
    project = yaml.safe_load((ROOT / "configs" / "project.yaml").read_text())
    io = script_io(
        'YOLO = repo_root() / CFG["paths"]["yolo"]\n'
        '(YOLO / "x.txt").read_text()\n'
        'list((raw_dir() / "RDD2022").glob("*"))\n'
    )
    assert io["reads"] == ["data/raw/RDD2022", f"{project['paths']['yolo']}/x.txt"]


def test_a_glob_never_matches_across_a_directory_boundary():
    assert matches("results/T9/x.json", "results/T9/*")
    assert matches("runs/kaggle/b/export/best.pt", "runs/kaggle/*")
    assert not matches("results/LOCKED/A_run/val/predictions.json", "results/LOCKED/*.json")


def test_a_file_contains_nothing():
    assert not matches("results/RESULTS.md", "results/*/val")
    assert matches("results/T6_A_nonindia_val/val", "results/*/val")


def test_config_subscripts_become_dotted_keys():
    assert script_io(SCRIPT)["config_keys"] == ["allocation.worst_k"]


def test_argparse_arguments_with_required_flags_and_defaults():
    io = script_io(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        'p.add_argument("--model", required=True, choices=["A", "B"])\n'
        'p.add_argument("--conf", type=float, default=0.25)\n'
        'p.add_argument("video")\n'
    )
    assert [(a["name"], a["required"], a["default"]) for a in io["args"]] == [
        ("--model", True, None),
        ("--conf", False, "0.25"),
        ("video", True, None),
    ]


def test_status_is_derived_from_which_expected_paths_exist():
    assert derive_status({"a": True, "b": True}) is Status.DONE
    assert derive_status({"a": True, "b": False}) is Status.PARTIAL
    assert derive_status({"a": False}) is Status.NOT_RUN
    assert derive_status({}) is Status.UNKNOWN


def test_first_sentence_of_a_docstring():
    assert (
        first_sentence("T4 — can this Mac train, and does MPS agree with CPU?\n\nMore.")
        == "T4 — can this Mac train, and does MPS agree with CPU?"
    )
    assert first_sentence("Write fixtures to runs/synthetic/ for manual runs. More.") == (
        "Write fixtures to runs/synthetic/ for manual runs."
    )
    assert first_sentence(None) == "no docstring"


def test_cited_but_absent_and_written_but_uncommitted_decisions():
    absent, uncommitted = decision_gaps(
        cited={"D001": ["a.py"], "D082": ["b.py"], "D999": ["c.py"]},
        defined_now={"D001", "D082"},
        defined_at_head={"D001"},
    )
    assert absent == {"D999": ["c.py"]}
    assert uncommitted == ["D082"]


def test_a_rebuild_that_differs_only_in_its_stamp_line_is_fresh():
    committed = "# R\nGenerated at 10:00, commit abc\nrow 1\nrow 2\n"
    rebuilt = "# R\nGenerated at 11:30, commit def\nrow 1\nrow 2\n"
    assert stale_lines(committed, rebuilt, r"^Generated at") == []


def test_a_changed_row_is_stale_and_named():
    committed = "Generated at 10:00\n| D082 | old | Accepted |\n"
    rebuilt = "Generated at 11:30\n| D082 | new | Accepted · T12 re-run Open |\n"
    assert stale_lines(committed, rebuilt, r"^Generated at") == [
        "-| D082 | old | Accepted |",
        "+| D082 | new | Accepted · T12 re-run Open |",
    ]


def test_excepted_sections_are_dropped_up_to_the_next_heading():
    text = "# R\nintro\n## Video (lane)\nv1\nv2\n## Decision log status\nd1\n## Allocation\na1\n"
    kept = drop_sections(text, ["## Video", "## Decision log"])
    assert kept == "# R\nintro\n## Allocation\na1"


def test_a_result_file_is_attributed_through_a_glob_or_not_at_all():
    produced_by = {"results/LOCKED/*_run/val/predictions.json": "eval_locked.py"}
    assert producer_of("results/LOCKED/B_india_heldout_run/val/predictions.json", produced_by) == (
        "eval_locked.py"
    )
    assert producer_of("results/LOCKED/B_india_heldout.json", produced_by) is None


def test_sources_named_by_a_generated_markdown_or_html_file():
    text = (
        "Source: `results/T12/allocation.json`\n"
        "Source: `results/T2/a.json`, `results/T9/b.json`\n"
        '<p class="src">Source: <code>results/T12/demo_network.json</code></p>\n'
        "Source: `results/T13` (missing)\n"
    )
    assert sources_in(text) == [
        "results/T12/allocation.json",
        "results/T12/demo_network.json",
        "results/T13",
        "results/T2/a.json",
        "results/T9/b.json",
    ]
