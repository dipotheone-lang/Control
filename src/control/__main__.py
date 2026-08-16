"""Command-line entry — `python -m control <command>`.

Commands map to what the engine can honestly do today:

  startup    run the §5.6 startup sequence and report the state
  discovery  Phase 0 Stages A-B against UB_ROOT (requires DISCOVERY state)
  verify     §13.3 assurance: DB integrity + audit hash chain

There is deliberately no `cycle` command yet: a live cycle needs the
Graph transport, which needs the §5.1 provisioning. Decision D-08 keeps
Phase 0 on the interim Outlook COM route and refuses it at startup in
SUPERVISED and LIVE. The engine does not pretend otherwise.

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


_REGISTER_ADDERS = {
    "contracts": "add_contract",
    "instruments": "add_instrument",
    "accreditations": "add_accreditation",
    "quotations": "add_quotation",
    "tenders": "add_tender",
}


def cmd_registers(args) -> int:
    """Class 2 registers (§2.2) — import rows, show the horizon."""
    from datetime import datetime as _dt

    import yaml

    from . import registers as reg
    from .db import connect

    db_path = Path(args.control_root) / "data" / "control.db"
    if not db_path.exists():
        print(f"no database at {db_path}. Run 'init' first.")
        return 1
    conn = connect(db_path)
    try:
        if args.import_file:
            data = yaml.safe_load(Path(args.import_file).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                print("import file must be a mapping of register name -> list of rows")
                return 1
            added = 0
            for register, rows in data.items():
                adder = _REGISTER_ADDERS.get(register)
                if not adder:
                    print(f"  unknown register {register!r} — skipped "
                          f"(expected one of {', '.join(_REGISTER_ADDERS)})")
                    continue
                for row in rows or []:
                    getattr(reg, adder)(conn, **row)
                    added += 1
                print(f"  {register}: +{len(rows or [])} rows")
            print(f"imported {added} rows (append-only: corrections add rows, "
                  "they never overwrite)")

        today = (_dt.fromisoformat(args.today).date() if args.today
                 else date.today())
        upcoming = reg.horizon(conn, today, days=args.days)

        print(f"\nCLASS 2 HORIZON — next {args.days} days (and anything overdue)")
        print(f"as of {today:%d-%b-%Y}\n")
        if not upcoming:
            print("  Nothing on record.")
            print("  An empty class 2 horizon before the registers are "
                  "populated means the registers are empty, not that the")
            print("  company has no commercial deadlines (§1.1).")
        for deadline in upcoming:
            days = (deadline.item.due - today).days
            marker = "OVERDUE" if days < 0 else f"T-{days}"
            print(f"  {deadline.item.due:%d-%b-%Y}  {marker:>8}  "
                  f"[{deadline.register}] {deadline.item.name[:60]}")
            print(f"{'':32}owner: {deadline.item.owner}")

        windows = reg.notice_periods(conn)
        if windows:
            print("\nSTANDING CLAIM/VARIATION WINDOWS (§2.2)")
            print("  A claim not noticed within its window is generally "
                  "forfeited. These run from an event, so no date is")
            print("  synthesised — they are windows, not deadlines.\n")
            for window in windows:
                print(f"  {window['contract_ref']} ({window['client']}): "
                      f"{window['notice_period_days']} days — "
                      f"owner {window['owner']}")
    finally:
        conn.close()
    return 0


def cmd_contracts(args) -> int:
    """Stage C — commercial terms from documents (§6)."""
    import yaml

    from .discovery.stage_c import render_commercial_exposure, run_stage_c

    control_root = Path(args.control_root)
    source = Path(args.source)
    if not source.is_dir():
        print(f"source folder not found: {source}")
        return 1

    clients, folders = [], []
    config = control_root / "config" / "confidential.yaml"
    if config.is_file():
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        clients = [c.get("name", "") for c in data.get("confidential_clients", [])]
        folders = list(data.get("confidential_folders") or [])
    else:
        print("WARNING: config/confidential.yaml not found — falling back to the "
              "§12.1.1 default client list. Run 'init' first.")
        clients = ["Siemens Energy", "Saint-Gobain", "KNAUF", "Galaxy",
                   "Canal Sugar", "Sukari", "Air Liquide"]

    print(f"scanning {source} for commercial terms")
    print(f"confidential clients: {len(clients)} | folders: {len(folders)}")
    if args.confidential_dates:
        print("D-05 ACTIVE: dates and term durations will be extracted from "
              "confidential contracts; no clause text is retained.")
    result = run_stage_c(source, clients, folders, exclude=[control_root],
                         permit_confidential_dates=args.confidential_dates)

    out = control_root / "discovery" / "COMMERCIAL-EXPOSURE.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_commercial_exposure(result), encoding="utf-8")

    print(f"\ndocuments seen:      {len(result.documents)}")
    print(f"terms extracted:     {len(result.terms)}")
    print(f"confidential, unread: {len(result.blocked)}  (D-01)")
    if result.d05_extracted:
        print(f"confidential, dates only: {len(result.d05_extracted)}  (D-05)")
    print(f"unreadable/scanned:   {len(result.unreadable)}  (OCR needed)")
    dated = [t for t in result.terms if t.found_date]
    if dated:
        soonest = sorted(dated, key=lambda t: t.found_date)[:5]
        print("\nnearest dated terms:")
        for term in soonest:
            print(f"  {term.found_date}  {term.kind:20} {term.source[:50]}")
    print(f"\nwritten: {out}")
    return 0


def cmd_init(args) -> int:
    """Create CONTROL_ROOT from the repository's config templates."""
    from .bootstrap import bootstrap, render_result

    repo_config = Path(__file__).resolve().parent.parent.parent / "config"
    template = Path(args.templates) if args.templates else repo_config
    result = bootstrap(Path(args.control_root), template)
    print(render_result(result))
    print("\nNext:")
    print(f"  python -m control verify --control-root \"{args.control_root}\"")
    print(f"  python -m control phase0 --control-root \"{args.control_root}\"")
    return 0


