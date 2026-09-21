"""T2 — build the YOLO image pool, the split lists, and the split audit."""

import json
import sys
import time
from collections import Counter
from multiprocessing.pool import ThreadPool
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import raw_dir, repo_root  # noqa: E402
from certain_road.perception.dataset.convert import ID_TO_CLASS  # noqa: E402
from certain_road.perception.dataset.pool import (  # noqa: E402
    materialise_one,
    pool_name,
    sample_replay,
    split_india,
    split_india_grouped,
    split_nonindia,
    write_split_txt,
)

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
SPLIT, SEED = CFG["split"], CFG["seed"]
INDIA, NONINDIA = CFG["countries"]["india"], CFG["countries"]["nonindia"]
YOLO = repo_root() / CFG["paths"]["yolo"]
SPLITS = repo_root() / CFG["paths"]["splits"]


def country_stems(country: str) -> list[str]:
    xml_dir = raw_dir() / "RDD2022" / country / "train" / "annotations" / "xmls"
    img_dir = raw_dir() / "RDD2022" / country / "train" / "images"
    return sorted(p.stem for p in xml_dir.glob("*.xml") if (img_dir / f"{p.stem}.jpg").exists())


def main() -> int:
    images_dir, labels_dir = YOLO / "images", YOLO / "labels"
    for d in (images_dir, labels_dir, SPLITS):
        d.mkdir(parents=True, exist_ok=True)

    stems = {c: country_stems(c) for c in [INDIA, *NONINDIA]}
    for c, s in stems.items():
        print(f"{c:<18} {len(s):>6} annotated images", flush=True)

    # ---- splits -------------------------------------------------------------
    splits = split_nonindia(
        {c: stems[c] for c in NONINDIA}, val_frac=SPLIT["nonindia_val_frac"]
    )
    # D061: keep same-scene groups intact if the audit has produced them.
    groups_file = repo_root() / "results" / "T2" / "india_scene_groups.json"
    if groups_file.exists():
        groups = list(json.loads(groups_file.read_text())["groups"].values())
        print(f"D061: {len(groups)} scene groups held together", flush=True)
        splits.update(split_india_grouped(
            [pool_name(INDIA, s) for s in stems[INDIA]],
            fracs=SPLIT["india_fracs"], groups=groups,
        ))
    else:
        print("D061: no scene-group file; falling back to per-image split", flush=True)
        splits.update(split_india(stems[INDIA], fracs=SPLIT["india_fracs"]))
    splits["india_full"] = sorted(pool_name(INDIA, s) for s in stems[INDIA])
    splits["india_heldout"] = sorted(splits["india_cal"] + splits["india_test"])
    splits["nonindia_replay"] = sample_replay(
        splits["nonindia_train"], SPLIT["replay_n"], SEED
    )

    # ---- materialise --------------------------------------------------------
    jobs = [(c, s) for c in [INDIA, *NONINDIA] for s in stems[c]]
    rejected: Counter = Counter()
    resized_by_country: Counter = Counter()
    t0 = time.time()

    def work(job):
        c, s = job
        root = raw_dir() / "RDD2022" / c / "train"
        return c, materialise_one(
            country=c, stem=s,
            img_src=root / "images" / f"{s}.jpg",
            xml_src=root / "annotations" / "xmls" / f"{s}.xml",
            images_dir=images_dir, labels_dir=labels_dir,
            max_side=SPLIT["max_side"], min_box_px=SPLIT["min_box_px"],
        )

    with ThreadPool(8) as pool:
        for i, (c, (was_resized, rej)) in enumerate(pool.imap_unordered(work, jobs, 64), 1):
            rejected.update(rej)
            if was_resized:
                resized_by_country[c] += 1
            if i % 5000 == 0:
                print(f"  materialised {i}/{len(jobs)}  {(time.time()-t0)/60:.1f} min", flush=True)
    print(f"materialised {len(jobs)} in {(time.time()-t0)/60:.1f} min", flush=True)

    # ---- split lists --------------------------------------------------------
    for name, members in sorted(splits.items()):
        write_split_txt(members, YOLO / f"{name}.txt")
        write_split_txt(members, SPLITS / f"{name}.txt")

    # ---- data yamls ---------------------------------------------------------
    cfg_dir = repo_root() / "configs" / "data"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    def data_yaml(path, train, val):
        with open(path, "w") as fh:
            yaml.safe_dump(
                {"path": str(YOLO.resolve()), "train": train, "val": val,
                 "names": ID_TO_CLASS},
                fh, sort_keys=False,
            )

    data_yaml(cfg_dir / "model_a.yaml", "nonindia_train.txt", "nonindia_val.txt")
    data_yaml(cfg_dir / "model_b.yaml",
              ["india_train.txt", "nonindia_replay.txt"], "india_val.txt")
    # Ultralytics requires both keys even for a set we only ever evaluate on.
    for locked in ("india_full", "india_heldout", "india_test", "india_cal",
                   "india_train", "india_val", "nonindia_val"):
        data_yaml(cfg_dir / f"{locked}.yaml", f"{locked}.txt", f"{locked}.txt")

    # ---- audit --------------------------------------------------------------
    def stats(names):
        cls: Counter = Counter()
        backgrounds = 0
        for n in names:
            lines = (labels_dir / f"{n}.txt").read_text().split()
            ids = lines[0::5]
            if not ids:
                backgrounds += 1
            cls.update(int(i) for i in ids)
        return {"images": len(names), "backgrounds": backgrounds,
                "instances": {ID_TO_CLASS[k]: v for k, v in sorted(cls.items())},
                "total_instances": sum(cls.values())}

    audit = {k: stats(v) for k, v in sorted(splits.items())}
    india_pot = audit["india_full"]["instances"].get("pothole", 0)
    india_tot = audit["india_full"]["total_instances"]
    non_pot = audit["nonindia_train"]["instances"].get("pothole", 0) + \
        audit["nonindia_val"]["instances"].get("pothole", 0)
    non_tot = audit["nonindia_train"]["total_instances"] + \
        audit["nonindia_val"]["total_instances"]

    payload = {
        "salt": "roadsight-pool-v1", "seed": SEED, "split_config": SPLIT,
        "splits": audit,
        "rejected_boxes": dict(rejected.most_common()),
        "resized_images": dict(resized_by_country),
        "pothole_share": {"india": round(india_pot / india_tot, 4) if india_tot else 0,
                          "nonindia": round(non_pot / non_tot, 4) if non_tot else 0},
        "d10_note": "D00 and D10 are merged into linear_crack; India has only 68 "
                    "D10 instances (D037/D038/D055).",
    }
    out = repo_root() / "results" / "T2"
    out.mkdir(parents=True, exist_ok=True)
    (out / "split_audit.json").write_text(json.dumps(payload, indent=2))

    md = ["# T2 — split audit", "",
          f"Salt `roadsight-pool-v1`, seed {SEED}. India is split per image, not in "
          "blocks of 50 — see D059.", "",
          "| split | images | backgrounds | " +
          " | ".join(ID_TO_CLASS.values()) + " | total |",
          "|---" * (len(ID_TO_CLASS) + 4) + "|"]
    for k, v in audit.items():
        md.append(f"| {k} | {v['images']} | {v['backgrounds']} | " +
                  " | ".join(str(v["instances"].get(c, 0)) for c in ID_TO_CLASS.values()) +
                  f" | {v['total_instances']} |")
    md += ["", "## Pothole share", "",
           f"- India: **{payload['pothole_share']['india']:.1%}** of instances",
           f"- non-India: **{payload['pothole_share']['nonindia']:.1%}** of instances", "",
           "## D10", "", payload["d10_note"], "",
           "## Rejected boxes", ""]
    md += [f"- `{k}`: {v}" for k, v in rejected.most_common()] or ["- none"]
    md += ["", "## Resized images", "",
           f"`max_side` is {SPLIT['max_side']}; everything else is copied byte-for-byte.", ""]
    md += [f"- {k}: {v}" for k, v in resized_by_country.most_common()] or ["- none"]
    md += ["", "---", "",
           "Split fractions, the India/non-India pothole share and the visual-QA",
           "notes are in `findings.md` alongside this file. This file is generated",
           "by `scripts/build_pool.py` and is overwritten on every run;",
           "`findings.md` is authored and is not."]
    (out / "split_audit.md").write_text("\n".join(md) + "\n")

    print("\n" + "\n".join(md[4:4 + len(audit) + 2]))
    print(f"\nrejected: {dict(rejected.most_common(5))}")
    print(f"resized : {dict(resized_by_country)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
