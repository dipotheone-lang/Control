"""Command-line entry — `python -m control <command>`.

Commands map to what the engine can honestly do today:

  startup    run the §5.6 startup sequence and report the state
  discovery  Phase 0 Stages A-B against UB_ROOT (requires DISCOVERY state)
  verify     §13.3 assurance: DB integrity + audit hash chain

  cycle      one sweep: fetch, classify, evaluate, enforce, gate

`cycle` is what Phase 1 runs. What it sends is decided by the §10 gate
table and the run mode, never by a flag here: in DRY_RUN it sends
nothing at all. Decision D-08 keeps Phase 0 and Phase 1 on the interim
Outlook route and refuses it at startup in SUPERVISED and LIVE.

Environment defaults (§5.1): UB_ROOT, CONTROL_ROOT, RUN_MODE,
LEARNING_MODE — flags override.
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import HaltError
from .states import LEGAL_STATES

# The UB-Mannheim installer's default location. It does not add itself to
# PATH in a silent install, so a bare `tesseract` call finds nothing.
_TESSERACT_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


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
    if report.schema_added:
        # A schema change applied to a database already in the field is
        # not a routine event, and it is not something to discover from
        # a crash three commands later.
        print(f"schema: created {', '.join(report.schema_added)} — the code "
              "was newer than this database. Existing rows are untouched "
              "(§5.2); the addition is in the audit log.")
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


def _check_mailbox_scope(mailbox_arg: str, report) -> list[str]:
    """§3.1a — gate every mailbox before anything opens it.

    Returns the notes that must be recorded for reads permitted only
    because this is Phase 0. Raises if a mailbox is out of scope in any
    other mode.
    """
    from .scope import assert_readable, load_scope_file

    scope = load_scope_file(Path(report.config.root))
    notes = []
    for mailbox in (m.strip() for m in mailbox_arg.split(",") if m.strip()):
        note = assert_readable(mailbox, scope, report.state.run_mode)
        if note:
            notes.append(note)
            report.audit.append("mailbox.out_of_scope_read", {
                "mailbox": mailbox, "run_mode": report.state.run_mode,
                "effective_scope": scope.effective})
    return notes


def cmd_outlook_scan(args) -> int:
    from . import HaltError
    from .discovery.outlook_scan import run_outlook_scan, write_overview
    from .outlook import _dispatch_namespace

    # §5.6 runs before the mailbox is touched — state, integrity, roots,
    # then mail. This command used to go straight to the namespace,
    # which is the one order the charter rules out.
    report = _startup(args)
    scope_notes = _check_mailbox_scope(args.mailbox, report)

    out_dir = Path(args.control_root) / "discovery"
    folders = [f.strip() for f in args.folders.split(",") if f.strip()]
    mailboxes = [m.strip() for m in args.mailbox.split(",") if m.strip()]
    for note in scope_notes:
        print(f"SCOPE: {note}")
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
        undated_rows = reg.undated(conn)
        if not upcoming:
            print("  Nothing due on record.")
            if not undated_rows:
                print("  An empty class 2 horizon before the registers are "
                      "populated means the registers are empty, not that the")
                print("  company has no commercial deadlines (§1.1).")
        for deadline in upcoming:
            days = (deadline.item.due - today).days
            marker = "OVERDUE" if days < 0 else f"T-{days}"
            print(f"  {deadline.item.due:%d-%b-%Y}  {marker:>8}  "
                  f"[{deadline.register}] {deadline.item.name[:60]}")
            # An empty owner used to be filled with a hardcoded address,
            # so a guarantee nobody was chasing read as assigned to a
            # named person (§1.1). It now reads as the gap it is.
            print(f"{'':32}owner: "
                  f"{deadline.item.owner or 'NOT ASSIGNED — nobody is chasing this'}")

        unowned_rows = reg.unowned(conn)
        if unowned_rows:
            print(f"\nON THE REGISTER, NOBODY AGAINST IT — {len(unowned_rows)} rows")
            print("  These carry a date and no owner, so the alert fires at")
            print("  nobody. Until this file was corrected they were shown as")
            print("  owned by a hardcoded address, which is worse than silence:")
            print("  it read as assigned (§1.1).\n")
            for row in unowned_rows:
                print(f"  {row['kind']:14} {row['ref'][:50]:50} "
                      f"missing {row['missing']}")

        if undated_rows:
            print(f"\nON THE REGISTER, ALERTING ON NOTHING — {len(undated_rows)} rows")
            print("  These exist but carry no date, so no alert can fire for")
            print("  them. §2.2: a lapsed prequalification shows up as silence,")
            print("  not rejection — which is what an undated row looks like.\n")
            for row in undated_rows:
                status = f" [{row['status']}]" if row["status"] else ""
                print(f"  {row['kind']:14} {row['ref'][:40]:40}{status}")
                print(f"{'':17}missing {row['missing']} — owner "
                      f"{row['owner'] or 'NOT ASSIGNED'}")

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


def cmd_classify_scan(args) -> int:
    """§9 category profile over the Stage A scan output (metadata only).

    Distinct from `classify`, which is the O-04 confidentiality
    worksheet. This one answers a different question: of the mail
    already scanned, what would §9 have called it?

    Not a live cycle — no mailbox is touched, no reply is produced, no
    verdict is reached. The classifier runs over metadata already on
    disk so its behaviour on real corporate mail is visible before
    anything depends on it."""
    from .config import load_config
    from .discovery.classify_scan import (
        BODY_DEPENDENT, build_classifier, classify_rows, load_rows, merge, render,
    )

    control_root = Path(args.control_root)
    discovery = control_root / "discovery"
    scans = sorted(discovery.glob("outlook-scan-*.jsonl"))
    if not scans:
        print(f"no scan output in {discovery}. Run outlook-scan or phase0 first.")
        return 1

    wanted = {m.strip().lower() for m in args.mailbox.split(",") if m.strip()}
    config = load_config(control_root / "config")
    classifier, limitations = build_classifier(config)

    reports = []
    for scan in scans:
        rows = load_rows(scan)
        if not rows:
            print(f"{scan.name}: empty, skipped")
            continue
        mailbox = str(rows[0].get("mailbox") or scan.stem)
        if wanted and mailbox.lower() not in wanted:
            continue
        report = classify_rows(rows, classifier, mailbox=mailbox)
        reports.append(report)
        top = ", ".join(f"{c} {n}" for c, n in report.by_category.most_common(4))
        print(f"  {mailbox}: {report.rows} messages — {top}")

    if not reports:
        print("nothing matched. Check --mailbox.")
        return 1

    merged = merge(reports)
    merged.limitations = limitations
    out = discovery / "CLASSIFY-SCAN.md"
    out.write_text(render(merged), encoding="utf-8")

    print(f"\n{merged.rows} messages classified across {len(reports)} mailbox(es)")
    for category, n in merged.by_category.most_common():
        print(f"  {category:26} {n:6}  {n / merged.rows:5.1%}")
    print(f"\nsecurity events: {len(merged.security_events)}")
    print("NOT detectable from metadata: " + ", ".join(BODY_DEPENDENT))
    print("  (a zero against those is a property of the input, not a finding)")
    print(f"\nwritten: {out}")
    return 0


def cmd_contracts(args) -> int:
    """Stage C — commercial terms from documents (§6)."""
    import yaml

    from .discovery.stage_c import render_commercial_exposure, run_stage_c

    control_root = Path(args.control_root)
    if not args.source:
        print("no --source and no UB_ROOT set. Nothing scanned.")
        return 1

    # Several folders may be given, comma-separated. A full-drive scan of
    # a real document store runs for hours, and this command writes only
    # once at the end — an interrupted run loses the whole scan. Naming
    # the folders that actually hold contracts builds the same register
    # without the all-or-nothing exposure.
    sources = [Path(s.strip()) for s in str(args.source).split(",") if s.strip()]
    missing = [s for s in sources if not s.is_dir()]
    sources = [s for s in sources if s.is_dir()]

    # One folder named wrongly used to refuse the whole scan. On a
    # five-folder run where four were fine that costs the whole hour and
    # teaches the operator to drop folders from the list, which is the
    # opposite of what a refusal is for. The scan now runs on what
    # exists and carries the miss through to the report, so the output
    # states its own incompleteness rather than looking complete.
    for s in missing:
        print(f"source folder not found: {s}")
        parent, prefix = s.parent, s.name.split()[0] if s.name.split() else ""
        if parent.is_dir() and prefix:
            near = sorted(p.name for p in parent.iterdir()
                          if p.is_dir() and p.name.startswith(prefix))
            if near:
                print("  did you mean: " + " | ".join(f"{n!r}" for n in near))
    if not sources:
        print("no source folder exists. Nothing scanned.")
        return 1
    if missing:
        print(f"scanning the {len(sources)} folder(s) that do exist; the "
              f"{len(missing)} above are named in the report as not scanned.")

    clients, folders, projects = [], [], []
    config = control_root / "config" / "confidential.yaml"
    if config.is_file():
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        clients = [c.get("name", "") for c in data.get("confidential_clients", [])]
        folders = list(data.get("confidential_folders") or [])
        projects = list(data.get("confidential_projects") or [])
    else:
        print("WARNING: config/confidential.yaml not found — falling back to the "
              "§12.1.1 default client list. Run 'init' first.")
        clients = ["Siemens Energy", "Saint-Gobain", "KNAUF", "Galaxy",
                   "Canal Sugar", "Sukari", "Air Liquide"]

    print(f"scanning {len(sources)} folder(s) for commercial terms")
    print(f"confidential clients: {len(clients)} | folders: {len(folders)}")
    if args.confidential_dates:
        print("D-05 ACTIVE: dates and term durations will be extracted from "
              "confidential contracts; no clause text is retained.")

    # Durable per-document outcomes. OCR over a real document store runs
    # for hours; without this an interrupted scan loses everything and the
    # next attempt starts from zero (§1.1 — a partial view must not be
    # thrown away, it must be recorded).
    cache_dir = None if args.no_cache else control_root / "data" / "stage-c-cache"
    if cache_dir:
        print(f"cache: {cache_dir}")

    ocr = None
    args_ocr_unavailable = ""
    if args.ocr:
        from .ocr import available, ocr_document

        usable, reason = available()
        if not usable and "Arabic" in reason:
            # A HALF-configured engine. English-only OCR over Arabic scans
            # fabricates text, and a fabricated clause is worse than the
            # gap it replaces (§1.1, §5.5). This one is worth refusing.
            print(f"OCR requested but unusable: {reason}")
            print("Refusing to scan with a half-configured engine — scanned "
                  "documents would be silently misread rather than recorded "
                  "as gaps (§1.1, §5.5).")
            return 1
        if not usable:
            # NO engine is a different case, and refusing it cost the whole
            # of Stage C for want of a component most of the documents do
            # not need. Without OCR a scanned document is recorded as
            # UNREADABLE with the reason — the honest gap §5.5 asks for —
            # while every text-readable contract still yields its
            # guarantees. Losing those too is not caution, it is a worse
            # answer than the one being avoided.
            print(f"OCR requested but unavailable: {reason}")
            print("Continuing WITHOUT OCR. Scanned documents will be "
                  "recorded as UNREADABLE with that reason rather than "
                  "guessed at (§5.5), and the count is in the report. "
                  "Text-readable contracts are unaffected.")
            args_ocr_unavailable = reason

        if usable:
            floor = args.ocr_floor
            print(f"OCR ACTIVE: {reason}")
            print(f"  confidence floor {floor} — below it a document is "
                  "UNREADABLE, not evaluated, not posted (§5.5)")
            if args.confidential_dates:
                print("  Confidential contracts ARE included, under decision "
                      "D-14 (17-Aug-2026):")
                print("  dates and term durations only, and the OCR text is "
                      "never retained — it is")
                print("  dropped at capture, so no clause text reaches a "
                      "register or a report.")
            else:
                print("  Confidential documents are NOT OCR'd on this run. "
                      "D-14 permits it for")
                print("  dates only, and only with --confidential-dates.")

            def ocr(path, _floor=floor):
                return ocr_document(path, floor=_floor)

    from .discovery.stage_c import StageCResult

    result = StageCResult()
    def scan_progress(stage, done, total, current, _last=[0.0]):
        """Say enough to tell working from hung, without flooding.

        A run over a real document store takes hours. Printing every
        document would bury the summary; printing nothing — which is
        what this did — leaves the operator choosing between waiting on
        faith and killing work that was fine.
        """
        import time

        if stage == "enumerating":
            print("    walking the folder tree — no documents opened yet, "
                  "this alone takes minutes on a full drive", flush=True)
        elif stage == "enumerated":
            print(f"    {total} document(s) to consider", flush=True)
        elif stage == "processing":
            now = time.monotonic()
            if done == 1 or now - _last[0] >= 15:
                _last[0] = now
                print(f"    {done}/{total}  {current[:70]}", flush=True)
        elif stage == "done":
            print(f"    {total}/{total} complete", flush=True)

    for source in sources:
        print(f"  {source}")
        part = run_stage_c(source, clients, folders, exclude=[control_root],
                           progress=scan_progress,
                           permit_confidential_dates=args.confidential_dates,
                           confidential_projects=projects, ocr=ocr,
                           cache_dir=cache_dir,
                           ocr_floor=args.ocr_floor if args.ocr else None)

        # Paths inside each part are relative to that part's own root, so
        # merging them raw would produce citations that no longer say
        # which folder a document came from. §1.2 wants a reference that
        # resolves; prefix each with its folder name before merging.
        prefix = source.name
        seen: dict[int, object] = {}
        for record in part.documents + part.blocked + part.unreadable:
            if id(record) not in seen:
                seen[id(record)] = record
                record.path = f"{prefix}/{record.path}"
        for term in part.terms:
            term.source = f"{prefix}/{term.source}"

        result.documents.extend(part.documents)
        result.terms.extend(part.terms)
        result.blocked.extend(part.blocked)
        result.unreadable.extend(part.unreadable)
        result.d05_extracted.extend(f"{prefix}/{p}" for p in part.d05_extracted)
        for name in ("ocr_attempted", "ocr_read", "ocr_below_floor", "ocr_failed"):
            getattr(result, name).extend(
                f"{prefix}/{entry}" for entry in getattr(part, name))
        # Counts and numbers, not paths — nothing to prefix. Without
        # this the cache works and silently reports reusing nothing,
        # which is the one number worth seeing after a scan that took
        # hours the first time.
        result.ocr_confidences.extend(part.ocr_confidences)
        result.from_cache += part.from_cache
        result.re_extracted += part.re_extracted
        print(f"    {len(part.documents)} documents, {len(part.terms)} terms, "
              f"{len(part.blocked)} confidential, {len(part.unreadable)} unreadable")

    out = control_root / "discovery" / "COMMERCIAL-EXPOSURE.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_commercial_exposure(result,
                                   not_scanned=[str(m) for m in missing],
                                   scanned=[str(s) for s in sources],
                                   ocr_unavailable=args_ocr_unavailable),
        encoding="utf-8")

    # The wire from the report to the thing that actually alerts. §2.2
    # schedules guarantees at 60/30/14/7 days off the class 2 registers,
    # which are populated by `registers --import-file` from a YAML
    # nothing produced — so until now a guarantee expiry Stage C found
    # sat in a markdown file and alerted on nothing. Proposing is
    # inference and happens here; importing is a separate deliberate act
    # and that act is the approval (§1.1).
    from .discovery import class2_proposal

    today = date.today()
    proposal = class2_proposal.propose(result.terms, today)
    proposed_yaml = control_root / "discovery" / "PROPOSED-CLASS2-REGISTERS.yaml"
    proposed_yaml.write_text(class2_proposal.to_yaml(proposal, today),
                             encoding="utf-8")
    (control_root / "discovery" / "PROPOSED-CLASS2-REGISTERS.md").write_text(
        class2_proposal.render(proposal, today), encoding="utf-8")

    print(f"\ndocuments seen:      {len(result.documents)}")
    print(f"terms extracted:     {len(result.terms)}")
    print(f"confidential, unread: {len(result.blocked)}  (D-01)")
    if result.d05_extracted:
        print(f"confidential, dates only: {len(result.d05_extracted)}  (D-05)")
    print(f"unreadable/scanned:   {len(result.unreadable)}  (OCR needed)")
    if result.from_cache:
        print(f"reused from cache:    {result.from_cache}")
    if result.re_extracted:
        # Counted apart from `from_cache` because they are not the same
        # claim: one says nothing was redone, the other says only the
        # expensive half was skipped. Reading "reused from cache: 957"
        # after a fix is what hid a whole broken run this morning.
        print(f"  of which re-read under the current term patterns: "
              f"{result.re_extracted} (text cached, document not reopened)")
    if result.ocr_attempted:
        print(f"\nOCR: {len(result.ocr_attempted)} attempted, "
              f"{len(result.ocr_read)} trusted, "
              f"{len(result.ocr_below_floor)} below the §5.5 floor, "
              f"{len(result.ocr_failed)} failed")
        if len(result.ocr_read) < len(result.ocr_attempted):
            print("  Documents not trusted stay UNREADABLE and post nothing. "
                  "That is the floor")
            print("  working, not a bug — a wrong date in a register is worse "
                  "than no date (§5.5).")
        seen = sorted(result.ocr_confidences)
        if seen:
            median = seen[len(seen) // 2]
            print(f"\n  confidence across {len(seen)} reading(s): "
                  f"min {seen[0]:.1f}, median {median:.1f}, max {seen[-1]:.1f}")
            print(f"  The floor is currently {args.ocr_floor:.0f}. It is a "
                  "governance number, not a tuning knob —")
            print("  set it from this distribution rather than from a default "
                  "chosen without")
            print("  seeing your documents (§5.5). Lowering it is never a "
                  "learned change (§14.4).")
    dated = [t for t in result.terms if t.found_date]
    if dated:
        soonest = sorted(dated, key=lambda t: t.found_date)[:5]
        print(f"\nnearest dated terms ({len(dated)} of {len(result.terms)} "
              "terms carry a date):")
        for term in soonest:
            print(f"  {term.found_date}  {term.kind:20} {term.source[:50]}")
    print(f"\nwritten: {out}")
    print(f"class 2 proposals: {proposal.count} row(s) ready to import, "
          f"{len(proposal.blocked)} term(s) need a person")
    if proposal.count:
        print("  review, then import — importing is what makes them alert:")
        print(f"    python -m control registers --control-root "
              f"\"{args.control_root}\" --import-file \"{proposed_yaml}\"")
    print("  why the rest could not be proposed: "
          f"{control_root / 'discovery' / 'PROPOSED-CLASS2-REGISTERS.md'}")
    return 0


def cmd_init(args) -> int:
    """Create CONTROL_ROOT from the repository's config templates."""
    from .bootstrap import (
        adopt_drift, adopt_key, bootstrap, config_drift, render_drift,
        render_result,
    )

    repo_config = Path(__file__).resolve().parent.parent.parent / "config"
    template = Path(args.templates) if args.templates else repo_config
    result = bootstrap(Path(args.control_root), template)
    print(render_result(result))

    for spec in args.adopt_key:
        try:
            print(f"\n{adopt_key(Path(args.control_root), template, spec)}")
        except HaltError as e:
            print(f"\nnot adopted: {e}")
            return 1

    # Kept files are never overwritten, so a decision taken after this
    # machine was set up would otherwise never arrive.
    drift = config_drift(Path(args.control_root), template)
    if drift and args.adopt:
        added = adopt_drift(Path(args.control_root), template,
                            accept_template=args.accept_template)
        print(f"\nadopted {len(added)} change(s):")
        for line in added:
            print(f"  + {line}")
        remaining = config_drift(Path(args.control_root), template)
        if remaining:
            print("\nLeft for you. Each of these is a real local value "
                  "against a real template value —")
            print("two decisions disagreeing, and yours may be the newer "
                  "one. Control saying which is")
            print("current would be Control deciding:")
            for line in remaining:
                print(f"  - {line}")
            print("\nIf the template side is the current decision, take it "
                  "for that file in one step:")
            for name in sorted({line.split(":")[0] for line in remaining}):
                print(f"  python -m control init --adopt --accept-template "
                      f"{name} --control-root \"{args.control_root}\"")
        else:
            print("\nNothing left differing. Your config now carries every "
                  "decision the templates hold.")
    elif drift:
        print()
        for line in render_drift(drift):
            print(line)
        print("\nTo close every difference that cannot discard a decision "
              "— missing keys, entries and\nfields, and placeholder values "
              "the templates now answer:")
        print(f"  python -m control init --adopt "
              f"--control-root \"{args.control_root}\"")

    print("\nNext:")
    print(f"  python -m control verify --control-root \"{args.control_root}\"")
    print(f"  python -m control phase0 --control-root \"{args.control_root}\"")
    return 0


