"""Source registry (configs/sources.yaml) and parsers that derive labels and groups from the downloaded files.

Every parser yields `RawItem`s: one image with its original labels and the `group_id` used for the splits
(images of the same group never end up in different splits).
"""
from __future__ import annotations

import csv
import fnmatch
import io
import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from fdmft.config import CONFIGS, RAW

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class Source:
    id: str
    kind: str          # kaggle | roboflow | huggingface
    ref: str
    license: str
    use: str           # train | eval
    parser: str
    exclude: tuple[str, ...] = ()
    export_format: str = "coco"
    citation: str = ""

    @property
    def raw_dir(self) -> Path:
        return RAW / self.id

    @property
    def files_dir(self) -> Path:
        return self.raw_dir / "files"


@dataclass
class RawItem:
    source: str
    key: str                               # stable id inside the source (relative path)
    raw_labels: list[str]
    group_id: str
    load: Callable[[], bytes]              # reads the bytes of the original image
    meta: dict = field(default_factory=dict)


@lru_cache(maxsize=1)
def registry() -> dict[str, Source]:
    data = yaml.safe_load((CONFIGS / "sources.yaml").read_text())
    out = {}
    for sid, cfg in data["sources"].items():
        cfg = dict(cfg)
        cfg["exclude"] = tuple(cfg.get("exclude", ()))
        out[sid] = Source(id=sid, **cfg)
    return out


def effective_license(src: Source) -> str:
    """Licence recorded at download time (Roboflow declares it through the API), otherwise the registry one."""
    info = src.raw_dir / "download.json"
    if info.exists():
        lic = json.loads(info.read_text()).get("license")
        if lic:
            return lic
    return src.license


def _images(root: Path, exclude: tuple[str, ...]) -> Iterator[Path]:
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() in IMAGE_EXTS and p.is_file():
            if any(fnmatch.fnmatch(p.name, pat) for pat in exclude):
                continue
            yield p


def _file_item(src: Source, path: Path, labels: list[str], group: str, **meta) -> RawItem:
    return RawItem(source=src.id, key=str(path.relative_to(src.files_dir)), raw_labels=labels,
                   group_id=f"{src.id}:{group}", load=path.read_bytes, meta=meta)


# --- parsers --------------------------------------------------------------------------------------

def parse_folder_class(src: Source) -> Iterator[RawItem]:
    """Label = folder that contains the image. Group = class (refined later for wengmhu, see build.py)."""
    for p in _images(src.files_dir, src.exclude):
        label = p.parent.name
        if label.lower() in {"train", "valid", "test", "images"}:
            continue
        yield _file_item(src, p, [label], label)


def parse_filename_prefix(src: Source) -> Iterator[RawItem]:
    """`defected/<type>_<n>.jpg` -> label from the prefix; `no_defected/...` -> label from the folder."""
    for p in _images(src.files_dir, src.exclude):
        folder = p.parent.name
        prefix = re.sub(r"[_\-]?\d+$", "", p.stem)
        negative = re.match(r"^no[nt]?[_\- ]?defect", folder.lower()) is not None
        label = folder if negative or not prefix else prefix
        yield _file_item(src, p, [label], label)


# From the dataset README: 0 Good, 1 Under-Extrusion, 2 Stringing, 4 Spaghetti (3 does not exist).
NIMBUS_CLASSES = {"0": "good", "1": "under_extrusion", "2": "stringing", "4": "spaghetti"}


def parse_nimbus200(src: Source) -> Iterator[RawItem]:
    """CSV `all_images_no_filter.csv` (";"-separated): image, class, layer, ex_mul, shape, recording, ...

    Group = recording (one print): frames of the same print are nearly identical.
    """
    csvs = list(src.files_dir.rglob("all_images_no_filter.csv"))
    if not csvs:
        raise FileNotFoundError(f"{src.id}: all_images_no_filter.csv not found")
    by_name = {p.name: p for p in _images(src.files_dir, src.exclude)}
    with csvs[0].open(newline="") as fh:
        dialect = csv.Sniffer().sniff(fh.readline(), delimiters=";,\t")
        fh.seek(0)
        for row in csv.DictReader(fh, dialect=dialect):
            name = Path(row["image"]).name
            path = by_name.get(name)
            if path is None:
                continue
            label = NIMBUS_CLASSES.get(str(row.get("class", "")).strip())
            if label is None:
                continue
            meta = {k: row[k] for k in ("layer", "ex_mul", "retraction", "filament_color", "shape", "printbed_color")
                    if row.get(k)}
            meta["subset"] = path.parent.name
            yield _file_item(src, path, [label], row.get("recording") or path.parent.name, **meta)


MMANDREW_CLASSES = {"100": "under_extrude", "010": "optimal", "001": "over_extrude"}


