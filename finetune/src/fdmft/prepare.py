"""Image normalization, manifest and de-duplication.

`prepare` is incremental: images already in the manifest (same source and key) are skipped, so it can run again
after more sources are downloaded. `dedup` rewrites `interim/dedup.json` from scratch.
"""
from __future__ import annotations

import hashlib
import io
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial

import imagehash
from PIL import Image, ImageOps

from fdmft.config import DATA, IMAGES, INTERIM, MANIFEST
from fdmft.download import log
from fdmft.sources import RawItem, Source, effective_license, iter_items, registry
from fdmft.taxonomy import load as load_taxonomy
from fdmft.taxonomy import map_labels

MAX_SIDE = 1280      # longest side stored (= a P1S frame); beyond that no useful token budget needs more
MIN_SIDE = 224       # smaller images are dropped
JPEG_QUALITY = 95
DEDUP_FILE = INTERIM / "dedup.json"


def item_id(source: str, key: str) -> str:
    return hashlib.sha1(f"{source}\x00{key}".encode()).hexdigest()[:16]


def read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    with MANIFEST.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def normalize(data: bytes) -> tuple[Image.Image, tuple[int, int]]:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    orig = img.size
    if img.mode != "RGB":
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    return img, orig


def _process(src: Source, license_: str, item: RawItem) -> dict:
    iid = item_id(item.source, item.key)
    base = {"id": iid, "source": item.source, "key": item.key, "group_id": item.group_id}
    try:
        img, orig = normalize(item.load())
    except Exception as exc:  # noqa: BLE001 - an unreadable file must not stop the rest
        return base | {"status": "error", "error": str(exc)[:200]}
    if min(orig) < MIN_SIDE:
        return base | {"status": "too_small", "orig_size": list(orig)}
    rel = f"images/{iid[:2]}/{iid}.jpg"
    out = INTERIM / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=JPEG_QUALITY)
    labels, review, unknown = map_labels(item.raw_labels)
    status = "ok"
    if unknown:
        status = "unknown_label"
    elif review or not labels:
        status = "review_label"
    return base | {
        "status": status,
        "path": str(out.relative_to(DATA)),
        "license": license_,
        "use": src.use,
        "raw_labels": item.raw_labels,
        "labels": labels,
        "review_labels": review,
        "unknown_labels": unknown,
        "size": list(img.size),
        "orig_size": list(orig),
        "phash": str(imagehash.phash(img)),
        "meta": item.meta,
    }


def prepare(source_ids: list[str] | None = None, workers: int = 8) -> Counter:
    srcs = registry()
    ids = source_ids or [s for s in srcs if (srcs[s].raw_dir / "download.json").exists()]
    seen = {(r["source"], r["key"]) for r in read_manifest()}
    IMAGES.mkdir(parents=True, exist_ok=True)
    stats: Counter = Counter()
    with MANIFEST.open("a") as fh, ThreadPoolExecutor(workers) as pool:
        for sid in ids:
            src = srcs[sid]
            if not (src.raw_dir / "download.json").exists():
                log(f"{sid}: not downloaded, skipped")
                continue
            lic = effective_license(src)
            todo = [it for it in iter_items(src) if (it.source, it.key) not in seen]
            log(f"{sid}: {len(todo)} new images (licence {lic}, use {src.use})")
            for n, rec in enumerate(pool.map(partial(_process, src, lic), todo), 1):
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                stats[(sid, rec["status"])] += 1
                if n % 1000 == 0:
                    fh.flush()
                    log(f"  {sid}: {n}/{len(todo)}")
    for (sid, status), n in sorted(stats.items()):
        log(f"{sid:28s} {status:14s} {n}")
    return stats


# --- dedup ------------------------------------------------------------------------------------------

