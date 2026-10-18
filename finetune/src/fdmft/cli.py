"""`printloop-ft`: download -> prepare -> dedup -> build -> train -> evaluate -> export."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("train", "evaluate", "serve-eval", "export"):
        cmd, rest = argv[0], argv[1:]
        if cmd == "train":
            from fdmft.train import main as run
        elif cmd == "evaluate":
            from fdmft.evaluate import main_checkpoint as run
        elif cmd == "serve-eval":
            from fdmft.evaluate import main_server as run
        else:
            from fdmft.export import main as run
        return run(rest)

    p = argparse.ArgumentParser(prog="printloop-ft", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", help="download the public sources into data/raw (resumable)")
    d.add_argument("sources", nargs="*", help="ids from configs/sources.yaml (default: all)")
    d.add_argument("--keep-archive", action="store_true")
    d.add_argument("--force", action="store_true")
    pr = sub.add_parser("prepare", help="normalize the images and update the manifest (incremental)")
    pr.add_argument("sources", nargs="*")
    pr.add_argument("--workers", type=int, default=8)
    dd = sub.add_parser("dedup", help="near-duplicates (pHash) across sources")
    dd.add_argument("--max-distance", type=int, default=4)
    dd.add_argument("--within-source", type=int, default=0)
    b = sub.add_parser("build", help="final labels, group splits, JSONL")
    b.add_argument("build_id", nargs="?", default="v1")
    b.add_argument("--class-cap", type=int, default=2000)
    sub.add_parser("status", help="manifest and builds")
    for c in ("train", "evaluate", "serve-eval", "export"):
        sub.add_parser(c, help=f"see `printloop-ft {c} --help`")
    args = p.parse_args(argv)

    if args.cmd == "download":
        from fdmft.download import download
        return 1 if download(args.sources or None, args.keep_archive, args.force) else 0
    if args.cmd == "prepare":
        from fdmft.prepare import prepare
        prepare(args.sources or None, args.workers)
    elif args.cmd == "dedup":
        from fdmft.prepare import dedup
        dedup(args.max_distance, args.within_source)
    elif args.cmd == "build":
        from fdmft.build import build
        build(args.build_id, class_cap=args.class_cap)
    elif args.cmd == "status":
        status()
    return 0


def status() -> None:
    import json
    from collections import Counter

    from fdmft.config import PROCESSED
    from fdmft.prepare import read_manifest, usable
    from fdmft.sources import effective_license, registry

    for sid, src in registry().items():
        done = (src.raw_dir / "download.json").exists()
        print(f"{sid:24s} {'downloaded' if done else '-':11s} use={src.use:5s} licence={effective_license(src)}")
    man = read_manifest()
    print(f"\nmanifest: {len(man)} records, {len(usable(man))} usable after dedup")
    for (s, lab), n in sorted(Counter((r["source"], ",".join(r.get("labels") or ["?"])) for r in usable(man)).items()):
        print(f"  {s:24s} {lab:30s} {n}")
    for stats in sorted(PROCESSED.glob("*/stats.json")):
        st = json.loads(stats.read_text())
        print(f"\nbuild {st['build_id']}: " + ", ".join(f"{k} {st[k]['n']}" for k in ("train", "val", "test")))


if __name__ == "__main__":
    raise SystemExit(main())