def cmd_doctor(args) -> int:
    """Check that this machine can actually run Control."""
    import importlib
    import platform
    import shutil

    from .config import load_config

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
        repo_config = Path(__file__).resolve().parent.parent.parent / "config"
        if repo_config.is_dir():
            from .bootstrap import config_drift
            drift = config_drift(control_root, repo_config)
            if drift:
                print(f"  [warn] config is behind the templates in "
                      f"{len(drift)} place(s)")
                print("         python -m control init --adopt   "
                      "(additive; nothing local is changed)")
                for line in drift[:5]:
                    print(f"         {line}")
                if len(drift) > 5:
                    print(f"         ... and {len(drift) - 5} more")
        if config_count < 15:
            ok = False
            print("    run: python -m control init --control-root <path>")
    else:
        print("\nNo CONTROL_ROOT given (--control-root or $CONTROL_ROOT)")
        ok = False

    # Outlook, actually asked rather than assumed. D-08 puts the engine
    # on the COM route for DISCOVERY and DRY_RUN, and every mailbox
    # Control reads comes through it.
    print("\nOUTLOOK (D-08) — the route the mailbox scan uses:")
    try:
        from .outlook import available_mailboxes

        mailboxes, problem = available_mailboxes()
        windows = platform.system() == "Windows"
        if problem:
            # Only a failure where the route could work. Off Windows
            # this is informational: Outlook is legitimately absent and
            # §5.1 puts the engine on Graph there anyway, so counting it
            # against READY would report a machine as broken for not
            # being the laptop.
            ok = ok and not windows
            print(f"  [{'MISSING' if windows else 'n/a  '}] {problem[:180]}")
            print("            Classic Outlook for Windows must be installed, "
                  "signed in and running.")
            print("            The 'new Outlook' app exposes no COM "
                  "interface at all — in classic Outlook,")
            print("            File → Options is the giveaway; new Outlook "
                  "has no such menu.")
        elif not mailboxes:
            ok = ok and not windows
            print("  [MISSING] Outlook answered and the profile holds no "
                  "mailbox Control can read.")
        else:
            print(f"  [ok]   {len(mailboxes)} mailbox(es) in the profile")
            scoped = str((load_config(control_root / "config")
                          .get("mailbox-scope") or {}).get("mailboxes") or []) \
                if control_root and (control_root / "config").is_dir() else ""
            for address in mailboxes:
                marker = "reads" if address in scoped else "     "
                print(f"           {marker}  {address}")
            print("           'reads' marks a mailbox in the configured "
                  "scope (§3.1a). The rest are")
            print("           visible to the profile and out of scope — "
                  "seeing a mailbox is not")
            print("           authority to read it, which is D-08's whole "
                  "objection to this route.")
    except Exception as e:                      # noqa: BLE001
        print(f"  [warn] could not test the Outlook route: {str(e)[:140]}")

    # OCR (§5.5). Reported separately and never counted toward READY:
    # its absence does not stop Control running, it decides whether
    # scanned documents become records or stay declared gaps. Arabic is
    # checked explicitly — an English-only engine turned loose on Arabic
    # contracts returns confident nonsense, which §1.1 rates worse than
    # the gap it replaces.
    print("\nOCR (§5.5) — scanned documents:")
    ocr_ready = True
    for module, why in (("pytesseract", "Tesseract binding"),
                        ("PIL", "image handling"),
                        ("pymupdf", "PDF rasterising")):
        try:
            importlib.import_module(module)
            print(f"  [ok]   {module:20} — {why}")
        except ImportError:
            ocr_ready = False
            print(f"  [warn] {module:20} — {why} (pip install {module})")

    # Resolve the language directory rather than trusting TESSDATA_PREFIX.
    # Language data installed under LOCALAPPDATA is invisible to any
    # process that did not inherit that variable — a scheduled run, a
    # service, a fresh shell — so a check that reads the ambient
    # environment reports "Arabic missing" on the same machine where it
    # is present. Look in the known places and say which one answered.
    tessdata = ""
    for candidate in (os.environ.get("TESSDATA_PREFIX", ""),
                      str(Path(os.environ.get("LOCALAPPDATA", "")) / "tessdata"),
                      str(Path(_TESSERACT_DEFAULT).parent / "tessdata")):
        if candidate and (Path(candidate) / "eng.traineddata").is_file():
            tessdata = candidate
            break

    languages: list[str] = []
    try:
        import pytesseract

        binary = shutil.which("tesseract") or _TESSERACT_DEFAULT
        if binary and Path(binary).is_file():
            pytesseract.pytesseract.tesseract_cmd = str(binary)
            print(f"  [ok]   tesseract binary     — {pytesseract.get_tesseract_version()}")
            if not shutil.which("tesseract"):
                print(f"         not on PATH; found at {binary}")
            # Via the environment, not --tessdata-dir: pytesseract splits
            # its config string on whitespace, so a path with spaces
            # arrives broken (see ocr._apply_tessdata).
            if tessdata:
                os.environ["TESSDATA_PREFIX"] = tessdata
            languages = sorted(pytesseract.get_languages(config=""))
            if tessdata:
                print(f"  tessdata: {tessdata}")
        else:
            ocr_ready = False
            print("  [warn] tesseract binary     — not found "
                  "(winget install UB-Mannheim.TesseractOCR)")
    except Exception as e:
        ocr_ready = False
        print(f"  [warn] tesseract binary     — {str(e)[:80]}")

    if languages:
        print(f"  languages: {', '.join(languages)}")
        if "ara" not in languages:
            ocr_ready = False
            print("  [warn] Arabic language data MISSING — §5.5 requires Arabic "
                  "support.")
            print("         Fetch ara.traineddata from tessdata_best into the "
                  "tessdata directory")
            print("         above. The winget package ships English only. "
                  "Without ara, scanned Arabic")
            print("         documents must stay UNREADABLE rather than be run "
                  "through an engine")
            print("         that cannot read them (§1.1).")
    print(f"  OCR usable: {'yes' if ocr_ready else 'no — scanned documents stay UNREADABLE'}")
    if ocr_ready:
        print("  Stage C will use it: python -m control contracts --ocr")
        print("  Confidential contracts are included only with "
              "--confidential-dates,")
        print("  under D-14, and their OCR text is never retained.")

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

    # §5.6: state, integrity, roots — then the mailbox, not before.
    report = _startup(args)

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

    # The profile is not the authority on what may be read — every
    # enumerated mailbox goes through the §3.1a gate, which permits a
    # Phase 0 archive read in DISCOVERY and refuses it in any other mode.
    for note in _check_mailbox_scope(",".join(mailboxes), report):
        print(f"SCOPE: {note}")

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
        apply_worksheet, build_rows, client_hints_from_config, read_worksheet,
        write_worksheet,
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

    # Hints come from the confirmed client list, so a client added to
    # confidential.yaml is never proposed NOT_CONFIDENTIAL here.
    import yaml as _yaml

    config_path = control_root / "config" / "confidential.yaml"
    hints = client_hints_from_config(
        _yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if config_path.is_file() else None)
    domains = build_rows(rows, hints)
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