@dataclass
class _UF:
    parent: dict[str, str]

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def near_duplicate_groups(hashes: dict[str, str], max_distance: int = 4, max_bucket: int = 5000,
                          can_merge: Callable[[str, str, int], bool] | None = None) -> list[list[str]]:
    """Groups of images whose pHash Hamming distance is <= `max_distance`.

    Banded LSH: with 8 bands of 8 bits and distance <= 7 at least one band matches (pigeonhole), so only pairs
    sharing a band are compared. `can_merge(a, b, distance)` can veto a pair.
    """
    if max_distance > 7:
        raise ValueError("max_distance <= 7 with 8 bands")
    ints = {k: int(v, 16) for k, v in hashes.items()}
    buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
    for k, h in ints.items():
        for band in range(8):
            buckets[(band, (h >> (8 * band)) & 0xFF)].append(k)
    uf = _UF({k: k for k in ints})
    for members in buckets.values():
        if len(members) < 2:
            continue
        members = members[:max_bucket]
        for i, a in enumerate(members):
            ha = ints[a]
            for b in members[i + 1:]:
                dist = (ha ^ ints[b]).bit_count()
                if dist <= max_distance and (can_merge is None or can_merge(a, b, dist)):
                    uf.union(a, b)
    groups: dict[str, list[str]] = defaultdict(list)
    for k in ints:
        groups[uf.find(k)].append(k)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def _rank(rec: dict, order: dict[str, int], train_licenses: frozenset[str]) -> tuple:
    trainable = rec.get("use") == "train" and rec.get("license") in train_licenses
    w, h = rec.get("orig_size", [0, 0])
    return (not trainable, order.get(rec["source"], 99), -(w * h), rec["id"])


def dedup(max_distance: int = 4, within_source_distance: int = 0) -> dict:
    """Near-duplicates: across different sources at distance <= `max_distance`; inside the same source only at
    distance <= `within_source_distance` and with the same labels.

    Inside a source, nearly identical images with different labels are the signal itself (calibration blocks
    under/optimal/over, frames of one print with and without stringing): pHash cannot see fine textures, and a
    threshold of 4 inside the sources would drop more than half of the data.
    """
    tax = load_taxonomy()
    recs = {r["id"]: r for r in read_manifest() if r.get("phash")}
    order = {sid: i for i, sid in enumerate(registry())}

    def can_merge(a: str, b: str, dist: int) -> bool:
        ra, rb = recs[a], recs[b]
        if ra["source"] != rb["source"]:
            return True
        return dist <= within_source_distance and ra.get("labels") == rb.get("labels")

    groups = near_duplicate_groups({k: r["phash"] for k, r in recs.items()}, max_distance, can_merge=can_merge)
    dropped: dict[str, str] = {}
    conflicts = []
    cross = Counter()
    for g in groups:
        ranked = sorted(g, key=lambda k: _rank(recs[k], order, tax.licenses_train))
        keep = ranked[0]
        for k in ranked[1:]:
            # by transitivity a group can join images of the same source with different labels: keep those
            if recs[k]["source"] != recs[keep]["source"] or recs[k].get("labels") == recs[keep].get("labels"):
                dropped[k] = keep
        label_sets = {tuple(recs[k].get("labels", [])) for k in g}
        if len(label_sets) > 1:
            conflicts.append({"keep": keep, "members": g, "labels": sorted(map(list, label_sets))})
        srcs = sorted({recs[k]["source"] for k in g})
        if len(srcs) > 1:
            cross["/".join(srcs)] += 1
    result = {"max_distance": max_distance, "within_source_distance": within_source_distance, "groups": len(groups),
              "dropped": dropped, "label_conflicts": conflicts, "cross_source_groups": dict(cross)}
    DEDUP_FILE.write_text(json.dumps(result, indent=1))
    log(f"dedup: {len(groups)} groups, {len(dropped)} images dropped, {len(conflicts)} groups with conflicting labels")
    for k, v in cross.most_common():
        log(f"  across sources {k}: {v} groups")
    return result


def dropped_ids() -> set[str]:
    if not DEDUP_FILE.exists():
        return set()
    return set(json.loads(DEDUP_FILE.read_text())["dropped"])


def usable(records: Iterable[dict]) -> list[dict]:
    """Records with a stored image that the dedup did not drop."""
    drop = dropped_ids()
    return [r for r in records if r.get("path") and r["id"] not in drop]
