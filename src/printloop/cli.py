"""PrintLoop CLI: `uv run printloop --help`."""
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
    print(f"case {case.id} · {case.name} · state {case.state}" + (f" · outcome {case.outcome}" if case.outcome else ""))
    print(f"  {case.printer} · {case.material} · iteration {it.n}/{case.max_iterations + 1}")
    if case.message:
        print(f"  {case.message}")
    if it.diagnosis:
        d = it.diagnosis
        print(f"  diagnosis ({d.source}): {label(d.primary)} severity {d.severity}/3 confidence {d.confidence:.2f}")
    if it.proposal and it.proposal.changes:
        p = it.proposal
        print(f"  patch ({p.source}):")
        for c in p.changes:
            print(f"    {c.key}: {c.before} → {c.after} {c.unit}  {c.reason}")
        for a in p.rejected_attempts:
            print(f"    discarded at {a.stage}: {a.reason}")
    if it.preflight:
        print(f"  pre-flight: {'OK' if it.preflight.ok else 'FAILED'}")
        for c in it.preflight.checks + it.preflight.limits:
            print(f"    [{c.status:4}] {c.check:<20} {c.target:<28} {c.before} → {c.after}  {c.detail}")
        print(f"    side effects: {it.preflight.side_effects}")
    if it.sliced_3mf:
        print(f"  file to print: {loop.case_dir(case.id) / it.sliced_3mf}")
    targets = loop.rewind_targets(case)
    if targets:
        last = targets[-1]
        print(f"  step back: printloop rewind {case.id} --iteration {last['iteration']} --step {last['step']}")


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
    """Full offline loop on a test set case, with stated diagnoses (severity 3 → 2 → 1)."""
    outdir = Path(args.testset)
    if not (outdir / args.case / "project.3mf").exists():
        testset.build_testset(outdir, slice_cases=False)
    manifest = json.loads((outdir / args.case / "manifest.json").read_text())
    defect = manifest["induced_defect"]
    case = loop.create(outdir / args.case / "project.3mf", f"demo {args.case}")
    for severity in (3, 2, 1):
        loop.add_photos(case.id, [("placeholder.jpg", _placeholder_photo())], note="offline demo")
        case = loop.diagnose_case(case.id, mode="operator", defect=defect, severity=severity)
        print(f"\n=== iteration {case.current.n}: {label(defect)} severity {severity}")
        if case.state != "diagnosed":
            _print_case(case)
            break
        case = loop.propose_case(case.id, mode="rules")
        _print_case(case)
        if case.state != "awaiting_approval":
            break
        case = loop.decide(case.id, approved=True, reason="demo: approved")
    print(f"\noutcome: {case.outcome} · patch expected by the manifest: {manifest['expected_patch']}")
    print(f"audit: {loop.case_dir(case.id) / 'audit.jsonl'}")


def _read_labels(path: str) -> dict[str, list[str]]:
    """CSV `name,defects` (defects separated by ';', empty = clean frame)."""
    import csv
    out = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if not row or row[0] in ("name", "frame", "frame_id"):
                continue
            out[row[0]] = [d.strip() for d in (row[1] if len(row) > 1 else "").split(";") if d.strip()]
    return out


