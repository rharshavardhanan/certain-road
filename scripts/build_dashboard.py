"""T16 — build the offline dashboard: one self-contained HTML file (D020).

Reads result files only. The allocation view's slider selects among plans the
real T12 optimiser computes here, at every budget step, for both objectives.
Output: results/dashboard/index.html — double-click to open; no server, no network.
"""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.dashboard.render import build_page  # noqa: E402


def main() -> int:
    root = repo_root()
    commit = (
        subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root
        ).stdout.strip()
        or "unknown"
    )
    stamp = {"utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "commit": commit}
    worst_k = yaml.safe_load((root / "configs/project.yaml").read_text())["allocation"]["worst_k"]
    page = build_page(root, stamp, worst_k=int(worst_k))
    out = root / "results" / "dashboard" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
