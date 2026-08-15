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
    from .discovery.outlook_scan import run_outlook_scan
    from .outlook import _dispatch_namespace

    out_dir = Path(args.control_root) / "discovery"
    folders = [f.strip() for f in args.folders.split(",") if f.strip()]

    def progress(done, total):
        print(f"  ... {done}/{total}", flush=True)

    print(f"scanning {args.mailbox} ({', '.join(folders)}) — metadata only")
    summaries = run_outlook_scan(
        _dispatch_namespace(), args.mailbox, folders, out_dir,
        limit=args.limit, progress=progress,
    )
    for s in summaries:
        print(f"\n{s.folder}: {s.total} messages, {s.earliest or 'n/a'} to "
              f"{s.latest or 'n/a'}")
        print(f"  with attachments: {s.with_attachments}")
        print(f"  internal/external senders: {s.internal_count}/{s.external_count}")
        print(f"  copied to control@: {s.copied_to_control}")
        if s.top_senders:
            print("  top senders: " + ", ".join(
                f"{a or '(unknown)'} ({n})" for a, n in s.top_senders[:5]))
    print(f"\noutputs in {out_dir}")
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
    scan.add_argument("--mailbox", required=True)
    scan.add_argument("--folders", default="Inbox",
                      help="comma-separated folder names (default: Inbox)")
    scan.add_argument("--limit", type=int, default=None,
                      help="stop after N messages per folder")
    scan.set_defaults(fn=cmd_outlook_scan)

    args = parser.parse_args(argv)
    if args.command in ("startup", "discovery") and (
            not args.control_root or not args.ub_root):
        parser.error("--control-root and --ub-root are required "
                     "(or set CONTROL_ROOT / UB_ROOT)")
    if args.command in ("verify", "outlook-scan") and not args.control_root:
        parser.error("--control-root is required (or set CONTROL_ROOT)")
    try:
        return args.fn(args)
    except HaltError as e:
        print(f"HALT: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