def cmd_cycle(args) -> int:
    """One sweep — §5.6 order, §10 gates, nothing sent that the mode
    does not permit."""
    import yaml

    from .backup import ensure_daily_backup
    from .cycle import run_cycle
    from .db import connect
    from .enforce import Enforcer
    from .loader import load_class2, load_for_cycle
    from .report import report_recipients

    control_root = Path(args.control_root)
    report = _startup(args)                      # halts on illegal state
    today = date.fromisoformat(args.today) if args.today else date.today()

    # §5.2: back up before the first write. A cycle that cannot protect
    # the record it is about to change does not proceed silently.
    backup_config = yaml.safe_load(
        (control_root / "config" / "backup.yaml").read_text(encoding="utf-8")) or {}
    backup = ensure_daily_backup(control_root, backup_config, on_date=today)
    for gap in backup.gaps:
        print(f"BACKUP GAP: {gap}")
    if backup.written and backup.files:
        print(f"backup: {backup.path.name} ({backup.files} files)")

    conn = connect(report.db_path)
    try:
        loaded = load_for_cycle(report.config, conn, today,
                                logs_dir=control_root / "logs")
        class2 = load_class2(conn)
        tracked = loaded.tracked + class2

        people = report.config["people"]
        ceo = _role(people, 4) or "ahmed@ubcsis.com"
        coo = _role(people, 3, "COO")
        cfo = _role(people, 3, "CFO")

        print(f"\nobligations approved and tracked: {loaded.approved}")
        print(f"tracked deadlines: {len(tracked)} "
              f"(class 2 from the registers: {len(class2)})")
        if loaded.gaps:
            print(f"\nGAPS — {len(loaded.gaps)}. Each is a thing Control "
                  "is NOT doing:\n")
            for gap in loaded.gaps:
                print(f"  - {gap}")

        transport = _transport_for(report, args)
        if transport is None:
            print("\nNo transport available. Nothing fetched, nothing sent.")
            print("Phase 0/1 run on Outlook (D-08); Graph is required from "
                  "Phase 2.")
            return 1

        result = run_cycle(
            report, transport, control_root,
            specs=loaded.specs, tracked_items=tracked,
            class3_state=loaded.class3_state,
            enforcer=Enforcer(loaded.calendar, loaded.roster,
                              ceo=ceo, coo=coo, cfo=cfo),
            watchdog=_watchdog_for(report, conn, loaded),
            today=today, ceo=ceo, cfo=cfo, coo=coo,
        )
    finally:
        conn.close()

    print(f"\nprocessed:        {result.processed}")
    print(f"verdicts:         {len(result.verdicts)}")
    print(f"sent:             {len(result.sent)}")
    print(f"drafted:          {len(result.drafted)}")
    print(f"duplicates held:  {result.skipped_duplicates}")
    if result.quarantined:
        print(f"quarantined:      {len(result.quarantined)} — reported, never opened")
    if result.security_events:
        print(f"SECURITY EVENTS:  {len(result.security_events)} — see the audit log")

    if result.locked_period_refusals:
        print(f"\nPERIOD LOCK (§5.2) — {len(result.locked_period_refusals)} "
              "submission(s) not posted:")
        for refusal in result.locked_period_refusals:
            print(f"  {refusal}")
        print("  The period was reported on. Posting these needs a "
              "CEO-approved correction and a reissued report revision — "
              "Control raises that decision, it does not take it.")

    if result.flags_raised or result.flags_suppressed:
        print("\nANOMALY FLAGS (§7.3)")
        print(f"  raised to the CEO:  {result.flags_raised}")
        if result.flags_suppressed:
            print(f"  held over budget:   {result.flags_suppressed} — recorded "
                  "and reported, never dropped (D-10)")
        print("  These never change a verdict and never appear in the "
              "submitter's reply.")

    if result.threads_opened or result.cc_compliance:
        metric = result.cc_compliance or {}
        print("\nEXTERNAL WATCHDOG (§8.5)")
        print(f"  threads opened this sweep: {result.threads_opened}")
        print(f"  closed by declaration:     {result.threads_closed_declared}")
        print(f"  open / breached:           "
              f"{metric.get('OPEN', 0)} / {metric.get('BREACHED', 0)}")
        share = metric.get("observed_share")
        if share is not None:
            print(f"  closed by a reply Control could see: {share:.0%} — the "
                  "rest were declared")
            print("  This is the CC-compliance metric, and live evidence for "
                  "the §3.1a scope question.")
        if result.threads_without_id:
            print(f"  {result.threads_without_id} message(s) carried no "
                  "conversation id — each is tracked as its own thread and "
                  "can only close by an explicit CLOSED reply")
        print("  Every thread is registered as 'unclassified' until a "
              "category can be assigned: §8.5's own catch-all row, owner COO, "
              "backup CEO. Categorising needs either a domain map or reading "
              "bodies, and neither is decided.")
    pending = len(list((control_root / "outbox" / "pending-approval").glob("*.json")))
    if pending:
        print(f"\n{pending} draft(s) awaiting release in "
              f"{control_root / 'outbox' / 'pending-approval'}")
        print("Nothing releases on silence (§10).")

    recipients, note = report_recipients(report.config["distribution"])
    print(f"\nmanagement report would go to: {', '.join(recipients) or 'nobody'}")
    if note:
        print(f"  {note}")
    return 0


def _role(people: dict, tier: int, marker: str = "") -> str:
    for entry in people.get("people") or []:
        if int(entry.get("tier") or 0) != tier:
            continue
        if marker and marker.lower() not in str(entry.get("role", "")).lower():
            continue
        return str(entry.get("email", "")).lower()
    return ""


def _transport_for(report, args):
    """Outlook in DISCOVERY/DRY_RUN, Graph beyond — D-08 already refused
    an illegal combination at startup, so this only picks."""
    route = str((report.config["transport"] or {}).get("route") or "graph").lower()
    if route == "outlook_com":
        from .outlook import OutlookTransport

        mailbox = (report.config["mailbox-scope"] or {}).get(
            "control_mailbox") or "control@ubcsis.com"
        try:
            return OutlookTransport(mailbox, allow_send=args.allow_send)
        except Exception as e:
            print(f"Outlook not available: {str(e)[:140]}")
            return None
    from .transport import GraphTransport

    try:
        return GraphTransport()
    except Exception as e:
        print(f"Graph not available: {str(e)[:140]}")
        return None


def cmd_report(args) -> int:
    """§11 weekly management report — always a draft (§10).

    Everything the charter asks to be visible renders here: the class
    1 & 2 horizon first, open items, external SLA, register deltas,
    anomaly flags, and the decisions and standing limitations that say
    what Control is NOT covering. A report that only showed what was
    found would read as assurance over ground it never saw.
    """
    from .db import connect, lock_period, reported_periods
    from .loader import load_class2, load_for_cycle
    from .outbox import Outbox, OutboundMessage
    from .report import HorizonItem, OpenItem, report_recipients, weekly_report

    control_root = Path(args.control_root)
    report = _startup(args)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    conn = connect(report.db_path)
    try:
        loaded = load_for_cycle(report.config, conn, as_of,
                                logs_dir=control_root / "logs")
        tracked = loaded.tracked + load_class2(conn)

        horizon = [
            HorizonItem(item_id=item.item_id, obligation_class=item.obligation_class,
                        name=item.name, owner=item.owner, due=item.due,
                        status="OPEN")
            for item in tracked if item.obligation_class in (1, 2)
        ]
        open_items = [
            OpenItem(item_id=item.item_id, obligation_class=item.obligation_class,
                     name=item.name, owner=item.owner,
                     days_outstanding=loaded.calendar.working_days_between(
                         item.due, as_of),
                     stage="OPEN")
            for item in tracked
            if item.due < as_of
            and not getattr(loaded.class3_state.get(item.item_id), "submitted", False)
        ]

        # §8.5's standing CC-compliance metric: threads closed by a reply
        # Control could see, versus by declaration. Live evidence for the
        # §3.1a scope question, so it belongs in the pack rather than
        # only in a cycle's console output.
        watchdog = _watchdog_for(report, conn, loaded)
        cc_metric = watchdog.cc_compliance() if watchdog else None

        # The gaps the loader found are decisions the report must carry:
        # each one is something Control is not doing (§1.1).
        rendered = weekly_report(
            conn, as_of=as_of, config_dir=control_root / "config",
            horizon=horizon, open_items=open_items, cc_metric=cc_metric,
            tracked=loaded.tracked,
            open_decisions=loaded.gaps, control_root=control_root)
    finally:
        conn.close()

    recipients, note = report_recipients(report.config["distribution"])
    outbox = Outbox(control_root, report.state.run_mode,
                    ceo=recipients[0] if recipients else "ahmed@ubcsis.com")
    disposition = outbox.submit(
        OutboundMessage(
            kind="MANAGEMENT_REPORT",
            subject=rendered["subject"],
            body=rendered["body"],
            recipients=list(recipients),
            dedupe_key=f"REPORT:{as_of.isoformat()}",
            rationale="§11 weekly management report"),
        already_sent=outbox.known_dedupe_keys())

    year_dir = control_root / "reports" / "management" / str(as_of.year)
    written = year_dir / f"weekly-{as_of.isoformat()}.md"

    if disposition.action == "SKIPPED_DUPLICATE":
        # The first run's draft is the one awaiting release. Rewriting the
        # file underneath it would leave the copy on disk saying something
        # the pending draft does not (§1.10, §5.2 append-only).
        print(f"Already produced for {as_of:%d-%b-%Y} — not duplicated (§1.10).")
        print(f"The draft awaiting release holds that version; {written} is "
              "left as it was.")
        print("To reissue after a correction, release or discard the pending "
              "draft first.")
        return 0

    year_dir.mkdir(parents=True, exist_ok=True)
    written.write_text(rendered["body"], encoding="utf-8")

    # §5.2: once a management report issues, the period locks. Only the
    # periods this report actually said something about — a period it
    # was silent on was not reported, and locking it would refuse later
    # entries the report never claimed to cover.
    conn = connect(report.db_path)
    try:
        report_ref = f"WEEKLY-{as_of.isoformat()}"
        # The same seven-day window the report itself covers.
        since = datetime.combine(as_of - timedelta(days=7), datetime.min.time())
        newly_locked = [p for p in reported_periods(conn, since.isoformat(sep=" "))
                        if lock_period(conn, p, report_ref)]
    finally:
        conn.close()

    print(rendered["body"])
    print("\n" + "=" * 60)
    print(f"written:    {written}")
    print(f"xlsx:       {rendered['xlsx_path']}")
    print(f"recipients: {', '.join(recipients) or 'nobody configured'}")
    if note:
        print(f"  {note}")
    if newly_locked:
        print(f"\nPERIOD LOCK (§5.2): {', '.join(newly_locked)}")
        print("  A later entry into a locked period needs a CEO-approved "
              "correction and a reissued revision of this report.")
    if disposition.action == "DRAFT":
        print(f"\nDRAFT {disposition.draft_id} — management reports are never "
              "auto-sent, in any mode (§10). Nothing releases on silence.")
    return 0


