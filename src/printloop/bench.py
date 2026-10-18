"""Diagnosis benchmark on AMD (evidence for the README): latency and throughput at increasing concurrency.

Each request is a full diagnosis (1-4 photos + JSON schema). It simulates a print farm sending several cases
at once, and declares it as a simulation. Usage:
    uv run python -m printloop.bench --photos data/testset/C1_bridge_speed/photos --concurrency 1 4 8 --requests 16
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from printloop import diagnose, llm
from printloop.config import LLM, ROOT
from printloop.eval import PHOTO_EXT


def run(photos: list[Path], concurrency: list[int], requests: int) -> dict:
    if not llm.available():
        raise llm.LLMUnavailable("set LLM_BASE_URL for the benchmark")
    diagnose.diagnose_llm(photos)  # warm-up
    levels = []
    for conc in concurrency:
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=conc) as pool:
            results = list(pool.map(lambda _: diagnose.diagnose_llm(photos), range(requests)))
        wall = time.perf_counter() - t0
        lat = sorted(r.latency_ms for r in results if r.latency_ms is not None)
        level = {"concurrency": conc, "requests": requests, "wall_s": round(wall, 2),
                 "diagnoses_per_min": round(requests / wall * 60, 1),
                 "latency_p50_ms": round(statistics.median(lat), 1),
                 "latency_p95_ms": round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 1),
                 "primary": sorted({r.primary for r in results})}
        levels.append(level)
        print(json.dumps(level))
    tel = llm.TELEMETRY.snapshot()
    return {"model": LLM.model, "base_url_host": (LLM.base_url or "").split("/")[2] if LLM.base_url else None,
            "photos_per_request": len(photos), "client_host": platform.node(), "levels": levels, "telemetry": tel,
            "note": "simulated load: the same photos sent in parallel"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", required=True, help="folder with 1-4 photos")
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8])
    ap.add_argument("--requests", type=int, default=16)
    ap.add_argument("--tag", default="mi300x")
    args = ap.parse_args()
    photos = sorted(p for p in Path(args.photos).glob("*") if p.suffix.lower() in PHOTO_EXT)[:4]
    result = run(photos, args.concurrency, args.requests)
    out = ROOT / "results" / f"bench_diagnosis_{args.tag}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"results: {out}")


if __name__ == "__main__":
    main()
