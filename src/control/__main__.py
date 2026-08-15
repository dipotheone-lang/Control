"""Command-line entry — `python -m control <command>`.

Commands map to what the engine can honestly do today:

  startup    run the §5.6 startup sequence and report the state
  discovery  Phase 0 Stages A-B against UB_ROOT (requires DISCOVERY state)
  verify     §13.3 assurance: DB integrity + audit hash chain

There is deliberately no `cycle` command yet: a live cycle needs the
Graph transport, which needs the §5.1 provisioning (O-09). The engine
refuses to pretend otherwise.

Environment defaults (§5.1): UB_ROOT, CONTROL_ROOT, RUN_MODE,
LEARNING_MODE — flags override.
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from . import HaltError
from .states import LEGAL_STATES


def _level_for(run_mode: str, learning_mode: str, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    matches = [s.level for s in LEGAL_STATES
               if s.run_mode == run_mode and s.learning_mode == learning_mode]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(
        f"level is ambiguous or undefined for RUN_MODE={run_mode} "
        f"LEARNING_MODE={learning_mode}; pass --level explicitly"
    )


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"),
                        help="CONTROL_ROOT path (env CONTROL_ROOT)")
    parser.add_argument("--ub-root", default=os.environ.get("UB_ROOT"),
                        help="UB_ROOT path (env UB_ROOT)")
    parser.add_argument("--run-mode", default=os.environ.get("RUN_MODE", "DISCOVERY"))
    parser.add_argument("--learning-mode",
                        default=os.environ.get("LEARNING_MODE", "OBSERVE"))
    parser.add_argument("--level", type=int, default=None)


def _startup(args):
    from .startup import run_startup

    level = _level_for(args.run_mode, args.learning_mode, args.level)
    report = run_startup(
        Path(args.control_root), Path(args.ub_root),
        args.run_mode, args.learning_mode, level, date.today().isoformat(),
    )
    print(f"startup OK — phase {report.state.phase}, level {report.state.level}, "
          f"RUN_MODE={report.state.run_mode}, LEARNING_MODE={report.state.learning_mode}")
    print(f"open disputes: {report.open_disputes} | open threads: {report.open_threads} | "
          f"active absences: {report.active_absences}")
    return report


def cmd_startup(args) -> int:
    _startup(args)
    return 0


def cmd_discovery(args) -> int:
    from .discovery.runner import run_discovery

    report = _startup(args)
    result = run_discovery(report, Path(args.ub_root), Path(args.control_root))
    a, b = result["stage_a"], result["stage_b"]
    print(f"stage A: {a['archives_found']} archives, {a['archives_parsed']} parsed, "
          f"{a['messages_indexed']} messages indexed, {len(a['limitations'])} limitations")
    print(f"stage B: {b['files']} files, {b['duplicate_groups']} duplicate groups, "
          f"{len(b['revision_conflicts'])} revision conflicts, "
          f"{len(b['dormant_folders'])} dormant folders")
    print(f"outputs in {Path(args.control_root) / 'discovery'}")
    return 0


def cmd_outlook_scan(args) -> int:
    from . import HaltError
    from .discovery.outlook_scan import run_outlook_scan, write_overview
    from .outlook import _dispatch_namespace

    out_dir = Path(args.control_root) / "discovery"
    folders = [f.strip() for f in args.folders.split(",") if f.strip()]
    mailboxes = [m.strip() for m in args.mailbox.split(",") if m.strip()]
    namespace = _dispatch_namespace()

    def progress(done, total):
        print(f"  ... {done}/{total}", flush=True)

    all_summaries: dict = {}
    failures: list[str] = []
    for mailbox in mailboxes:
        redact = args.redact_subjects or mailbox.lower().startswith("hr@")
        label = "metadata only, subjects redacted" if redact else "metadata only"
        print(f"\n=== {mailbox} ({', '.join(folders) or 'all folders'}) — {label}")
        try:
            summaries = run_outlook_scan(
                namespace, mailbox, folders, out_dir, limit=args.limit,
                progress=progress, redact_subjects=redact, recurse=args.recurse,
            )
        except HaltError as e:
            # A mailbox missing from the profile is a recorded gap, not a
            # reason to abandon the other mailboxes (§1.1).
            print(f"  SKIPPED: {e}")
            failures.append(f"{mailbox}: {e}")
            continue
        all_summaries[mailbox] = summaries
        for s in summaries:
            if not s.total:
                continue
            print(f"  {s.folder}: {s.total} messages, {s.earliest} to {s.latest}, "
                  f"{s.with_attachments} with attachments, "
                  f"{s.copied_to_control} copied to control@")

    if all_summaries:
        overview = write_overview(all_summaries, out_dir)
        print(f"\noverview: {overview}")
    if failures:
        print("\nGAPS (must appear in DISCOVERY-LIMITATIONS.md):")
        for failure in failures:
            print(f"  - {failure}")
    print(f"outputs in {out_dir}")
    return 0 if all_summaries else 1


def cmd_analyse(args) -> int:
    from .discovery.analyse import (
        analyse_responses, infer_obligations, load_rows,
        render_stage_d, render_stage_h,
    )

    discovery = Path(args.control_root) / "discovery"
    scans = sorted(discovery.glob("outlook-scan-*.jsonl"))
    if not scans:
        print(f"no scan output in {discovery}. Run outlook-scan first.")
        return 1

    for scan in scans:
        rows = load_rows(scan)
        if not rows:
            print(f"{scan.name}: empty, skipped")
            continue
        mailbox = rows[0].get("mailbox", scan.stem)
        stem = scan.stem.replace("outlook-scan-", "")

        candidates = infer_obligations(rows, min_occurrences=args.min_occurrences)
        (discovery / f"STAGE-D-{stem}.md").write_text(
            render_stage_d(candidates, mailbox), encoding="utf-8")

        report = analyse_responses(rows)
        (discovery / f"STAGE-H-{stem}.md").write_text(
            render_stage_h(report, mailbox), encoding="utf-8")

        print(f"\n{mailbox} ({len(rows)} messages)")
        high = [c for c in candidates if c.confidence == "HIGH"]
        medium = [c for c in candidates if c.confidence == "MEDIUM"]
        print(f"  candidate obligations: {len(high)} HIGH, {len(medium)} MEDIUM, "
              f"{len(candidates) - len(high) - len(medium)} LOW")
        for c in candidates[:5]:
            print(f"    [{c.confidence}] {c.cadence:12} n={c.occurrences:<4} "
                  f"{c.sender} — {c.subject_template[:45]}")
        total = report.answered + report.unanswered
        if total:
            print(f"  external messages: {total}, answered {report.answered}, "
                  f"no reply found {report.unanswered}")
            if report.median_hours is not None:
                print(f"  median first reply: {report.median_hours}h")
        if not report.sent_items_present:
            print("  NOTE: Sent Items not in this scan — unanswered count is "
                  "not reliable")
    print(f"\nreports in {discovery}")
    return 0


def cmd_phase0(args) -> int:
    """One command: find every mailbox, scan it, analyse it, write the
    Phase 0 deliverables. Nothing needs naming."""
    from . import HaltError
    from .discovery.deliverables import (
        build_results, write_confidential_scope, write_discovery_report,
        write_paste_summary,
    )
    from .discovery.outlook_scan import run_outlook_scan, write_overview
    from .outlook import _dispatch_namespace, safe_get

    discovery = Path(args.control_root) / "discovery"
    discovery.mkdir(parents=True, exist_ok=True)
    namespace = _dispatch_namespace()

    # Enumerate whatever this Outlook profile actually holds.
    mailboxes = []
    for store in namespace.Folders:
        address = str(safe_get(store, "SmtpAddress") or safe_get(store, "Name"))
        if "@" in address:
            mailboxes.append(address.lower())
    if args.mailbox:
        wanted = {m.strip().lower() for m in args.mailbox.split(",") if m.strip()}
        mailboxes = [m for m in mailboxes if m in wanted]
    if not mailboxes:
        print("No mailboxes with an email address found in this Outlook profile.")
        return 1

    print(f"Phase 0 — {len(mailboxes)} mailbox(es): {', '.join(mailboxes)}")
    print("Metadata only; no message body is read. This may take a while.\n")

    folders = [f.strip() for f in args.folders.split(",") if f.strip()]
    gaps: list[str] = []
    all_summaries: dict = {}

    def progress(done, total):
        print(f"    ... {done}/{total}", flush=True)

    for mailbox in mailboxes:
        redact = args.redact_subjects or mailbox.startswith("hr@")
        print(f"  {mailbox}" + ("  [subjects redacted]" if redact else ""))
        try:
            summaries = run_outlook_scan(
                namespace, mailbox, folders, discovery, limit=args.limit,
                progress=progress, redact_subjects=redact, recurse=args.recurse,
            )
        except HaltError as e:
            print(f"    SKIPPED: {e}")
            gaps.append(f"{mailbox}: {e}")
            continue
        all_summaries[mailbox] = summaries
        for s in summaries:
            if s.total or s.unreadable_items:
                note = (f", {s.unreadable_items} unreadable"
                        if s.unreadable_items else "")
                print(f"    {s.folder}: {s.total} messages{note}")
            if s.unreadable_items:
                gaps.append(f"{mailbox}/{s.folder}: {s.unreadable_items} "
                            "items could not be read")

    if not all_summaries:
        print("\nNothing scanned. Nothing generated.")
        return 1

    write_overview(all_summaries, discovery)
    results = build_results(discovery, min_occurrences=args.min_occurrences)
    report = write_discovery_report(results, discovery, gaps)
    scope = write_confidential_scope(results, discovery)
    summary = write_paste_summary(results, discovery, gaps)

    print("\n" + "=" * 60)
    print(summary.read_text(encoding="utf-8"))
    print("=" * 60)
    print(f"\nDeliverables written to {discovery}:")
    for path in (report, scope, summary):
        print(f"  {path.name}")
    print("  MAILBOX-OVERVIEW.md, STAGE-D-*.md, STAGE-H-*.md via 'analyse'")
    return 0


def cmd_verify(args) -> int:
    from .audit import AuditLog
    from .db import connect, integrity_check

    control_root = Path(args.control_root)
    failures = 0

    db_path = control_root / "data" / "control.db"
    if db_path.exists():
        conn = connect(db_path)
        try:
            integrity_check(conn)
            print("db: integrity OK")
        except HaltError as e:
            print(f"db: FAILED — {e}")
            failures += 1
        finally:
            conn.close()
    else:
        print("db: not present (no cycles run yet)")

    ok, detail = AuditLog(control_root / "logs").verify()
    print(f"audit chain: {'OK — ' + detail if ok else 'BROKEN — ' + detail}")
    if not ok:
        failures += 1
        print("a chain break is a critical incident (§13.3)")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="control")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("startup", cmd_startup), ("discovery", cmd_discovery),
                     ("verify", cmd_verify)):
        p = sub.add_parser(name)
        _common(p)
        p.set_defaults(fn=fn)

    scan = sub.add_parser("outlook-scan",
                          help="historical mailbox scan via Outlook (metadata only)")
    scan.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    scan.add_argument("--mailbox", required=True,
                      help="one address, or several separated by commas")
    scan.add_argument("--folders", default="Inbox",
                      help="comma-separated folder names; empty string = all folders")
    scan.add_argument("--limit", type=int, default=None,
                      help="stop after N messages per folder")
    scan.add_argument("--recurse", action="store_true",
                      help="include subfolders")
    scan.add_argument("--redact-subjects", action="store_true",
                      help="omit subject lines (automatic for hr@ mailboxes)")
    scan.set_defaults(fn=cmd_outlook_scan)

    analyse = sub.add_parser("analyse",
                             help="Stage D cadence and Stage H responses from scan output")
    analyse.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    analyse.add_argument("--min-occurrences", type=int, default=3,
                         help="minimum repeats before a pattern is a candidate")
    analyse.set_defaults(fn=cmd_analyse)

    phase0 = sub.add_parser(
        "phase0",
        help="one command: scan every mailbox, analyse, write the deliverables")
    phase0.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    phase0.add_argument("--mailbox", default="",
                        help="restrict to these addresses (default: all in profile)")
    phase0.add_argument("--folders", default="Inbox,Sent Items")
    phase0.add_argument("--limit", type=int, default=None)
    phase0.add_argument("--recurse", action="store_true")
    phase0.add_argument("--redact-subjects", action="store_true")
    phase0.add_argument("--min-occurrences", type=int, default=3)
    phase0.set_defaults(fn=cmd_phase0)

    args = parser.parse_args(argv)
    if args.command in ("startup", "discovery") and (
            not args.control_root or not args.ub_root):
        parser.error("--control-root and --ub-root are required "
                     "(or set CONTROL_ROOT / UB_ROOT)")
    if (args.command in ("verify", "outlook-scan", "analyse", "phase0")
            and not args.control_root):
        parser.error("--control-root is required (or set CONTROL_ROOT)")
    try:
        return args.fn(args)
    except HaltError as e:
        print(f"HALT: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