def cmd_diagnose_dates(args) -> int:
    """Why terms carry no date — measured, not guessed (§1.1).

    Two scans produced 525 terms and 2 dated ones, and two fixes made on
    reasoning alone did not move it. This counts what is in the cached
    text so the next change answers evidence.
    """
    from .discovery import date_diagnosis

    cache = Path(args.control_root) / "data" / "stage-c-cache"
    result = date_diagnosis.diagnose(cache)
    print(date_diagnosis.render(result))
    return 0


def cmd_status(args) -> int:
    """One page of what the runs actually found.

    Everything here already exists in the register, the database, the
    Stage C cache and the config. Scattered across six outputs it cannot
    be weighed, and the question of whether to continue this project
    should not rest on a summary of a summary.
    """
    from . import status as st

    control_root = Path(args.control_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    report = st.render(st.build(control_root, today), today)
    print(report)

    out = control_root / "reports" / f"status-{today:%Y-%m-%d}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\nwritten: {out}")
    return 0


def cmd_ocr_floor(args) -> int:
    """What each OCR confidence floor would admit — §5.5, §14.4.

    The floor is at 60 because 60 is the default, which §5.5 names as
    the wrong reason: it is a governance number to be set from this
    estate's own documents. Reports only — §14.4 forbids learning from
    lowering it, and nothing here changes a setting.
    """
    from .discovery import ocr_floor

    control_root = Path(args.control_root)
    evidence = ocr_floor.gather(control_root / "data" / "stage-c-cache",
                                floor_in_force=args.ocr_floor)
    print(ocr_floor.render(evidence))
    return 0


