"""CLI di PrintLoop: `uv run printloop --help`."""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from printloop import gcode, llm, loop, slicer, testset
from printloop.models import Case
from printloop.taxonomy import label


def _print_case(case: Case) -> None:
    it = case.current
    print(f"caso {case.id} · {case.name} · stato {case.state}" + (f" · esito {case.outcome}" if case.outcome else ""))
    print(f"  {case.printer} · {case.material} · iterazione {it.n}/{case.max_iterations + 1}")
    if case.message:
        print(f"  {case.message}")
    if it.diagnosis:
        d = it.diagnosis
        print(f"  diagnosi ({d.source}): {label(d.primary)} severità {d.severity}/3 confidenza {d.confidence:.2f}")
    if it.proposal and it.proposal.changes:
        p = it.proposal
        print(f"  patch ({p.source}):")
        for c in p.changes:
            print(f"    {c.key}: {c.before} → {c.after} {c.unit}  {c.reason}")
        for a in p.rejected_attempts:
            print(f"    scartata in {a.stage}: {a.reason}")
    if it.preflight:
        print(f"  pre-flight: {'OK' if it.preflight.ok else 'FALLITO'}")
        for c in it.preflight.checks + it.preflight.limits:
            print(f"    [{c.status:4}] {c.check:<20} {c.target:<28} {c.before} → {c.after}  {c.detail}")
        print(f"    effetti: {it.preflight.side_effects}")
    if it.sliced_3mf:
        print(f"  file da stampare: {loop.case_dir(case.id) / it.sliced_3mf}")


def _parse_edits(items: list[str] | None) -> dict[str, float] | None:
    if not items:
        return None
    edits = {}
    for item in items:
        key, _, value = item.partition("=")
        edits[key.strip()] = float(value)
    return edits


def _placeholder_photo() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (128, 128, 128)).save(buf, "JPEG")
    return buf.getvalue()


