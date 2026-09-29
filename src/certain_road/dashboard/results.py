"""Read-only access to result files. A missing input is "not run", never an error.

The dashboard runs no training and no inference; it shows what the experiments
wrote. Several of them have not run (T13 has no results, T14 has produced no edge
database), and a view that crashed or rendered an empty table on a missing file
would make "not run" indistinguishable from "ran and found nothing". So every
read goes through `load_json`, which returns the data or a `NotRun` naming the
file it looked for.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NotRun:
    path: Path
    reason: str

    def __str__(self) -> str:
        return f"not run ({self.path}: {self.reason})"


def load_json(path: Path) -> dict | list | NotRun:
    if not path.exists():
        return NotRun(path, "missing")
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return NotRun(path, f"unreadable: {e}")


def existing(path: Path) -> Path | NotRun:
    """A figure or database that is either there or not run."""
    return path if path.exists() else NotRun(path, "missing")