def cmd_live_replay(args) -> None:
    """Detector + temporal filter on a folder of frames, without the UI (08_MODE1_LIVE.md §10)."""
    import statistics

    from printloop import config, detector
    from printloop.live.policy import Policy
    from printloop.live.sources import ReplaySource

    if not llm.vision_available():
        raise ValueError("set VISION_LLM_BASE_URL (the fine-tuned E4B detector)")
    src, pol = ReplaySource(args.dir), Policy(config.MODE1)
    labels = _read_labels(args.labels) if args.labels else {}
    frames, latencies, errors, first_alert, first_defect = [], [], 0, {}, None
    while (frame := src.latest()) is not None:
        det = detector.detect(frame.jpeg)
        if det.error:
            errors += 1
            print(f"{frame.name}: error {det.error}")
            continue
        latencies.append(det.latency_ms or 0)
        frames.append((frame.name, det))
        truth = labels.get(frame.name)
        if truth and first_defect is None:
            first_defect = len(frames) - 1
        for alert in pol.update(frame.id, det.defects, frame.name):
            state = f"cleared ({alert.id})" if alert.cleared_at else f"RAISED {alert.level} ({alert.id})"
            print(f"{frame.name}: {alert.defect} {state}")
            first_alert.setdefault(alert.defect, len(frames) - 1)
        if args.verbose:
            print(f"{frame.name}: {det.defects or 'clean'} {det.latency_ms} ms")
    print(f"\nframes {len(frames)} · errors {errors} · latency p50 "
          f"{statistics.median(latencies) if latencies else '-'} ms · thresholds {pol.thresholds()}")
    print("alerts: " + (", ".join(f"{a.defect} {a.level} since {a.since}" for a in pol.alerts) or "none"))
    if labels:
        scored = [(name, det) for name, det in frames if name in labels]
        truth_primary = lambda d: (detector.sort(d) or ["none"])[0]  # noqa: E731
        correct = sum(det.primary == truth_primary(labels[name]) for name, det in scored)
        clean = [det for name, det in scored if not labels[name]]
        print(f"labelled frames {len(scored)} · primary accuracy {correct}/{len(scored)} · "
              f"false positives on clean frames {sum(bool(d.defects) for d in clean)}/{len(clean)}")
        if first_defect is not None and first_alert:
            print(f"frames from the first labelled defect to the first alert: {min(first_alert.values()) - first_defect}")
        elif not any(labels.values()):
            print(f"clean print: false alerts {len(pol.alerts)}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="printloop", description="PrintLoop: photos → diagnosis → verified patch")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="slicer, LLM and configuration")
    p = sub.add_parser("coupon", help="rebuilds examples/coupon from the model and the system presets")
    p = sub.add_parser("testset", help="projects with induced defects + manifest (ground truth)")
    p.add_argument("--out", default=str(testset.DEFAULT_TESTSET_DIR))
    p.add_argument("--no-slice", action="store_true")
    p.add_argument("--bed", help='actual plate, e.g. "Textured PEI Plate" (default: the coupon\'s)')
    p = sub.add_parser("inspect", help="G-code statistics (slices first when given a 3MF)")
    p.add_argument("file")
    sub.add_parser("list", help="existing cases")
    p = sub.add_parser("new", help="new case from a 3MF project")
    p.add_argument("project")
    p.add_argument("--name")
    p = sub.add_parser("photos", help="upload photos for the current iteration")
    p.add_argument("case_id")
    p.add_argument("files", nargs="+")
    p.add_argument("--note", default="")
    p = sub.add_parser("diagnose", help="diagnosis (LLM if configured, otherwise --defect)")
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
        p.add_argument("--set", nargs="*", metavar="KEY=VALUE", help="values chosen by the operator")
    p = sub.add_parser("stop", help="stops the loop")
    p.add_argument("case_id")
    p.add_argument("--reason", default="")
    p = sub.add_parser("confirm", help="the reprint is good: close the case as fixed")
    p.add_argument("case_id")
    p.add_argument("--note", default="")
    p = sub.add_parser("rewind", help="go back to an earlier step (later data is archived in discarded/)")
    p.add_argument("case_id")
    p.add_argument("--iteration", type=int, required=True)
    p.add_argument("--step", required=True, choices=list(loop.STEPS))
    p = sub.add_parser("delete", help="delete a case and all its files")
    p.add_argument("case_id")
    p = sub.add_parser("show")
    p.add_argument("case_id")
    p = sub.add_parser("live", help="Mode 1 tools (the live session itself runs from the API / UI)")
    live_sub = p.add_subparsers(dest="live_cmd", required=True)
    lp = live_sub.add_parser("replay", help="detector + temporal filter on a folder of frames, with a report")
    lp.add_argument("dir")
    lp.add_argument("--labels", help="CSV name,defects (';'-separated, empty = clean) for accuracy and false alerts")
    lp.add_argument("--verbose", "-v", action="store_true")
    p = sub.add_parser("demo", help="full offline loop on a test set case")
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
        elif args.cmd == "confirm":
            _print_case(loop.confirm_success(args.case_id, args.note))
        elif args.cmd == "rewind":
            _print_case(loop.rewind(args.case_id, args.iteration, args.step))
        elif args.cmd == "delete":
            loop.delete(args.case_id)
            print(f"deleted {args.case_id}")
        elif args.cmd == "show":
            _print_case(loop.load(args.case_id))
        elif args.cmd == "demo":
            cmd_demo(args)
        elif args.cmd == "live":
            cmd_live_replay(args)
    except (loop.CaseError, loop.NotFound, slicer.SlicerError, llm.LLMUnavailable, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
