"""Image-level multi-label metrics."""
from __future__ import annotations

from collections import Counter


def evaluate(rows: list[dict], classes: tuple[str, ...], min_support: int = 20) -> dict:
    """rows: {"gold": [...], "pred": [...], "valid": bool, "source": str}. Empty lists mean `none`."""
    tp, fp, fn, support = Counter(), Counter(), Counter(), Counter()
    exact = valid = primary_ok = 0
    bin_fp = bin_neg = bin_tp = bin_pos = 0
    for r in rows:
        g, p = set(r["gold"]), set(r["pred"])
        valid += r["valid"]
        exact += g == p
        primary_ok += (r["gold"][:1] or ["none"]) == (r["pred"][:1] or ["none"])
        for c in classes:
            support[c] += c in g
            tp[c] += c in g and c in p
            fp[c] += c in p and c not in g
            fn[c] += c in g and c not in p
        if g:
            bin_pos += 1
            bin_tp += bool(p)
        else:
            bin_neg += 1
            bin_fp += bool(p)
    per_class = {}
    for c in classes:
        prec = tp[c] / (tp[c] + fp[c]) if tp[c] + fp[c] else 0.0
        rec = tp[c] / (tp[c] + fn[c]) if tp[c] + fn[c] else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per_class[c] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "support": support[c]}
    scored = [c for c in classes if support[c] >= min_support]
    n = len(rows) or 1
    return {
        "n": len(rows),
        "valid_json": round(valid / n, 4),
        "exact_match": round(exact / n, 4),
        "primary_accuracy": round(primary_ok / n, 4),
        "macro_f1": round(sum(per_class[c]["f1"] for c in scored) / len(scored), 4) if scored else None,
        "macro_f1_classes": scored,
        "binary": {"false_positive_rate_on_none": round(bin_fp / bin_neg, 4) if bin_neg else None,
                   "defect_recall": round(bin_tp / bin_pos, 4) if bin_pos else None,
                   "none_images": bin_neg, "defect_images": bin_pos},
        "per_class": per_class,
    }


def by_source(rows: list[dict], classes: tuple[str, ...]) -> dict:
    out = {}
    for src in sorted({r["source"] for r in rows}):
        m = evaluate([r for r in rows if r["source"] == src], classes)
        out[src] = {k: m[k] for k in ("n", "valid_json", "exact_match", "primary_accuracy", "macro_f1")}
    return out
