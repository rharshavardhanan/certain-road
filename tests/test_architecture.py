"""The stage-isolation contract is part of the test suite, not just CI."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_import_contracts_hold():
    # cwd must be the repo root: import-linter reads .importlinter relative to it.
    # Resolved from __file__ rather than core.paths, which does not exist yet.
    result = subprocess.run(
        ["lint-imports"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"import-linter failed:\n{result.stdout}\n{result.stderr}"
