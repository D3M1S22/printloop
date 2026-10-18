"""Mode 1 taxonomy and mapping of the source labels (configs/taxonomy.yaml)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import yaml

from fdmft.config import CONFIGS

REVIEW = "review"   # label that needs a decision: the image is kept in the manifest but not used for training
IGNORE = "ignore"   # object label (e.g. "part"): not a defect, does not change the labels


@dataclass(frozen=True)
class Taxonomy:
    classes: dict[str, str]          # code -> description (English, for the prompt)
    order: tuple[str, ...]           # canonical order of the defects in the output (without "none")
    label_map: dict[str, str | None]
    licenses_train: frozenset[str]
    licenses_eval: frozenset[str]

    def sort(self, defects: set[str] | list[str]) -> list[str]:
        """Unique defects in the canonical order; `none` and unknown classes are dropped."""
        present = set(defects)
        return [d for d in self.order if d in present]

    def primary(self, defects: list[str]) -> str:
        ordered = self.sort(defects)
        return ordered[0] if ordered else "none"


def normalize_label(raw: str) -> str:
    """'Layer Shifting' / 'layer-shifting' / 'LAYER_SHIFTING' -> 'layer_shifting'."""
    return re.sub(r"[\s\-]+", "_", raw.strip().lower()).strip("_")


@lru_cache(maxsize=1)
def load() -> Taxonomy:
    data = yaml.safe_load((CONFIGS / "taxonomy.yaml").read_text())
    classes = {k: v["description"] for k, v in data["classes"].items()}
    order = tuple(data["order"])
    unknown = [c for c in order if c not in classes]
    if unknown:
        raise ValueError(f"taxonomy.yaml: classes in `order` are not defined: {unknown}")
    lic = data["licenses"]
    return Taxonomy(
        classes=classes,
        order=order,
        label_map={normalize_label(k): v for k, v in data["label_map"].items()},
        licenses_train=frozenset(lic["allowed_for_training"]),
        licenses_eval=frozenset(lic["eval_only"]),
    )


def map_labels(raw_labels: list[str], tax: Taxonomy | None = None) -> tuple[list[str], list[str], list[str]]:
    """Source labels -> (classes, labels to review, unknown labels). `none` appears only if no defect does."""
    tax = tax or load()
    classes: set[str] = set()
    review: list[str] = []
    unknown: list[str] = []
    for raw in raw_labels:
        key = normalize_label(raw)
        if key not in tax.label_map:
            unknown.append(raw)
            continue
        target = tax.label_map[key]
        if target == IGNORE:
            continue
        if target == REVIEW:
            review.append(raw)
        elif target:
            classes.add(target)
    defects = tax.sort(classes)
    if not defects and "none" in classes:
        return ["none"], review, unknown
    return defects, review, unknown