def parse_mmandrew(src: Source) -> Iterator[RawItem]:
    """`<id>_<100|010|001>.png` in close_/far_flowrate_dataset. Group = block id (close and far view)."""
    for p in _images(src.files_dir, src.exclude):
        m = re.fullmatch(r"(\d+)_(\d{3})", p.stem)
        if not m or m.group(2) not in MMANDREW_CLASSES:
            continue
        yield _file_item(src, p, [MMANDREW_CLASSES[m.group(2)]], m.group(1), view=p.parent.name)


def parse_coco(src: Source) -> Iterator[RawItem]:
    """Roboflow COCO export: image labels = categories of its boxes (multi-label).

    Without annotations the image is labelled `unlabeled` (to review: in Roboflow it is often a negative).
    """
    for ann_file in sorted(src.files_dir.rglob("_annotations.coco.json")):
        data = json.loads(ann_file.read_text())
        cats = {c["id"]: c["name"] for c in data.get("categories", [])}
        by_image: dict[int, list[dict]] = {}
        for a in data.get("annotations", []):
            by_image.setdefault(a["image_id"], []).append(a)
        for img in data.get("images", []):
            path = ann_file.parent / img["file_name"]
            if not path.exists():
                continue
            anns = by_image.get(img["id"], [])
            # Category 0 in Roboflow exports is the project supercategory, not a defect.
            labels = sorted({cats[a["category_id"]] for a in anns if a["category_id"] in cats and a["category_id"] != 0})
            boxes = [{"label": cats.get(a["category_id"]), "bbox": a["bbox"]} for a in anns]
            yield _file_item(src, path, labels or ["unlabeled"], "project", split=ann_file.parent.name,
                             width=img.get("width"), height=img.get("height"), boxes=boxes)


def parse_hf_binary(src: Source) -> Iterator[RawItem]:
    """Hugging Face parquet with columns `image` ({bytes, path}) and `label` (ClassLabel in the README)."""
    import pyarrow.parquet as pq

    names = _hf_label_names(src.files_dir / "README.md")
    for pf in sorted(src.files_dir.rglob("*.parquet")):
        table = pq.read_table(pf, columns=["image", "label"])
        for i, row in enumerate(table.to_pylist()):
            data = row["image"]["bytes"]
            label = names.get(row["label"], str(row["label"]))
            yield RawItem(source=src.id, key=f"{pf.relative_to(src.files_dir)}#{i}", raw_labels=[label],
                          group_id=f"{src.id}:{label}", load=(lambda d=data: d), meta={"split": pf.parent.name})


def _hf_label_names(readme: Path) -> dict[int, str]:
    if not readme.exists():
        return {}
    text = readme.read_text()
    front = text.split("---")[1] if text.startswith("---") else ""
    info = yaml.safe_load(io.StringIO(front)) or {}
    for feat in info.get("dataset_info", {}).get("features", []):
        names = feat.get("dtype", {}).get("class_label", {}).get("names") if isinstance(feat.get("dtype"), dict) else None
        if feat.get("name") == "label" and names:
            return {int(k): v for k, v in names.items()}
    return {}


PARSERS: dict[str, Callable[[Source], Iterator[RawItem]]] = {
    "folder_class": parse_folder_class,
    "filename_prefix": parse_filename_prefix,
    "nimbus200": parse_nimbus200,
    "mmandrew": parse_mmandrew,
    "coco": parse_coco,
    "hf_binary": parse_hf_binary,
}


RF_SUFFIX = re.compile(r"\.rf\.[0-9a-f]{16,}$")
SPLIT_PREFERENCE = {"valid": 0, "test": 1, "train": 2}   # Roboflow applies augmentation to the train split only


def roboflow_stem(key: str) -> str:
    """`train/<original>_jpg.rf.<hash>.jpg` -> `<original>_jpg`: export and augmentation copies share the stem."""
    return RF_SUFFIX.sub("", Path(key).stem)


def one_per_original(items: Iterator[RawItem]) -> Iterator[RawItem]:
    """One image per Roboflow original: prefers valid/test (never augmented), then the first in order.

    Roboflow exports contain up to 100 copies of the same original (x3 augmentation with vertical flips and
    rotations, crops, merged forks). The stem also becomes the group for the splits.
    """
    best: dict[str, RawItem] = {}
    rank: dict[str, tuple] = {}
    copies: dict[str, int] = defaultdict(int)
    for it in items:
        stem = roboflow_stem(it.key)
        copies[stem] += 1
        split = Path(it.key).parts[0]
        r = (SPLIT_PREFERENCE.get(split, 3), it.key)
        if stem not in best or r < rank[stem]:
            best[stem], rank[stem] = it, r
    for stem, it in best.items():
        it.group_id = f"{it.source}:{stem}"
        it.meta["copies"] = copies[stem]
        yield it


def iter_items(src: Source) -> Iterator[RawItem]:
    items = PARSERS[src.parser](src)
    return one_per_original(items) if src.kind == "roboflow" else items