def cmd_terms(args) -> int:
    """§5.5 — the work queue for what OCR could not reach."""
    from .db import connect
    from .discovery.manual_terms import apply_rows, read_worksheet

    control_root = Path(args.control_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    worksheet = (Path(args.apply) if args.apply
                 else control_root / "discovery" / "MANUAL-TERMS.csv")

    if not args.apply:
        print(f"To create the worksheet, run the contracts scan — it writes\n"
              f"  {worksheet}\n"
              "listing every document that produced no usable terms.\n\n"
              "Fill TERM_KIND, DATE_yyyy_mm_dd or VALUE, and COUNTERPARTY,\n"
              "then re-run this with --apply <path>.")
        return 0

    if not worksheet.is_file():
        print(f"worksheet not found: {worksheet}")
        return 1

    rows, problems = read_worksheet(worksheet)
    if problems:
        print("The worksheet has entries Control will not interpret:\n")
        for problem in problems:
            print(f"  {problem}")
        print("\nNothing applied. A guessed date in a class 2 register alerts "
              "confidently on the wrong day (§1.1).")
        return 1
    if not rows:
        print("No terms entered. Nothing applied.")
        return 1

    db_path = control_root / "data" / "control.db"
    if not db_path.exists():
        print(f"no database at {db_path}. Run 'init' first.")
        return 1
    conn = connect(db_path)
    try:
        counts = apply_rows(conn, rows, entered_by=args.entered_by,
                            on_date=today)
    finally:
        conn.close()

    print(f"applied {len(rows)} term(s) from {worksheet.name}")
    for register, count in counts.items():
        if count:
            print(f"  {register}: +{count}")
    print(f"\nRecorded as BACKFILL entered by {args.entered_by} (§5.2), so a "
          "hand-read value stays distinguishable from a machine-read one.")
    print("Check the horizon:  python -m control registers")
    return 0


def _watchdog_for(report, conn, loaded):
    """The §8.5 watchdog, or None when no external SLA is configured.

    Absence of `external_sla` means the SLAs have not been set, and a
    watchdog with no rules would breach nothing while looking like a
    running control.
    """
    from .watchdog import Watchdog, parse_sla_config

    rules = parse_sla_config((report.config["sla"] or {}).get("external_sla"))
    if not rules:
        return None
    managers = {email: person.manager
                for email, person in loaded.roster.items() if person.manager}
    return Watchdog(conn, rules, loaded.calendar, managers)


def cmd_disputes(args) -> int:
    """§8.4 — list disputes awaiting a ruling, or record one.

    A dispute suspends the escalation clock on its item. Without a way
    to rule, the suspension has no end and the appeal path doubles as a
    way to stop enforcement indefinitely (finding V4).
    """
    from . import disputes as dsp
    from .config import load_config
    from .db import connect

    control_root = Path(args.control_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    conn = connect(control_root / "data" / "control.db")
    try:
        people = load_config(control_root / "config")["people"]
        ceo = _role(people, 4) or "ahmed@ubcsis.com"
        coo = _role(people, 3, "COO")

        if not (args.uphold or args.reject):
            open_disputes = dsp.pending(conn, today)
            if not open_disputes:
                print("No disputes pending adjudication.")
                return 0

            print(f"{len(open_disputes)} dispute(s) awaiting a ruling (§8.4). "
                  "The escalation clock on each item is suspended until one "
                  "is recorded.\n")
            for item in open_disputes:
                marker = " — PAST THE §8.4 VISIBILITY LINE" if \
                    item.days_open >= dsp.VISIBILITY_DAYS else ""
                print(f"  [{item.dispute_id}] raised by {item.raised_by} on "
                      f"{item.raised_at:%d-%b-%Y}, {item.days_open} days "
                      f"open{marker}")
                if item.linked:
                    print(f"       contests {item.verdict} on "
                          f"{item.obligation_id} (submission "
                          f"{item.submission_id})")
                else:
                    print("       not linked to a submission — the reply "
                          "could not be matched to what it contests")
            print("\nTo rule:")
            print("  python -m control disputes --uphold <id> "
                  "--reason \"...\"")
            print("  python -m control disputes --reject <id> "
                  "--reason \"...\"")
            print("\nAn upheld dispute becomes a permanent golden case, with "
                  "your ruling as the expected answer (§13.1).")
            return 0

        dispute_id = int(args.uphold or args.reject)
        outcome = "UPHELD" if args.uphold else "REJECTED"
        target = next((d for d in dsp.pending(conn, today)
                       if d.dispute_id == dispute_id), None)

        try:
            ruling = dsp.adjudicate(
                conn, dispute_id, outcome=outcome, by=args.by,
                reason=args.reason, ceo=ceo, coo=coo, on=today)
        except (dsp.AuthorityError, ValueError) as e:
            print(f"Not recorded: {e}")
            return 1

        print(f"dispute {dispute_id}: {outcome}")
        print(f"  recorded as dispute row {ruling['ruling_id']}, appended — "
              "the original row is unchanged (§5.2)")
        if ruling["deputised"]:
            print(f"  logged as deputised for {ceo} during registered absence "
                  "(§3.3, D-12)")
        print("  the escalation clock on this item resumes")

        if outcome == "UPHELD":
            path = dsp.record_golden_requirement(
                control_root, ruling, reason=args.reason,
                obligation_id=target.obligation_id if target else None,
                verdict=target.verdict if target else None, on=today)
            print(f"\n§13.1: this must become a permanent test case.\n"
                  f"  queued in {path}\n"
                  "  Control cannot write the case itself — it holds the "
                  "verdict, not the document.")

        for line in dsp.rejection_pattern(conn):
            print(f"\n§8.6: {line}")
        return 0
    finally:
        conn.close()


# Where contracts, guarantees and delegated limits actually live.
# Everything else on this drive is project documentation.
_CONTRACT_FOLDERS = (
    "6. Clients Legal Documents",
    "7. Suppliers Legal Documents",
    "11. Vendor Registration Request",
    "13. Delegations",
)


def cmd_phase1(args) -> int:
    """Everything Phase 1 can do without a human — §16.

    Phase 1 is DRY_RUN: all classes evaluated, everything a draft,
    nothing sent. That means almost all of it is machine work, and
    running it as eight separate commands turned a build step into an
    afternoon of copying paths between prompts.

    It stops at the two things that are decisions rather than work: the
    CEO approving the obligation register (§6), and the CEO judging the
    golden set unanchored (§13.1, D-03). Neither can be done for them
    without making the gate meaningless — a test the machine cannot
    fail is not a test.

    Each step is skipped rather than fatal when its input is absent, and
    what was skipped is stated at the end. A runner that halts halfway
    and says nothing is worse than the eight commands it replaced.
    """
    control_root = Path(args.control_root)
    steps: list[tuple[str, str]] = []      # (step, outcome)

    def run(label: str, fn, needed: str = "") -> bool:
        print(f"\n{'=' * 62}\n{label}\n{'=' * 62}")
        try:
            code = fn()
        except Exception as e:                      # noqa: BLE001
            steps.append((label, f"FAILED — {str(e)[:120]}"))
            print(f"  step failed: {str(e)[:200]}")
            return False
        outcome = "done" if code == 0 else (needed or "skipped")
        steps.append((label, outcome))
        return code == 0

    from argparse import Namespace

    def like(**over):
        base = dict(vars(args))
        base.update(over)
        return Namespace(**base)

    # 1 — config first. A machine running on last month's decisions
    #     produces honest-looking numbers from the wrong rules.
    run("1. Config — install and adopt every decision the templates hold",
        lambda: cmd_init(like(adopt=True, templates="", adopt_key=[],
                              accept_template=args.accept_template)))

    # 2 — the archive. Skipped without Outlook, which is the normal case
    #     off the laptop.
    if not args.skip_scan:
        run("2. Phase 0 — scan every mailbox and write the deliverables",
            lambda: cmd_phase0(like()),
            needed="skipped — Outlook not available on this machine")

    # 3 — propose the register. This is the join that was missing.
    run("3. Stage D — propose the obligation register (§6)",
        lambda: cmd_register_obligations(
            like(approve=None, by="", min_occurrences=3,
                 min_confidence="MEDIUM")),
        needed="skipped — no scan output to infer from")

    # 4 — what the filing archive says about the statutory rules.
    run("4. Extraction brief — the archive against the stated rules",
        lambda: cmd_extract_brief(like(rescan=False)),
        needed="skipped — no filing evidence config")

    # 5 — the two documents that go to humans outside the company.
    run("5. Advisor brief — the completed statutory table",
        lambda: cmd_advisor_brief(like()))

    # 5b — Stage C. §6 calls COMMERCIAL-EXPOSURE.md the likely
    #      highest-value single output of the build, and it was not in
    #      this chain at all: the guarantee expiries and forfeitable
    #      claim windows were reachable only by a separate command
    #      nobody was told to run.
    #
    #      Scoped to the folders that hold contracts rather than the
    #      whole drive. Measured, not assumed: `14. Construction
    #      Management Files` is 801 of 957 documents and produced 525
    #      terms with one usable date — project files and blank
    #      templates naming a retention because the boilerplate does.
    #      Scanning it costs hours and buys nothing.
    ub_root = Path(args.ub_root) if getattr(args, "ub_root", "") else None
    if ub_root and ub_root.is_dir():
        folders = [ub_root / name for name in _CONTRACT_FOLDERS]
        present = [str(f) for f in folders if f.is_dir()]
        if present:
            run("5b. Stage C — guarantee expiries, notice periods, "
                "accreditations",
                lambda: cmd_contracts(like(
                    source=",".join(present), no_cache=False,
                    ocr=getattr(args, "ocr", False),
                    ocr_floor=getattr(args, "ocr_floor", 60.0),
                    confidential_dates=True)),
                needed="skipped — no contract folder found")

    # 5c — the cases the golden set is built from. Nothing put a case
    #      into pending/, so the Phase 1 gate reported the set as
    #      blocked on the CEO's time when the missing piece was this.
    if ub_root and ub_root.is_dir():
        run("5c. Golden set — build the pending cases from the archive",
            lambda: cmd_golden(like(build=True, issue=False, apply="",
                                    per_obligation=12)),
            needed="skipped — UB_ROOT not reachable")

    # 6 — a full DRY_RUN cycle: everything evaluated, everything drafted.
    if not args.skip_cycle:
        run("6. Cycle — evaluate everything, send nothing (DRY_RUN)",
            lambda: cmd_cycle(like(allow_send=False, mailbox="",
                                   today=args.today)),
            needed="skipped — no transport on this machine")

    # 7 — the report, and the gap register that says what is left.
    run("7. Weekly report — always a draft (§10)",
        lambda: cmd_report(like(as_of=args.today)))
    run("8. Gap register — every open item, typed by who can close it",
        lambda: cmd_gaps(like()))

    print(f"\n{'=' * 62}\nPHASE 1 RUN COMPLETE\n{'=' * 62}")
    for label, outcome in steps:
        marker = "ok " if outcome == "done" else "-- "
        print(f"  {marker}{label.split('.', 1)[-1].strip()} — {outcome}")

    # The run is not the answer. §16's gate is seven conditions and
    # Control can close none of them, so the runner ends by measuring
    # them rather than by reporting that it finished.
    run("9. Phase 1 gate — the seven conditions, measured", lambda: cmd_gate(
        like()))

    # What is left is read off the gate rather than written here. A
    # hardcoded list told the CEO to approve a register he had already
    # approved, which is the fastest way to teach someone that the
    # closing summary is not worth reading.
    print("\nEverything above ran without you. What is left cannot be:")
    print("  see the gate rows immediately above — each names the one "
          "person who can\n  close it, and what they would do. Control "
          "closes none of them by design\n  (§16): a gate the system "
          "could close alone would not be a gate.")
    return 0


def cmd_gate(args) -> int:
    """The Phase 0 and Phase 1 gates, measured — §16, §13.1.

    Control can close none of the seven Phase 1 conditions by itself.
    That is the point of writing them down, and it is why this measures
    rather than decides: each condition becomes a row with its state,
    the evidence actually observed, and the named person who can close
    it.
    """
    from . import phase1 as gate
    from .config import load_config
    from .db import connect, ensure_schema

    control_root = Path(args.control_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    config = load_config(control_root / "config")

    conn = None
    db_path = control_root / "data" / "control.db"
    if db_path.is_file():
        conn = connect(db_path)
        ensure_schema(conn)
    try:
        evidence = gate.gather(control_root, conn, config)
    finally:
        if conn is not None:
            conn.close()

    phase0 = gate.assess_phase0(evidence)
    phase1_items = gate.assess_phase1(evidence)
    for line in gate.console_lines(phase0, phase1_items):
        print(line)

    out_dir = control_root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = out_dir / f"phase1-gate-{today.isoformat()}.md"
    written.write_text(
        gate.render(phase0, phase1_items, evidence, today), encoding="utf-8")
    print(f"\nwritten: {written}")
    return 0


def cmd_register_obligations(args) -> int:
    """Stage D proposals to an approved obligation register — §6.

    Two halves, deliberately apart. Proposing is inference and Control
    does it; approving is the decision that ends Phase 0 and only the
    CEO makes it.
    """
    from . import register as reg
    from .config import load_config
    from .discovery import forms as forms_mod
    from .discovery import register_proposal as proposal
    from .discovery import series as series_mod

    control_root = Path(args.control_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    discovery = control_root / "discovery"
    proposals_path = discovery / "PROPOSED-OBLIGATION-REGISTER.yaml"
    obligations_path = control_root / "config" / "obligations.yaml"

    if args.approve is not None:
        if not args.by:
            print("--by is required. §6 ends Phase 0 when the CEO approves "
                  "the register, and an approval with no name attached is "
                  "not one.")
            return 1
        # Where the register is has to be settled before anything is
        # approved. On the live laptop this command was given a
        # CONTROL_ROOT whose config/ had never been populated, and the
        # CEO's one approval command answered with a stack trace. What
        # he needed was the path it looked at and what is actually
        # there.
        if not obligations_path.is_file():
            print(f"no obligation register at {obligations_path}")
            config_dir = obligations_path.parent
            if not config_dir.is_dir():
                print(f"  {config_dir} does not exist either — this "
                      "CONTROL_ROOT has no config directory, so it is not "
                      "the folder the engine reads.")
            else:
                present = sorted(p.name for p in config_dir.glob("*.yaml"))
                print(f"  {config_dir} exists and holds: "
                      f"{', '.join(present) or 'no .yaml files'}")
            print("  Point --control-root at the CONTROL folder whose "
                  "config/ the engine is reading, or copy the register "
                  "there. Nothing was approved (§1.1: an approval against "
                  "a file that is not there is not an approval).")
            return 1

        only = set(args.approve) or None
        approved, skipped = [], []
        # Two shapes of the same decision. A Stage D run writes proposals
        # to discovery/ and they are moved across; the starter register
        # assigned from the archive on 26-Aug-2026 was written straight
        # into obligations.yaml and is stamped where it sits. Both are
        # run, because which one is present depends on whether Stage D
        # has been re-run on this machine, and neither is the CEO's
        # problem.
        if proposals_path.is_file():
            approved, skipped = reg.approve(
                proposals_path, obligations_path, args.by, only)
        in_place, also_skipped = reg.approve_in_place(
            obligations_path, args.by, only)
        approved += in_place
        skipped += also_skipped
        if not proposals_path.is_file() and not approved and not skipped:
            print(f"nothing to approve — {proposals_path.name} does not "
                  "exist and every row in obligations.yaml is already "
                  "approved or has no computable due date.")
            return 1
        # §1.9: unlogged means it didn't happen. This is the single most
        # consequential decision in the system — the approval that ends
        # Phase 0 (§6) and puts obligations under the class 3 ladder —
        # and it was leaving no hash-chained record at all. The register
        # file itself is not the record: it is a config file, editable
        # by anyone with the folder open, with no chain behind it.
        if approved or skipped:
            from .audit import AuditLog

            AuditLog(control_root / "logs").append("register.approved", {
                "by": args.by,
                "approved": approved,
                "skipped": skipped,
                "register": str(obligations_path),
                "requested": sorted(only) if only else "all",
            })

        print(f"approved {len(approved)} obligation(s) as {args.by}:")
        for item in approved:
            print(f"  + {item}")
        for item in skipped:
            print(f"  - {item}")
        if approved:
            print("\n§6: this is what ends Phase 0. These are now tracked, "
                  "and the class 3 ladder runs on them from the next cycle.")
            print(f"Logged to the audit chain in {control_root / 'logs'} "
                  "(§1.9). Verify with: python -m control verify")
        return 0

    # Built from the DRIVE, not from the mailboxes. Stage D against
    # control@ finds almost nothing: the recurring senders are the tax
    # portal and the e-invoicing gateway, because the company's internal
    # reporting was never sent there. A register built from the mail
    # alone would have proposed an empty class 3 with a clean
    # conscience.
    inventory = discovery / "file-inventory.csv"
    ub_root = Path(args.ub_root) if args.ub_root else None
    if inventory.is_file():
        rows = series_mod.read_inventory(inventory)
        source = f"Stage B inventory ({inventory.name})"
    elif ub_root and ub_root.is_dir():
        # Materialised, because `walk` yields. The generator was counted
        # with len() below and reported as a failed step, so the whole
        # register proposal was skipped on any machine with no Stage B
        # inventory — which is every machine before the first scan.
        rows = list(series_mod.walk(ub_root))
        source = f"direct walk of {ub_root}"
    else:
        print(f"no file inventory at {inventory} and UB_ROOT not reachable. "
              "The register is built from document series on the drive, so "
              "there is nothing to infer from.")
        return 1

    detected = series_mod.detect(rows)
    significant = series_mod.significant(detected)

    manual_root = control_root / "knowledge" / "manuals"
    if ub_root and ub_root.is_dir():
        manual_root = ub_root
    forms_register = forms_mod.build(manual_root)

    statutory = load_config(control_root / "config")["statutory-calendar"]
    register = proposal.build(significant, forms_register, statutory, today)

    discovery.mkdir(parents=True, exist_ok=True)
    proposals_path.write_text(proposal.to_yaml(register), encoding="utf-8")
    gap_analysis = discovery / "GAP-ANALYSIS.md"
    gap_analysis.write_text(
        proposal.render_gap_analysis(register, today), encoding="utf-8")

    print(f"source: {source} — {len(rows)} path(s), {len(detected)} series, "
          f"{len(significant)} significant")
    for line in proposal.render_summary(register):
        print(f"  {line}")
    print(f"\nproposals: {proposals_path}")
    print(f"gap analysis: {gap_analysis}")
    print("\nNothing is tracked until it carries approved_by_ceo (§6). "
          "To approve every proposal with a usable due date:")
    print(f"  python -m control register --approve --by ahmed@ubcsis.com "
          f"--control-root \"{args.control_root}\"")
    return 0


def cmd_authority(args) -> int:
    """Delegated limits from the delegation documents — O-02, §3.2.

    D-06's interim was to observe a month of commitment volume so the
    thresholds came from evidence. Phase 0 records no transactions, so
    the review due 16-Sep-2026 would arrive with the evidence it started
    with. `13. Delegations` is the company's own answer to the same
    question and predates the interim.

    Proposes only. §14.2 Tier C: authority limits are never applied by
    the system.
    """
    from .discovery import authority_proposal as ap
    from .discovery.stage_c import extract_text

    control_root = Path(args.control_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    sources = [Path(s.strip()) for s in str(args.source).split(",") if s.strip()]
    missing = [s for s in sources if not s.is_dir()]
    sources = [s for s in sources if s.is_dir()]
    for s in missing:
        print(f"source folder not found: {s}")
    if not sources:
        print("no source folder exists. Nothing read.")
        return 1

    proposal = ap.Proposal()
    for root in sources:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (
                    ".pdf", ".docx", ".txt", ".md"):
                continue
            text = extract_text(path)
            proposal.documents_read += 1
            if not text:
                proposal.documents_with_no_amount += 1
                continue
            found = ap.extract(text, path.relative_to(root).as_posix())
            if not found:
                proposal.documents_with_no_amount += 1
            proposal.candidates.extend(found)

    discovery = control_root / "discovery"
    discovery.mkdir(parents=True, exist_ok=True)
    (discovery / "PROPOSED-AUTHORITY.md").write_text(
        ap.render(proposal, today), encoding="utf-8")
    (discovery / "PROPOSED-AUTHORITY.yaml").write_text(
        ap.to_yaml(proposal, today), encoding="utf-8")

    print(f"{proposal.documents_read} document(s) read, "
          f"{len(proposal.candidates)} candidate limit(s) found")
    for item in sorted(proposal.candidates, key=lambda c: -c.amount)[:10]:
        print(f"  {item.amount:>14,.0f} {item.currency:<10} {item.source[:44]}")
    print(f"\nworksheet: {discovery / 'PROPOSED-AUTHORITY.md'}")
    print("Nothing is in force. §14.2 Tier C puts authority limits with a "
          "human — copy a\nvalue into config/authority.yaml by hand, with "
          "the holder you decide.")
    return 0


def cmd_advisor_brief(args) -> int:
    """The tax advisor brief — execution order step 5.

    "Send the completed statutory table for correction, not blank rows.
    Request the full filing archive in the same message. Lead with the
    payroll cycle and the corporate return date."

    Generated rather than written, for §11's reason: a number that
    cannot be traced to a row does not appear. The stated column comes
    from the calendar and the observed column from the archive, so
    neither can be typed in by hand and neither can drift.
    """
    from . import advisor
    from . import extraction as ex
    from .config import load_config

    control_root = Path(args.control_root)
    ub_root = Path(args.ub_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    config = load_config(control_root / "config")
    statutory = config["statutory-calendar"]

    observed = {}
    evidence_rules = config.get("filing-evidence")
    inventory = control_root / "discovery" / "file-inventory.csv"
    if evidence_rules and (inventory.is_file() or ub_root.is_dir()):
        paths = (ex.paths_from_inventory(inventory) if inventory.is_file()
                 else ex.walk_paths(ub_root))
        observed = ex.observe(ex.scan_paths(paths, evidence_rules))
        print(f"archive: {len(paths)} path(s), evidence for "
              f"{len(observed)} obligation(s)")
    else:
        print("No filing evidence available — the practice column will say "
              "so on every row rather than being left blank, because a "
              "blank reads as nothing filed (§1.1).")

    rows, excluded = advisor.build_rows(statutory, observed)
    out_dir = control_root / "discovery"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = out_dir / "TAX-ADVISOR-BRIEF.md"
    written.write_text(
        advisor.render(rows, statutory, today, excluded), encoding="utf-8")

    for item in excluded:
        print(f"  not for the advisor: {item}")
    print(f"\n{len(rows)} obligation(s) in the table. Leading with "
          + ", ".join(r.name for r in rows[:len(advisor.LEAD_WITH)]) + ".")
    if not statutory.get("verified_by_advisor"):
        print("\nEvery row is marked as CEO-stated and unverified. The "
              "brief says so, and asks for correction rather than "
              "agreement — agreeing with a plausible row is the failure "
              "mode here.")
    print(f"\nwritten: {written}")
    print("This leaves the company from you, never from Control (§10).")
    return 0


def cmd_gaps(args) -> int:
    """The gap register — execution order step 3.

    Every open item, typed by who can close it, counted per type and
    never totalled. §6 of the order requires legal coverage to stay
    visible at 0%, and an average across types is precisely a way of
    not doing that.
    """
    from . import gaps as gp
    from .db import connect, ensure_schema
    from .loader import load_for_cycle

    control_root = Path(args.control_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    repo = Path(__file__).resolve().parent.parent.parent

    order = repo / "docs" / "decisions" / "EXECUTION-ORDER-18-Aug-2026.md"
    charter = repo / "CLAUDE.md"
    order_text = order.read_text(encoding="utf-8") if order.is_file() else ""
    charter_text = charter.read_text(encoding="utf-8") if charter.is_file() else ""
    if not order_text:
        print(f"execution order not found at {order} — the register would be "
              "missing the seven items the CEO already listed, and a partial "
              "register that does not say so is worse than none (§1.1).")
        return 1

    report = _startup(args)
    conn = connect(report.db_path)
    try:
        ensure_schema(conn)
        loaded = load_for_cycle(report.config, conn, today,
                                logs_dir=control_root / "logs")
        live = loaded.gaps
    finally:
        conn.close()

    documents = sorted((repo / "docs" / "governance").glob("*.md"))
    found = gp.collect(order_text, charter_text, documents, live)
    per_type = gp.counts(found)

    out_dir = control_root / "discovery"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = out_dir / "GAP-REGISTER.md"
    written.write_text(gp.render(found, today), encoding="utf-8")

    print(f"gap register — {len(found)} item(s), counted per type and never "
          "totalled:")
    for kind in gp.TYPES:
        print(f"  {kind:8} {per_type[kind]:3}  — {gp.TYPE_NOTE[kind]}")
    print("\nLEGAL coverage reads 0% and must stay visible at 0% until "
          "counsel is engaged — that is D-52 working, not failing "
          "(execution order §6).")

    for note in gp.reconcile(found, order_text):
        print(f"\nRECONCILIATION: {note}")

    print(f"\nwritten: {written}")
    return 0


def cmd_extract_brief(args) -> int:
    """The extraction brief — execution order step 2.

    Read-only against the filing archive. Reports disagreements first
    and resolves none of them: §14.2 puts statutory deadlines in Tier C,
    raised with evidence for a human decision and never changed by the
    system.
    """
    from . import extraction as ex
    from .config import load_config

    control_root = Path(args.control_root)
    ub_root = Path(args.ub_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    config = load_config(control_root / "config")

    evidence_rules = config.get("filing-evidence")
    if not evidence_rules:
        print("filing-evidence.yaml is missing from config. Without it "
              "nothing identifies a filing, and guessing which documents "
              "are returns is exactly what this brief must not do (§1.1).")
        return 1

    inventory = control_root / "discovery" / "file-inventory.csv"
    if inventory.is_file() and not args.rescan:
        paths = ex.paths_from_inventory(inventory)
        source = f"Stage B inventory ({inventory.name})"
    else:
        if not ub_root.is_dir():
            print(f"UB_ROOT not reachable: {ub_root} — halting rather than "
                  "reporting on a partial view (§13.2).")
            return 1
        print(f"No inventory at {inventory} — walking {ub_root}. "
              "This is the slow path.")
        paths = ex.walk_paths(ub_root)
        source = f"direct walk of {ub_root}"

    found = ex.scan_paths(paths, evidence_rules)
    observed = ex.observe(found)
    statutory = config["statutory-calendar"]
    disagreeing = ex.disagreements(statutory, observed)
    candidates = ex.upgrade_candidates(statutory, observed, disagreeing)

    brief = ex.render_brief(statutory, observed, disagreeing, candidates,
                            source, len(paths), today)
    out_dir = control_root / "discovery"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = out_dir / "EXTRACTION-BRIEF.md"
    written.write_text(brief, encoding="utf-8")

    print(f"{len(paths)} path(s) considered, {len(found)} matched as filing "
          f"evidence across {len(observed)} obligation(s).")
    if disagreeing:
        print(f"\n{len(disagreeing)} DISAGREEMENT(S) — the archive "
              "contradicts a CEO-stated rule:")
        for item in disagreeing:
            print(f"  {item.obligation_id}: stated {item.stated}; "
                  f"observed {item.observed}")
        print("\nNone of these is resolved here. §14.2 puts statutory "
              "deadlines in Tier C — raised for a human decision, never "
              "changed by the system.")
    else:
        silent = ex.silent_obligations(statutory, observed)
        checked = len([r for r in (statutory or {}).get("obligations") or []
                       if ex.STATED_CADENCE_PERIODS.get(
                           str(r.get("cadence") or "").lower())]) - len(silent)
        print(f"\nNo disagreement — but only {checked} obligation(s) could "
              "actually be asked. \"The archive agreed\" and \"the archive "
              "could not be asked\"\nlook identical in an empty section, so "
              "here is which:")
        for note in silent:
            print(f"  - {note}")

    if candidates:
        print(f"\n{len(candidates)} rule(s) corroborated by the filings, "
              "proposed for ceo_stated → document_evidenced:")
        for candidate in candidates:
            print(f"  {candidate['id']}: {candidate['evidence']}")
        print("\nO-03 stays open regardless — the archive shows what the "
              "company did, not what the law requires.")

    print(f"\nwritten: {written}")
    return 0


def cmd_event(args) -> int:
    """Event-driven statutory windows — §2.1, execution order B1 and B4.

    Two class 1 obligations have no cadence: the ETA rejection clearance
    window starts when ETA rejects an invoice, and the social insurance
    headcount declaration starts when someone joins or leaves. There is
    no date to compute until the event exists.

    This command is how the event gets in. It exists as a human-driven
    command rather than a detector because M1 keeps Control on
    `control@` only, and ETA rejections arrive in `accounts@` — so for
    now a person enters them, and every row says so.
    """
    from . import events as ev
    from .config import load_config
    from .db import connect, ensure_schema

    control_root = Path(args.control_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    conn = connect(control_root / "data" / "control.db")
    try:
        # This command does not go through startup, and the event tables
        # postdate every database created before them.
        added = ensure_schema(conn)
        if added:
            print(f"schema: created {', '.join(added)}")
        statutory = load_config(control_root / "config")["statutory-calendar"]

        # §5.2 requires `submitted_by` on every row, and this register is
        # the one place where a human's memory is the only evidence
        # there is. An unattributable row here could not be checked with
        # anyone later.
        if (args.discharge or args.obligation) and not args.by:
            print("--by is required: every row records who entered it "
                  "(§5.2), and for a manually detected event that is the "
                  "only evidence of where the date came from.")
            return 1

        if args.discharge:
            event_id = int(args.discharge)
            if event_id not in {e.row_id for e in ev.open_events(conn)}:
                print(f"No open event {event_id}. Nothing recorded.")
                return 1
            on = date.fromisoformat(args.on) if args.on else today
            ev.discharge_event(conn, event_id, on, args.by,
                               reference=args.reference or None)
            print(f"event {event_id}: discharged on {on:%d-%b-%Y} by "
                  f"{args.by}")
            print("  the event row is unchanged — closure is its own row "
                  "(§5.2)")
            return 0

        if args.obligation:
            if not args.date:
                print("--date is required: the deadline counts from the day "
                      "the event happened, not from today (B4).")
                return 1
            event_date = date.fromisoformat(args.date)
            if event_date > today:
                print(f"Not recorded: {event_date:%d-%b-%Y} is in the future. "
                      "An event that has not happened starts no clock.")
                return 1
            event_id = ev.record_event(
                conn, args.obligation, args.type or "UNSPECIFIED", event_date,
                args.reference or None, "MANUAL", args.by,
                registered_at=today)
            print(f"event {event_id}: {args.obligation} on "
                  f"{event_date:%d-%b-%Y}, entered by {args.by}")
            lag = (today - event_date).days
            if lag:
                print(f"  registered {lag} day(s) after the event — that "
                      "much of the window was already spent before Control "
                      "could start counting (B4)")
            tracked, _ = ev.build_event_items(conn, statutory, today)
            mine = next((t for t in tracked
                         if t.item_id.endswith(f"#{event_id}")), None)
            if mine:
                print(f"  due {mine.due:%d-%b-%Y} "
                      f"(T-{(mine.due - today).days}), owner {mine.owner}")
            else:
                print("  no deadline computed — see the gaps in the next "
                      "report; the clock is running and Control is not "
                      "counting it")
            return 0

        # No arguments: show what is running.
        tracked, gaps = ev.build_event_items(conn, statutory, today)
        rows = ev.open_events(conn)
        if not rows:
            print("No statutory events on record — nothing is being counted.")
        else:
            print(f"{len(rows)} open statutory event(s):\n")
            due_by_id = {t.item_id: t for t in tracked}
            for event in rows:
                item = due_by_id.get(
                    f"{event.obligation_id}#{event.row_id}")
                when = (f"due {item.due:%d-%b-%Y} "
                        f"(T-{(item.due - today).days})" if item
                        else "NO DEADLINE COMPUTED")
                print(f"  [{event.row_id}] {event.obligation_id} — "
                      f"{event.event_type} on {event.event_date:%d-%b-%Y} — "
                      f"{when}")
                if event.reference:
                    print(f"       ref {event.reference}")
                if event.registration_lag_days:
                    print(f"       registered {event.registration_lag_days} "
                          "day(s) late — that much of the window was gone "
                          "before Control saw it")
                print(f"       detection: {event.detection}")
        for line in gaps:
            print(f"\n  {line}")
        print("\nTo record:   python -m control event --obligation "
              "STAT-ETA-REJ --type ETA_REJECTION \\\n"
              "               --date YYYY-MM-DD --reference INV-1234 "
              "--by you@ubcsis.com")
        print("To discharge: python -m control event --discharge <id> "
              "--by you@ubcsis.com")
        return 0
    finally:
        conn.close()


def cmd_golden(args) -> int:
    """§13.1 golden set — issue a batch, apply it, or run the gate.

    Three modes, in the order the charter runs them:

      --issue   write the next batch of 10 for the CEO to judge (D-03:
                Control's own verdict never appears on the sheet)
      --apply   read a filled sheet back in as permanent test cases
      (none)    run the engine against the set and report the gate

    The gate is what stands between here and Phase 2: zero false
    RETURNED_FOR_REVISION or NOT_ACCEPTED verdicts, counted per check
    rather than per document.
    """
    import yaml

    from . import golden_worksheet as gw
    from .goldenset import load_cases, report, run_golden_set

    control_root = Path(args.control_root)
    today = date.fromisoformat(args.today) if args.today else date.today()
    golden_dir = control_root / "tests" / "golden-set"
    pending_dir = golden_dir / "pending"
    # Beside the worksheets it tracks, not among the cases: the case
    # directory is globbed for *.yaml, and a ledger sitting in it would
    # be loaded as a case with no verdict.
    ledger_path = golden_dir / "worksheets" / "batches.yaml"
    batches = gw.load_ledger(ledger_path)

    if args.build:
        # The step nothing performed. `--issue` writes batches and
        # `--apply` reads them back; neither ever put a case into
        # pending/, so the Phase 1 gate reported the golden set as
        # BLOCKED on the CEO's time when what was missing was this.
        from . import golden_build
        from .config import load_config

        ub_root = Path(args.ub_root) if args.ub_root else None
        if not ub_root or not ub_root.is_dir():
            print("--ub-root is required and must exist: the cases are built "
                  "from documents on the drive.")
            return 1

        obligations = (load_config(control_root / "config")
                       .get("obligations") or {}).get("obligations") or []
        documents = []
        for path in ub_root.rglob("*"):
            if path.is_file() and path.suffix.lower() in (
                    ".xlsx", ".xls", ".docx", ".pdf"):
                documents.append(
                    (path, datetime.fromtimestamp(path.stat().st_mtime)))

        owner_folders = {
            "accounts@ubcsis.com": ["8. Finance"],
            "hr@ubcsis.com": ["9. HR Department"],
            "shymaa@ubcsis.com": ["Progress Reports"],
            "a.elsayed@ubcsis.com": ["14. Construction Management Files"],
            "hse@ubcsis.com": ["16. Safety Documents"],
            "info@ubcsis.com": ["3. Purchase Orders", "4. Suppliers POs"],
        }
        buildable = golden_build.build(obligations, documents, owner_folders,
                                       per_obligation=args.per_obligation)
        cases = golden_build.to_cases(buildable, obligations)

        pending_dir.mkdir(parents=True, exist_ok=True)
        written = 0
        for case in cases:
            target = pending_dir / f"{case['case_id']}.yaml"
            if target.exists():
                continue
            target.write_text(
                yaml.safe_dump(case, allow_unicode=True, sort_keys=False),
                encoding="utf-8")
            written += 1

        for line in golden_build.render(buildable, cases, today):
            print(line)
        print(f"\nwritten: {written} pending case(s) to {pending_dir}")
        if written:
            print("Next: python -m control golden --issue   "
                  "(a batch of 10 for the CEO, unanchored — D-03)")
        return 0

    if args.issue:
        pending = gw.load_pending(pending_dir)
        issued = {cid for b in batches for cid in b.case_ids}
        queue = [p for p in pending if str(p.get("case_id")) not in issued]
        if not queue:
            print(f"Nothing pending in {pending_dir}.")
            print("\nPending cases are real historical submissions with their "
                  "governing spec: 30-50 spanning every report type and every "
                  "submitter, with a realistic spread of good and defective "
                  "work (§13.1) — not a curated sample of clean ones. A set "
                  "drawn only from what is easy to parse would certify the "
                  "engine against the work it already handles.")
            print("\nThat needs the mailbox scan and its attachments, so the "
                  "cases are built on the machine holding the archive, not "
                  "here. Each is one YAML file carrying spec + doc and no "
                  "expected verdict — the verdict is what this worksheet is "
                  "for.")
            return 1

        chunk = queue[:gw.BATCH_SIZE]
        number = max((b.number for b in batches), default=0) + 1
        # The subsample accumulates across batches: ten items total, not
        # ten per week (§13.1).
        already_withheld = {cid for b in batches for cid in b.clause_withheld}
        clause_blank = gw.choose_clause_subsample(
            chunk, already=already_withheld)
        path, case_ids = gw.write_batch(
            chunk, golden_dir / "worksheets" / f"batch-{number:02d}.csv",
            clause_blank=clause_blank)

        batches.append(gw.Batch(number=number, case_ids=case_ids, issued=today,
                                path=str(path),
                                clause_withheld=sorted(clause_blank)))
        gw.save_ledger(batches, ledger_path)

        print(f"batch {number}: {len(case_ids)} item(s) -> {path}")
        print(f"  {len(clause_blank)} with the clause withheld, so your own "
              "clause choice can be compared against Control's (§13.1)")
        print(f"  {len(queue) - len(chunk)} still pending after this batch")
        print("\nFill VERDICT and, where not accepted, FAILED_CHECKS. Control's "
              "own verdict is deliberately not on the sheet: judging against it "
              "would produce a test it cannot fail (D-03).")
        print(f"Then: python -m control golden --apply \"{path}\"")
        return 0

    if args.apply:
        worksheet = Path(args.apply)
        if not worksheet.is_file():
            print(f"worksheet not found: {worksheet}")
            return 1
        answers, problems = gw.read_batch(worksheet)
        if problems:
            print("The worksheet has entries Control will not interpret:\n")
            for problem in problems:
                print(f"  {problem}")
            print("\nNothing applied. A guessed verdict here becomes a "
                  "permanent expected answer in the gate that decides whether "
                  "Control may send anything (§1.1).")
            return 1
        if not answers:
            print("No verdicts entered. Nothing applied.")
            return 1

        applied, problems, clause_results = gw.apply_batch(
            answers, pending_dir, golden_dir)
        for problem in problems:
            print(f"  {problem}")
        print(f"applied {len(applied)} verdict(s) to the golden set")

        for batch in batches:
            if batch.path and Path(batch.path).name == worksheet.name:
                if not set(batch.case_ids) - set(applied):
                    batch.returned = today
        gw.save_ledger(batches, ledger_path)

        for line in gw.clause_mapping_report(clause_results):
            print(line)
        print("\nRun the gate:  python -m control golden")
        return 1 if problems else 0

    cases = load_cases(golden_dir)
    if not cases:
        print(f"The golden set is empty ({golden_dir}).")
        print("Nothing has been tested, so nothing is certified — and §16 "
              "gates Phase 2 on this set passing. An empty set is not a pass.")
        print("\nStart with:  python -m control golden --issue")
        for line in gw.ledger_lines(batches, today):
            print(f"  {line}")
        return 1

    result = run_golden_set(cases)
    print(report(result))

    clause_results = []
    for case in cases:
        raw = yaml.safe_load(case.path.read_text(encoding="utf-8")) or {}
        mapping = raw.get("clause_mapping")
        if mapping:
            clause_results.append({
                "case_id": case.case_id, "ceo": mapping.get("ceo", ""),
                "control": mapping.get("control", ""),
                "agrees": gw.clause_matches(mapping.get("ceo", ""),
                                            mapping.get("control", "")),
            })
    print("")
    for line in gw.clause_mapping_report(clause_results):
        print(line)

    for line in gw.ledger_lines(batches, today):
        print(f"\n{line}")

    if len(cases) < 30:
        print(f"\n{len(cases)} cases. §13.1 asks for 30–50 spanning every "
              "report type and submitter — the gate is not yet a test of the "
              "whole engine.")
    return 0 if result.gate_passed else 1


def cmd_manuals(args) -> int:
    """Stage C — find the governing manuals, for CEO confirmation."""
    import yaml

    from .discovery.manuals import (
        CANDIDATE_THRESHOLD, render_manual_inventory, score_candidate,
    )
    from .discovery.stage_c import (
        READABLE_SUFFIXES, SCANNED_SUFFIXES, classify_confidential, extract_text,
    )

    control_root = Path(args.control_root)
    if not args.source:
        print("no --source and no UB_ROOT set. Nothing scanned.")
        return 1
    source = Path(args.source)
    if not source.is_dir():
        print(f"source folder not found: {source}")
        return 1

    clients, folders, projects = [], [], []
    config = control_root / "config" / "confidential.yaml"
    if config.is_file():
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        clients = [c.get("name", "") for c in data.get("confidential_clients", [])]
        folders = list(data.get("confidential_folders") or [])
        projects = list(data.get("confidential_projects") or [])

    print(f"scanning {source} for governing manuals")
    candidates = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in READABLE_SUFFIXES and suffix not in SCANNED_SUFFIXES:
            continue
        if path.resolve().is_relative_to(control_root.resolve()):
            continue
        relative = str(path.relative_to(source))
        confidential, _ = classify_confidential(
            Path(relative), clients, folders, projects)
        # A confidential manual is still scored — on its filename only.
        # D-01 forbids opening it, and D-05 covers contracts, not manuals.
        text = None if (confidential or suffix in SCANNED_SUFFIXES) \
            else extract_text(path)
        candidate = score_candidate(relative, text)
        candidate.confidential = confidential
        if candidate.score >= CANDIDATE_THRESHOLD:
            candidates.append(candidate)

    out = control_root / "discovery" / "MANUAL-INVENTORY.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_manual_inventory(candidates, expected=args.expected),
                   encoding="utf-8")

    high = [c for c in candidates if c.confidence == "HIGH"]
    print(f"\ncandidates:      {len(candidates)}")
    print(f"high confidence: {len(high)} (charter expects {args.expected})")
    for candidate in sorted(high, key=lambda c: -c.score)[:15]:
        print(f"  {candidate.score:>3}  {candidate.path[:70]}")
    if len(high) < args.expected:
        print(f"\nGAP: {args.expected - len(high)} of the {args.expected} "
              "manuals are not accounted for at high confidence.")
        print("They may be named differently, unreadable, or not written. "
              "Which it is changes what C6 can claim (§1.1).")
    print(f"\nwritten: {out}")
    print("Tick the governing manuals in that file; clause extraction runs "
          "only against confirmed ones.")
    return 0


def cmd_backup(args) -> int:
    """Continuity — §5.2, decision D-11."""
    import tempfile

    import yaml

    from .backup import (
        BackupResult, continuity_lines, create_backup, create_key,
        latest_backup, prune, resolve_destination, restore, restore_test,
    )

    control_root = Path(args.control_root)
    config_path = control_root / "config" / "backup.yaml"
    if not config_path.is_file():
        print(f"no backup.yaml at {config_path}. Run 'init' first.")
        return 1
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    today = date.fromisoformat(args.today) if args.today else date.today()

    if args.init_key:
        key = create_key(config)
        print("A new backup encryption key has been created and stored in "
              "the Windows credential store.\n")
        print(f"  {key}\n")
        print("Write it down somewhere off this machine, now. A key that")
        print("exists only on the laptop the backup protects against is not")
        print("a key. Without it the backups cannot be restored by anyone,")
        print("including you.")
        return 0

    destination = resolve_destination(config)
    print(f"destination: {destination or 'NOT CONFIGURED'}")

    if args.restore:
        archive = Path(args.archive) if args.archive else latest_backup(config)
        if archive is None:
            print("no backup to restore.")
            return 1
        target = restore(archive, Path(args.restore), config)
        print(f"restored {archive.name} -> {target}")
        return 0

    if args.test:
        with tempfile.TemporaryDirectory() as tmp:
            outcome = restore_test(config, Path(tmp) / "restored")
        if outcome.get("error"):
            print(f"restore test: {outcome['error']}")
            return 1
        print(f"restore test on {outcome['archive']}")
        print(f"  files restored: {outcome['files']}")
        print(f"  database:       {outcome['db']}")
        print(f"  audit chain:    {outcome['chain']}")
        print(f"\n{'PASS' if outcome['ok'] else 'FAIL'}")
        if outcome["ok"]:
            print("\nRecord this in backup.yaml: restore_test.last_tested = "
                  f"{today.isoformat()}")
        return 0 if outcome["ok"] else 1

    result: BackupResult = create_backup(control_root, config, on_date=today)
    for gap in result.gaps:
        print(f"GAP: {gap}")
    if not result.written:
        return 1
    print(f"wrote {result.path.name}")
    print(f"  files:     {result.files}")
    print(f"  plaintext: {result.plaintext_bytes:,} bytes")
    print(f"  encrypted: {result.encrypted_bytes:,} bytes")
    print(f"  sha256:    {result.sha256[:32]}…")
    removed = prune(config, on_date=today)
    if removed:
        print(f"  pruned:    {len(removed)} past retention")
    for line in continuity_lines(config, on_date=today):
        print(f"\n{line}")
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


def _harden_console() -> None:
    """Stop a console encoding from killing a successful run.

    Windows consoles default to cp1252, which cannot encode Arabic. Most
    of this document estate is Arabic, and several commands print file
    and folder names — so the first Arabic path would raise
    UnicodeEncodeError and take down a scan that had otherwise worked.

    Files were always written UTF-8; only the console was at risk. The
    fallback replaces unencodable characters rather than raising, so a
    name may render imperfectly in the terminal while the run completes
    and the written output stays exact.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _harden_console()
    parser = argparse.ArgumentParser(prog="control")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("startup", cmd_startup), ("discovery", cmd_discovery),
                     ("verify", cmd_verify)):
        p = sub.add_parser(name)
        _common(p)
        p.set_defaults(fn=fn)

    scan = sub.add_parser("outlook-scan",
                          help="historical mailbox scan via Outlook (metadata only)")
    _common(scan)
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
    _common(phase0)
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
    init.add_argument("--adopt-key", action="append", default=[],
                      metavar="FILE:KEY",
                      help="copy one named config key from the template, "
                           "e.g. authority.yaml:interim. Naming it is you "
                           "deciding; it never replaces a key you already have")
    init.add_argument("--accept-template", action="append", default=[],
                      metavar="FILE.yaml",
                      help="resolve this file's conflicts in favour of the "
                           "template, because you have decided the template "
                           "side is current. Repeatable.")
    init.add_argument("--adopt", action="store_true",
                      help="add template list entries your config lacks; "
                           "never removes or changes what is already there")
    init.add_argument("--templates", default="",
                      help="config template directory (default: repo config/)")
    init.set_defaults(fn=cmd_init)

    contracts = sub.add_parser(
        "contracts",
        help="Stage C: extract guarantee, LD, notice and accreditation terms")
    contracts.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    contracts.add_argument("--source", default=os.environ.get("UB_ROOT", ""),
                           help="folder(s) to scan, comma-separated (default: "
                                "UB_ROOT — the whole "
                                "drive, so a guarantee filed somewhere nobody "
                                "remembered is still found)")
    contracts.add_argument("--no-cache", action="store_true",
                           help="re-read every document instead of reusing "
                                "cached per-document outcomes")
    contracts.add_argument("--ocr", action="store_true",
                           help="§5.5: OCR scanned documents (ara+eng). "
                                "Confidential contracts only with "
                                "--confidential-dates (D-14)")
    contracts.add_argument("--ocr-floor", type=float, default=60.0,
                           help="§5.5 confidence floor, 0-100 (default 60). "
                                "Below it a document is UNREADABLE")
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

    classify_scan = sub.add_parser(
        "classify-scan",
        help="§9 category profile over scan output (metadata only, no mailbox access)")
    classify_scan.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    classify_scan.add_argument("--mailbox", default="",
                               help="restrict to these addresses (default: every scan)")
    classify_scan.set_defaults(fn=cmd_classify_scan)

    cycle = sub.add_parser(
        "cycle", help="one sweep: fetch, classify, evaluate, enforce, gate")
    _common(cycle)
    cycle.add_argument("--today", default="", help="ISO date, for testing")
    cycle.add_argument("--allow-send", action="store_true",
                       help="permit the transport to send what the §10 gate "
                            "has already approved for this run mode")
    cycle.set_defaults(fn=cmd_cycle)

    report_cmd = sub.add_parser(
        "report", help="§11 weekly management report (always a draft)")
    _common(report_cmd)
    report_cmd.add_argument("--as-of", default="", help="ISO date, for testing")
    report_cmd.set_defaults(fn=cmd_report)

    disputes = sub.add_parser(
        "disputes", help="§8.4: list disputes awaiting a ruling, or record one")
    disputes.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    disputes.add_argument("--uphold", default="", help="dispute id to uphold")
    disputes.add_argument("--reject", default="", help="dispute id to reject")
    disputes.add_argument("--reason", default="",
                          help="the ruling — kept as the expected answer (§13.1)")
    disputes.add_argument("--by", default="ahmed@ubcsis.com",
                          help="who is ruling; the COO only during registered "
                               "CEO absence (§3.3)")
    disputes.add_argument("--today", default="", help="ISO date, for testing")
    disputes.set_defaults(fn=cmd_disputes)

    phase1 = sub.add_parser(
        "phase1",
        help="everything Phase 1 can do without a human, in one command")
    _common(phase1)
    phase1.add_argument("--today", default="", help="ISO date, for testing")
    phase1.add_argument("--ocr", action="store_true",
                        help="§5.5: OCR scanned documents in Stage C")
    phase1.add_argument("--ocr-floor", type=float, default=60.0)
    phase1.add_argument("--accept-template", action="append", default=[],
                        metavar="FILE.yaml")
    phase1.add_argument("--skip-scan", action="store_true",
                        help="skip the Outlook scan (no Outlook on this machine)")
    phase1.add_argument("--skip-cycle", action="store_true",
                        help="skip the mail cycle (no transport)")
    phase1.set_defaults(fn=cmd_phase1)

    gate_cmd = sub.add_parser(
        "gate",
        help="§16: the Phase 0 and Phase 1 gate conditions, measured")
    _common(gate_cmd)
    gate_cmd.add_argument("--today", default="", help="ISO date, for testing")
    gate_cmd.set_defaults(fn=cmd_gate)

    register_cmd = sub.add_parser(
        "register",
        help="§6: propose the obligation register from Stage D, or approve "
             "it — approval is what ends Phase 0")
    register_cmd.add_argument("--control-root",
                              default=os.environ.get("CONTROL_ROOT"))
    register_cmd.add_argument("--approve", nargs="*", default=None,
                              metavar="ID",
                              help="approve all usable proposals, or only "
                                   "the ids named")
    register_cmd.add_argument("--by", default="",
                              help="who is approving; §6 says the CEO")
    register_cmd.add_argument("--min-occurrences", type=int, default=3)
    register_cmd.add_argument("--min-confidence", default="MEDIUM",
                              choices=["HIGH", "MEDIUM", "LOW"])
    register_cmd.add_argument("--today", default="", help="ISO date, for testing")
    register_cmd.set_defaults(fn=cmd_register_obligations)

    advisor_cmd = sub.add_parser(
        "advisor-brief",
        help="execution order step 5: the completed statutory table, for "
             "the tax advisor to correct")
    advisor_cmd.add_argument("--control-root",
                             default=os.environ.get("CONTROL_ROOT"))
    advisor_cmd.add_argument("--ub-root", default=os.environ.get("UB_ROOT"))
    advisor_cmd.add_argument("--today", default="", help="ISO date, for testing")
    advisor_cmd.set_defaults(fn=cmd_advisor_brief)

    gaps_cmd = sub.add_parser(
        "gaps",
        help="execution order step 3: every open item, typed by who can "
             "close it")
    _common(gaps_cmd)
    gaps_cmd.add_argument("--today", default="", help="ISO date, for testing")
    gaps_cmd.set_defaults(fn=cmd_gaps)

    extract = sub.add_parser(
        "extract-brief",
        help="execution order step 2: what the filing archive says about "
             "the CEO-stated statutory rules")
    extract.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    extract.add_argument("--ub-root", default=os.environ.get("UB_ROOT"))
    extract.add_argument("--rescan", action="store_true",
                         help="walk UB_ROOT instead of reusing the Stage B "
                              "inventory")
    extract.add_argument("--today", default="", help="ISO date, for testing")
    extract.set_defaults(fn=cmd_extract_brief)

    event = sub.add_parser(
        "event",
        help="event-driven class 1 windows: record an event, discharge one, "
             "or list what is running (B1, B4)")
    event.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    event.add_argument("--obligation", default="",
                       help="e.g. STAT-ETA-REJ, STAT-SI-HEADCOUNT")
    event.add_argument("--type", default="",
                       help="e.g. ETA_REJECTION, JOINER, LEAVER")
    event.add_argument("--date", default="",
                       help="ISO date the event HAPPENED — the deadline "
                            "counts from this, not from today (B4)")
    event.add_argument("--reference", default="",
                       help="invoice number, employee reference")
    event.add_argument("--discharge", default="",
                       help="event id to close")
    event.add_argument("--on", default="",
                       help="ISO date the obligation was discharged")
    event.add_argument("--by", default="", help="who is entering this")
    event.add_argument("--today", default="", help="ISO date, for testing")
    event.set_defaults(fn=cmd_event)

    golden = sub.add_parser(
        "golden",
        help="§13.1 golden set: issue a batch, apply it, or run the gate")
    golden.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    golden.add_argument("--build", action="store_true",
                        help="build pending cases from documents on the drive "
                             "(needs --ub-root)")
    golden.add_argument("--ub-root", default=os.environ.get("UB_ROOT", ""))
    golden.add_argument("--per-obligation", type=int, default=12)
    golden.add_argument("--issue", action="store_true",
                        help="write the next batch of 10 for the CEO to judge")
    golden.add_argument("--apply", default="",
                        help="path to a filled-in worksheet CSV")
    golden.add_argument("--today", default="", help="ISO date, for testing")
    golden.set_defaults(fn=cmd_golden)

    terms = sub.add_parser(
        "terms",
        help="manual entry for documents no machine could read (§5.5)")
    terms.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    terms.add_argument("--apply", default="",
                       help="path to the filled-in worksheet CSV")
    terms.add_argument("--entered-by", default="ahmed@ubcsis.com")
    terms.add_argument("--today", default="", help="ISO date, for testing")
    terms.set_defaults(fn=cmd_terms)

    diagnose = sub.add_parser(
        "diagnose-dates",
        help="why Stage C terms carry no date — counts what the documents "
             "actually write, from cached text (no re-read, no OCR)")
    diagnose.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    diagnose.set_defaults(fn=cmd_diagnose_dates)

    status = sub.add_parser(
        "status",
        help="one page of what the runs actually found — reads what is on "
             "disk, scans nothing")
    status.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    status.add_argument("--today", default="", help="ISO date, for testing")
    status.set_defaults(fn=cmd_status)

    floor = sub.add_parser(
        "ocr-floor",
        help="§5.5: what each OCR confidence floor would admit, from this "
             "estate's own readings (reports only — §14.4)")
    floor.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    floor.add_argument("--ocr-floor", type=float, default=60.0,
                       help="the floor currently in force, for comparison")
    floor.set_defaults(fn=cmd_ocr_floor)

    authority = sub.add_parser(
        "authority",
        help="O-02: read candidate delegated limits out of the delegation "
             "documents (proposes only — §14.2 Tier C)")
    authority.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    authority.add_argument("--source", default="",
                           help="folder(s) holding delegation documents, "
                                "comma-separated")
    authority.add_argument("--today", default="", help="ISO date, for testing")
    authority.set_defaults(fn=cmd_authority)

    manuals = sub.add_parser(
        "manuals",
        help="Stage C: find the governing manuals, for CEO confirmation")
    manuals.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    manuals.add_argument("--source", default=os.environ.get("UB_ROOT", ""),
                         help="folder to scan (default: UB_ROOT)")
    manuals.add_argument("--expected", type=int, default=12,
                         help="how many manuals the charter names (§6)")
    manuals.set_defaults(fn=cmd_manuals)

    backup = sub.add_parser(
        "backup", help="§5.2 continuity: encrypted backup of CONTROL_ROOT")
    backup.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    backup.add_argument("--init-key", action="store_true",
                        help="create and store the encryption key (once)")
    backup.add_argument("--test", action="store_true",
                        help="§13.3 restore test: unpack the latest backup "
                             "and verify the database and audit chain")
    backup.add_argument("--restore", default="",
                        help="restore into this directory")
    backup.add_argument("--archive", default="",
                        help="specific archive to restore (default: latest)")
    backup.add_argument("--today", default="", help="ISO date, for testing")
    backup.set_defaults(fn=cmd_backup)

    doctor = sub.add_parser("doctor",
                            help="check this machine can run Control")
    doctor.add_argument("--control-root", default=os.environ.get("CONTROL_ROOT"))
    doctor.set_defaults(fn=cmd_doctor)

    # Arabic filenames and citations are normal here (§4), and the Windows
    # console defaults to cp1252, which cannot encode them: printing a
    # citation would raise UnicodeEncodeError and take down a scan that
    # had otherwise succeeded. Replace unencodable characters in console
    # output only — files are written UTF-8 regardless.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = parser.parse_args(argv)
    # outlook-scan and phase0 belong here now: they run the §5.6 startup
    # before touching the mailbox, and startup verifies UB_ROOT.
    if args.command in ("startup", "discovery", "cycle", "report",
                        "outlook-scan", "phase0") and (
            not args.control_root or not args.ub_root):
        parser.error("--control-root and --ub-root are required "
                     "(or set CONTROL_ROOT / UB_ROOT)")
    if (args.command in ("verify", "analyse", "init", "contracts", "registers",
                         "classify", "classify-scan", "backup", "manuals",
                         "terms", "golden", "disputes", "diagnose-dates", "authority", "ocr-floor", "status")
            and not args.control_root):
        parser.error("--control-root is required (or set CONTROL_ROOT)")
    try:
        return args.fn(args)
    except HaltError as e:
        print(f"HALT: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