def cmd_demo(args) -> None:
    """Loop completo offline su un caso del test set, con diagnosi dichiarate (severità 3 → 2 → 1)."""
    outdir = Path(args.testset)
    if not (outdir / args.case / "project.3mf").exists():
        testset.build_testset(outdir, slice_cases=False)
    manifest = json.loads((outdir / args.case / "manifest.json").read_text())
    defect = manifest["induced_defect"]
    case = loop.create(outdir / args.case / "project.3mf", f"demo {args.case}")
    for severity in (3, 2, 1):
        loop.add_photos(case.id, [("placeholder.jpg", _placeholder_photo())], note="demo offline")
        case = loop.diagnose_case(case.id, mode="operator", defect=defect, severity=severity)
        print(f"\n=== iterazione {case.current.n}: {label(defect)} severità {severity}")
        if case.state != "diagnosed":
            _print_case(case)
            break
        case = loop.propose_case(case.id, mode="rules")
        _print_case(case)
        if case.state != "awaiting_approval":
            break
        case = loop.decide(case.id, approved=True, reason="demo: approvata")
    print(f"\nesito: {case.outcome} · patch attesa dal manifest: {manifest['expected_patch']}")
    print(f"audit: {loop.case_dir(case.id) / 'audit.jsonl'}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="printloop", description="PrintLoop: foto → diagnosi → patch verificata")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="slicer, LLM e configurazione")
    p = sub.add_parser("coupon", help="ricostruisce examples/coupon dal modello e dai preset di sistema")
    p = sub.add_parser("testset", help="progetti con difetti indotti + manifest (ground truth)")
    p.add_argument("--out", default=str(testset.DEFAULT_TESTSET_DIR))
    p.add_argument("--no-slice", action="store_true")
    p.add_argument("--bed", help='piatto reale, es. "Textured PEI Plate" (default: quello del coupon)')
    p = sub.add_parser("inspect", help="statistiche del G-code (fa lo slicing se riceve un 3MF)")
    p.add_argument("file")
    sub.add_parser("list", help="casi esistenti")
    p = sub.add_parser("new", help="nuovo caso da un progetto 3MF")
    p.add_argument("project")
    p.add_argument("--name")
    p = sub.add_parser("photos", help="carica le foto dell'iterazione corrente")
    p.add_argument("case_id")
    p.add_argument("files", nargs="+")
    p.add_argument("--note", default="")
    p = sub.add_parser("diagnose", help="diagnosi (LLM se configurato, altrimenti --defect)")
    p.add_argument("case_id")
    p.add_argument("--defect")
    p.add_argument("--severity", type=int)
    p.add_argument("--mode", default="auto", choices=["auto", "llm", "operator"])
    p.add_argument("--note", default="")
    p = sub.add_parser("propose", help="patch + slicing + pre-flight")
    p.add_argument("case_id")
    p.add_argument("--mode", default="auto", choices=["auto", "llm", "rules"])
    for name in ("approve", "reject"):
        p = sub.add_parser(name)
        p.add_argument("case_id")
        p.add_argument("--reason", default="")
        p.add_argument("--set", nargs="*", metavar="KEY=VALUE", help="valori scelti dall'operatore")
    p = sub.add_parser("stop", help="ferma il loop")
    p.add_argument("case_id")
    p.add_argument("--reason", default="")
    p = sub.add_parser("show")
    p.add_argument("case_id")
    p = sub.add_parser("demo", help="loop completo offline su un caso del test set")
    p.add_argument("--case", default="C1_bridge_speed")
    p.add_argument("--testset", default=str(testset.DEFAULT_TESTSET_DIR))

    args = ap.parse_args(argv)
    try:
        if args.cmd == "status":
            print(json.dumps({"slicer": slicer.version(), "llm": llm.describe(), "runs": str(loop.cases_dir())}, indent=2))
        elif args.cmd == "coupon":
            print(testset.build_coupon())
        elif args.cmd == "testset":
            for entry in testset.build_testset(Path(args.out), slice_cases=not args.no_slice,
                                               bed_type=args.bed):
                print(f"{entry['case_id']:<26} {entry['induced_defect']:<16} {entry['induced_params']}  "
                      f"{entry.get('print_time_min', '')} min")
            print(f"manifest: {Path(args.out) / 'manifest.json'}")
        elif args.cmd == "inspect":
            path = Path(args.file)
            if path.suffix == ".3mf":
                path = slicer.slice_project(path, Path(loop.LOOP.runs_dir) / "inspect" / path.stem).gcode
            print(json.dumps(gcode.parse(path).summary(), indent=2, ensure_ascii=False))
        elif args.cmd == "list":
            for c in loop.list_cases():
                print(f"{c.id}  {c.state:<18} {c.outcome or '':<10} it.{c.current.n}  {c.name}")
        elif args.cmd == "new":
            _print_case(loop.create(args.project, args.name))
        elif args.cmd == "photos":
            files = [(Path(f).name, Path(f).read_bytes()) for f in args.files]
            _print_case(loop.add_photos(args.case_id, files, args.note))
        elif args.cmd == "diagnose":
            _print_case(loop.diagnose_case(args.case_id, args.mode, args.defect, args.severity, args.note))
        elif args.cmd == "propose":
            _print_case(loop.propose_case(args.case_id, args.mode))
        elif args.cmd in ("approve", "reject"):
            _print_case(loop.decide(args.case_id, args.cmd == "approve", args.reason, _parse_edits(args.set)))
        elif args.cmd == "stop":
            _print_case(loop.decide(args.case_id, False, args.reason, stop=True))
        elif args.cmd == "show":
            _print_case(loop.load(args.case_id))
        elif args.cmd == "demo":
            cmd_demo(args)
    except (loop.CaseError, loop.NotFound, slicer.SlicerError, llm.LLMUnavailable, ValueError) as exc:
        print(f"errore: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
