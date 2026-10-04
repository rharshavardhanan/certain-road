"""T5 — poll a Kaggle kernel, then pull its output.

Kaggle gives no push notification, so this polls. On completion it downloads the
kernel output and prints `status.json` plus the tail of `results.csv`; on error
it fetches the log and shows the failure rather than leaving you to open a
browser.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
USER = CFG["kaggle"]["username"]
POLL_S = 600


def status(slug: str) -> str:
    out = subprocess.run(
        ["kaggle", "kernels", "status", f"{USER}/{slug}"], capture_output=True, text=True
    )
    return (out.stdout + out.stderr).strip()


def main() -> int:
    slug = sys.argv[1]
    dest = repo_root() / "runs" / "kaggle" / slug
    dest.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    while True:
        s = status(slug)
        print(f"[{(time.time() - t0) / 60:6.1f} min] {s}", flush=True)
        low = s.lower()
        if "complete" in low or "error" in low or "cancel" in low:
            break
        time.sleep(POLL_S)

    subprocess.run(["kaggle", "kernels", "output", f"{USER}/{slug}", "-p", str(dest)], check=False)
    for found in dest.rglob("status.json"):
        print("\n" + json.dumps(json.loads(found.read_text()), indent=2))
    for found in dest.rglob("results.csv"):
        lines = found.read_text().strip().splitlines()
        print(f"\n{found.name}: {len(lines) - 1} epochs")
        print("\n".join(lines[:1] + lines[-3:]))
    for found in dest.rglob("*.log"):
        print(f"\n--- {found.name} (tail) ---\n" + "\n".join(found.read_text().splitlines()[-30:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
