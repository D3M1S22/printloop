"""Training dataset: final labels, sub-sampling, group splits, JSONL.

- the label is the one of the dataset;
- only `use: train` sources with an allowed licence, images with status `ok` (no labels left to review);
- `nimbus200`: at most `max_per_group` evenly spaced frames per recording (they are nearly identical);
- group split with a deterministic hash: test 10%, val 5% of the groups;
- `wengmhu` has no print metadata: its groups are the sessions derived from the timestamp in the file name;
- train balanced with a cap per primary class (sampling without repetition).

The build is deterministic: the same manifest gives the same splits (seeded shuffles, hashed groups).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from fdmft.config import PROCESSED
from fdmft.download import log
from fdmft.prepare import read_manifest, usable
from fdmft.sources import effective_license, registry
from fdmft.taxonomy import load as load_taxonomy

TS = re.compile(r"(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})")
SESSION_GAP_S = 600


def session_groups(records: list[dict], gap_s: int = SESSION_GAP_S) -> dict[str, str]:
    """id -> session group: photos less than `gap_s` seconds after the previous one belong to the same print."""
    stamped = []
    for r in records:
        m = TS.search(Path(r["key"]).name)
        if m:
            stamped.append((datetime(*map(int, m.groups())), r["id"]))
    stamped.sort()
    out, session, last = {}, 0, None
    for t, iid in stamped:
        if last is not None and (t - last).total_seconds() > gap_s:
            session += 1
        out[iid] = f"session{session:04d}"
        last = t
    return out


def split_of(group_id: str, test: float = 0.10, val: float = 0.05) -> str:
    h = int(hashlib.sha1(group_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if h < test else "val" if h < test + val else "train"


def build(build_id: str, max_per_group: dict[str, int] | None = None, class_cap: int = 2000, seed: int = 0) -> Path:
    tax = load_taxonomy()
    srcs = registry()
    max_per_group = {"kaggle_nimbus200": 25} if max_per_group is None else max_per_group
    allowed = {sid for sid, s in srcs.items() if s.use == "train" and effective_license(s) in tax.licenses_train}
    recs = [r for r in usable(read_manifest())
            if r["source"] in allowed and r["status"] == "ok" and r.get("labels")]
    log(f"build {build_id}: {len(recs)} candidate images from {sorted(allowed)}")

    # wengmhu groups from the capture sessions
    weng = [r for r in recs if r["source"] == "kaggle_wengmhu"]
    sess = session_groups(weng)
    for r in weng:
        r["group_id"] = f"kaggle_wengmhu:{sess.get(r['id'], r['id'])}"

    # per-group sub-sampling (evenly spaced frames, sorted by layer or key)
    by_group: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_group[r["group_id"]].append(r)
    kept = []
    for items in by_group.values():
        cap = max_per_group.get(items[0]["source"])
        if cap and len(items) > cap:
            items = sorted(items, key=lambda r: (int(r["meta"].get("layer", 0) or 0), r["key"]))
            step = len(items) / cap
            items = [items[int(i * step)] for i in range(cap)]
        kept.extend(items)

    rows = {"train": [], "val": [], "test": []}
    for r in kept:
        defects = [d for d in r["labels"] if d != "none"]
        rows[split_of(r["group_id"])].append({
            "id": r["id"], "image": r["path"], "defects": tax.sort(defects),   # relative to FDMFT_DATA_DIR
            "primary": tax.primary(defects), "source": r["source"], "group": r["group_id"],
        })

    # cap per primary class in the train split
    rng = random.Random(seed)
    by_primary: dict[str, list[dict]] = defaultdict(list)
    for row in rows["train"]:
        by_primary[row["primary"]].append(row)
    train = []
    for _cls, items in sorted(by_primary.items()):
        rng.shuffle(items)
        train.extend(items[:class_cap])
    rng.shuffle(train)
    rows["train_full"], rows["train"] = rows["train"], train

    out = PROCESSED / build_id
    out.mkdir(parents=True, exist_ok=True)
    stats = {"build_id": build_id, "created_at": datetime.now().isoformat(timespec="seconds"),
             "class_cap": class_cap, "max_per_group": max_per_group, "sources": sorted(allowed)}
    for split, items in rows.items():
        with (out / f"{split}.jsonl").open("w") as fh:
            for row in items:
                fh.write(json.dumps(row) + "\n")
        stats[split] = {"n": len(items), "groups": len({i["group"] for i in items}),
                        "primary": dict(Counter(i["primary"] for i in items).most_common()),
                        "source": dict(Counter(i["source"] for i in items).most_common())}
        log(f"  {split:10s} {len(items):6d} images, {stats[split]['groups']} groups")
    (out / "stats.json").write_text(json.dumps(stats, indent=1))
    return out