def cmd_doctor(args) -> int:
    """Check that this machine can actually run Control."""
    import importlib
    import platform

    ok = True
    print(f"platform: {platform.system()} {platform.release()}")
    print(f"python:   {platform.python_version()}")

    for module, why in (("yaml", "config"), ("openpyxl", "xlsx extraction"),
                        ("win32com.client", "Outlook transport (Windows only)"),
                        ("msal", "Graph transport"),
                        ("cryptography", "certificate handling")):
        try:
            importlib.import_module(module)
            print(f"  [ok]   {module:20} — {why}")
        except ImportError:
            level = "warn" if module in ("msal", "win32com.client") else "MISSING"
            if level == "MISSING":
                ok = False
            print(f"  [{level}] {module:20} — {why}")

    control_root = Path(args.control_root) if args.control_root else None
    if control_root:
        print(f"\nCONTROL_ROOT: {control_root}")
        for relative in ("config", "data", "logs", "outbox", "discovery"):
            path = control_root / relative
            print(f"  [{'ok' if path.is_dir() else 'MISSING'}] {relative}")
            if not path.is_dir():
                ok = False
        config_count = len(list((control_root / "config").glob("*.yaml"))) \
            if (control_root / "config").is_dir() else 0
        print(f"  config files: {config_count}")
        if config_count < 13:
            ok = False
            print("    run: python -m control init --control-root <path>")
    else:
        print("\nNo CONTROL_ROOT given (--control-root or $CONTROL_ROOT)")
        ok = False

    try:
        from .outlook import _dispatch_namespace
        namespace = _dispatch_namespace()
        boxes = [str(getattr(s, "Name", "?")) for s in namespace.Folders]
        print(f"\nOutlook: attached, {len(boxes)} store(s)")
        for box in boxes[:10]:
            print(f"  - {box}")
    except Exception as e:
        print(f"\nOutlook: not available — {str(e)[:120]}")

    print("\n" + ("READY" if ok else "NOT READY — fix the items above"))
    return 0 if ok else 1


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
            if s.not_found:
                print(f"    !! {s.folder}")
                print(f"       folders present: "
                      f"{', '.join(s.available_folders[:12]) or 'none'}")
                gaps.append(f"{mailbox}: requested folder {s.folder}")
                continue
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


