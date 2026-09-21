"""T3 — stage only what Kaggle needs, and nothing it must never see.

`india_cal` and `india_test` are **not uploaded**. Locked evaluation runs locally
on CPU, so the held-out images have no reason to leave this machine — and if they
never leave it, no Kaggle kernel can touch them by accident, misconfiguration or
a copy-pasted data yaml. The calibration firewall stops being a convention the
code has to honour and becomes a fact about where the bytes are.

Files are hard-linked, not copied: same filesystem, no second 4.6 GB.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO = repo_root() / CFG["paths"]["yolo"]
STAGE = repo_root() / "data" / "kaggle_upload"
UPLOAD_SPLITS = ["nonindia_train", "nonindia_val", "india_train", "india_val"]
WITHHELD_SPLITS = ["india_cal", "india_test", "india_heldout", "india_full", "nonindia_replay"]


def stems(split: str) -> list[str]:
    return [Path(x).stem for x in (YOLO / f"{split}.txt").read_text().splitlines() if x.strip()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if STAGE.exists():
        subprocess.run(["rm", "-rf", str(STAGE)], check=True)
    (STAGE / "images").mkdir(parents=True)
    (STAGE / "labels").mkdir(parents=True)

    withheld = {s for split in ("india_cal", "india_test") for s in stems(split)}
    upload: set[str] = set()
    for split in UPLOAD_SPLITS:
        upload.update(stems(split))
    assert not (upload & withheld), "held-out stems reached the upload set"

    for name in sorted(upload):
        os.link(YOLO / "images" / f"{name}.jpg", STAGE / "images" / f"{name}.jpg")
        os.link(YOLO / "labels" / f"{name}.txt", STAGE / "labels" / f"{name}.txt")

    # nonindia_replay is a subset of nonindia_train, so Model B can still use it
    # without india_cal/test ever being present.
    for split in [*UPLOAD_SPLITS, "nonindia_replay"]:
        (STAGE / f"{split}.txt").write_text((YOLO / f"{split}.txt").read_text())

    manifest = {
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                     text=True, check=True).stdout.strip(),
        "uploaded_splits": {s: len(stems(s)) for s in [*UPLOAD_SPLITS, "nonindia_replay"]},
        "uploaded_images": len(upload),
        "withheld": {
            "reason": "held-out India never leaves the local machine (D062); "
                      "locked evaluation runs locally on CPU",
            "splits": {s: len(stems(s)) for s in WITHHELD_SPLITS},
            "withheld_images": len(withheld),
        },
        "split_sha256": {s: sha256(STAGE / f"{s}.txt")
                         for s in [*UPLOAD_SPLITS, "nonindia_replay"]},
        "classes": CFG["classes"],
    }
    (STAGE / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"staged   {len(upload):,} images -> {STAGE}")
    print(f"withheld {len(withheld):,} india_cal + india_test images (never uploaded)")
    for s, n in manifest["uploaded_splits"].items():
        print(f"  {s:<18} {n:>6}")
    leaked = [p.stem for p in (STAGE / "images").glob("*.jpg") if p.stem in withheld]
    print(f"\nheld-out stems present in staging: {len(leaked)}  (must be 0)")
    return 0 if not leaked else 1


if __name__ == "__main__":
    raise SystemExit(main())
