"""Valutazione sul test set con difetti indotti (docs/printloop/02_DATA_STRATEGY.md §5).

- `patches`: data la diagnosi corretta, la prima patch tocca il parametro indotto nella direzione giusta
  e supera il pre-flight? Il controllo negativo C0 non deve produrre patch. Gira offline.
- `diagnosis`: Gemma sulle foto reali di ogni caso (data/testset/<caso>/photos/*.jpg) contro il difetto
  indotto: top-1, top-2, severità, latenza. Richiede l'endpoint LLM e le foto delle stampe.

Uso: `uv run python -m printloop.eval patches|diagnosis [--testset DIR] [--mode rules|llm]`
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from printloop import diagnose, loop, testset
from printloop.config import ROOT

RESULTS_DIR = ROOT / "results"
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _cases(testset_dir: Path) -> list[dict]:
    manifest = testset_dir / "manifest.json"
    if not manifest.exists():
        testset.build_testset(testset_dir, slice_cases=False)
    return json.loads(manifest.read_text())


def eval_patches(testset_dir: Path, mode: str = "rules") -> dict:
    rows = []
    for entry in _cases(testset_dir):
        t0 = time.perf_counter()
        case = loop.create(testset_dir / entry["case_id"] / "project.3mf", f"eval {entry['case_id']}")
        case = loop.diagnose_case(case.id, mode="operator", defect=entry["induced_defect"], severity=2)
        row = {"case_id": entry["case_id"], "defect": entry["induced_defect"], "expected": entry["expected_patch"]}
        if case.state == "diagnosed":
            case = loop.propose_case(case.id, mode=mode)
        it = case.current
        changes = [c for c in (it.proposal.changes if it.proposal else []) if not c.companion]
        row["proposed"] = {c.key: [c.before, c.after] for c in changes}
        row["state"] = case.state
        row["preflight_ok"] = bool(it.preflight and it.preflight.ok)
        row["rejected_attempts"] = len(it.proposal.rejected_attempts) if it.proposal else 0
        if not entry["expected_patch"]:
            row["correct"] = case.state == "done" and not changes
        else:
            row["correct"] = any(
                c.key in entry["expected_patch"]
                and (c.after - c.before > 0) == (entry["expected_patch"][c.key] == "up") for c in changes)
        row["seconds"] = round(time.perf_counter() - t0, 2)
        rows.append(row)
        print(f"{row['case_id']:<26} {'OK ' if row['correct'] else 'NO '} proposto {row['proposed']} "
              f"atteso {row['expected']} pre-flight {row['preflight_ok']}")
    summary = {"mode": mode, "cases": len(rows), "correct": sum(r["correct"] for r in rows),
               "preflight_ok": sum(r["preflight_ok"] for r in rows if r["expected"]), "rows": rows}
    print(f"\ncausa corretta: {summary['correct']}/{summary['cases']}")
    return summary


def eval_diagnosis(testset_dir: Path) -> dict:
    rows = []
    for entry in _cases(testset_dir):
        photo_dir = testset_dir / entry["case_id"] / "photos"
        photos = sorted(p for p in photo_dir.glob("*") if p.suffix.lower() in PHOTO_EXT) if photo_dir.exists() else []
        if not photos:
            continue
        diag = diagnose.diagnose_llm(photos[:4], entry.get("printer"), "PLA")
        ranked = [f.defect for f in sorted(diag.findings, key=lambda f: (-f.severity, -f.confidence))]
        truth = entry["induced_defect"]
        rows.append({"case_id": entry["case_id"], "truth": truth, "primary": diag.primary, "ranked": ranked,
                     "top1": diag.primary == truth, "top2": truth in ([diag.primary] + ranked)[:2],
                     "severity": diag.severity, "confidence": diag.confidence, "latency_ms": diag.latency_ms})
        print(f"{entry['case_id']:<26} verità {truth:<16} modello {diag.primary:<16} "
              f"conf {diag.confidence:.2f} {diag.latency_ms} ms")
    n = len(rows)
    summary = {"cases": n, "top1": sum(r["top1"] for r in rows), "top2": sum(r["top2"] for r in rows), "rows": rows}
    print(f"\ntop-1 {summary['top1']}/{n} · top-2 {summary['top2']}/{n}" if n else "nessuna foto nel test set")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["patches", "diagnosis"])
    ap.add_argument("--testset", default=str(testset.DEFAULT_TESTSET_DIR))
    ap.add_argument("--mode", default="rules", choices=["rules", "llm"])
    args = ap.parse_args()
    testset_dir = Path(args.testset)
    result = eval_patches(testset_dir, args.mode) if args.what == "patches" else eval_diagnosis(testset_dir)
    RESULTS_DIR.mkdir(exist_ok=True)
    name = f"eval_{args.what}" + (f"_{args.mode}" if args.what == "patches" else "") + ".json"
    (RESULTS_DIR / name).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"risultati: {RESULTS_DIR / name}")


if __name__ == "__main__":
    main()