def cmd_classify(args) -> int:
    """Decision O-04 — build the domain worksheet, or apply the answers."""
    from .discovery.analyse import load_rows
    from .discovery.classify_worksheet import (
        apply_worksheet, build_rows, read_worksheet, write_worksheet,
    )

    control_root = Path(args.control_root)
    discovery = control_root / "discovery"

    if args.apply:
        worksheet = Path(args.apply)
        if not worksheet.is_file():
            print(f"worksheet not found: {worksheet}")
            return 1
        decisions, problems = read_worksheet(worksheet)
        if problems:
            print("The worksheet has entries Control will not interpret:\n")
            for problem in problems:
                print(f"  {problem}")
            print("\nNothing applied. Fix those rows and run again — a "
                  "guessed classification is a fabrication (§1.1).")
            return 1
        if not decisions:
            print("No decisions found in the worksheet. Nothing applied.")
            return 1
        config = control_root / "config" / "confidential.yaml"
        if not config.is_file():
            print(f"config not found: {config}. Run 'init' first.")
            return 1
        result = apply_worksheet(decisions, config, args.decided_by,
                                 args.decided_on or date.today().isoformat())
        import csv as _csv

        with worksheet.open(encoding="utf-8-sig", newline="") as f:
            total = sum(1 for r in _csv.DictReader(f) if (r.get("domain") or "").strip())
        blank = total - len(decisions)
        print(f"applied to {config}")
        print(f"  CONFIDENTIAL:     {result['confidential']}")
        print(f"  NOT_CONFIDENTIAL: {result['not_confidential']}")
        print(f"  left blank:       {blank}  (stay CONFIDENTIAL)")
        print("\nD-01 is untouched: contents of confidential items are still "
              "never read.")
        print("Domains left blank remain confidential by default (§12.1.1).")
        return 0

    scans = sorted(discovery.glob("outlook-scan-*.jsonl"))
    if not scans:
        print(f"no scan output in {discovery}. Run phase0 or outlook-scan first.")
        return 1
    rows: list[dict] = []
    for scan in scans:
        rows.extend(load_rows(scan))
    if not rows:
        print("scan files are empty.")
        return 1

    domains = build_rows(rows)
    out = write_worksheet(domains, discovery / "DOMAIN-CLASSIFICATION.csv")

    proposed_conf = sum(1 for d in domains if d.proposed == "CONFIDENTIAL")
    matched = [d for d in domains if d.matched_client]
    print(f"{len(rows)} messages, {len(domains)} external domains\n")
    print(f"  proposed CONFIDENTIAL:     {proposed_conf}")
    print(f"  proposed NOT_CONFIDENTIAL: {len(domains) - proposed_conf}")
    print(f"  matching a §12.1.1 client: {len(matched)}")
    print("\nTop counterparties by volume:")
    for d in domains[:15]:
        client = f"  [{d.matched_client}]" if d.matched_client else ""
        print(f"  {d.messages:>6}  {d.domain[:42]:42} {d.proposed}{client}")

    print(f"\nworksheet: {out}")
    print("Open it, fill YOUR_DECISION with CONFIDENTIAL or NOT_CONFIDENTIAL, "
          "then run:")
    print(f'  python -m control classify --apply "{out}"')
    print("\nLeave a row blank and the domain stays confidential — blanks are "
          "never read as approval (§12.1.1).")
    print("Outbound counts are a lower bound: Outlook reports many recipients "
          "as display names, not addresses.")
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

    init = sub.add_parser("init",
                          help="create CONTROL_ROOT from the config templates")
    init.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    init.add_argument("--templates", default="",
                      help="config template directory (default: repo config/)")
    init.set_defaults(fn=cmd_init)

    contracts = sub.add_parser(
        "contracts",
        help="Stage C: extract guarantee, LD, notice and accreditation terms")
    contracts.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    contracts.add_argument("--source", required=True,
                           help="folder holding contracts and agreements")
    contracts.add_argument("--confidential-dates", action="store_true",
                           help="D-05: extract dates and term durations from "
                                "confidential contracts (no clause text kept)")
    contracts.set_defaults(fn=cmd_contracts)

    registers = sub.add_parser(
        "registers", help="class 2 registers (§2.2): import rows, show the horizon")
    registers.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    registers.add_argument("--import-file", default="",
                           help="YAML file of register rows to append")
    registers.add_argument("--days", type=int, default=30)
    registers.add_argument("--today", default="", help="ISO date, for testing")
    registers.set_defaults(fn=cmd_registers)

    classify = sub.add_parser(
        "classify",
        help="O-04: build the domain confidentiality worksheet, or apply it")
    classify.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    classify.add_argument("--apply", default="",
                          help="path to the filled-in worksheet CSV")
    classify.add_argument("--decided-by", default="ahmed@ubcsis.com")
    classify.add_argument("--decided-on", default="",
                          help="ISO date of the decision (default: today)")
    classify.set_defaults(fn=cmd_classify)

    doctor = sub.add_parser("doctor",
                            help="check this machine can run Control")
    doctor.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    doctor.set_defaults(fn=cmd_doctor)

    args = parser.parse_args(argv)
    if args.command in ("startup", "discovery") and (
            not args.control_root or not args.ub_root):
        parser.error("--control-root and --ub-root are required "
                     "(or set CONTROL_ROOT / UB_ROOT)")
    if (args.command in ("verify", "outlook-scan", "analyse", "phase0", "init",
                         "contracts", "registers", "classify")
            and not args.control_root):
        parser.error("--control-root is required (or set CONTROL_ROOT)")
    try:
        return args.fn(args)
    except HaltError as e:
        print(f"HALT: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
