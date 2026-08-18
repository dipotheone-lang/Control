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
from datetime import date
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
            print(f"{'':32}owner: {deadline.item.owner}")

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
    if missing:
        for s in missing:
            print(f"source folder not found: {s}")
        return 1

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
    if args.ocr:
        from .ocr import DEFAULT_CONFIDENCE_FLOOR, available, ocr_document

        usable, reason = available()
        if not usable:
            print(f"OCR requested but unusable: {reason}")
            print("Refusing to scan with a half-configured engine — scanned "
                  "documents would be silently misread rather than recorded "
                  "as gaps (§1.1, §5.5).")
            return 1
        floor = args.ocr_floor
        print(f"OCR ACTIVE: {reason}")
        print(f"  confidence floor {floor} — below it a document is UNREADABLE, "
              "not evaluated, not posted (§5.5)")
        print("  OCR is NOT applied to confidential documents: "
              "confidential.yaml lists OCR")
        print("  under metadata_only_mode.prohibited, and D-05 as recorded "
              "covers dates, not OCR.")
        print("  Extending it requires a CEO decision, not a flag.")

        def ocr(path, _floor=floor):
            return ocr_document(path, floor=_floor)

    from .discovery.stage_c import StageCResult

    result = StageCResult()
    for source in sources:
        print(f"  {source}")
        part = run_stage_c(source, clients, folders, exclude=[control_root],
                           permit_confidential_dates=args.confidential_dates,
                           confidential_projects=projects, ocr=ocr,
                           cache_dir=cache_dir)

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
        print(f"    {len(part.documents)} documents, {len(part.terms)} terms, "
              f"{len(part.blocked)} confidential, {len(part.unreadable)} unreadable")

    out = control_root / "discovery" / "COMMERCIAL-EXPOSURE.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_commercial_exposure(result), encoding="utf-8")

    print(f"\ndocuments seen:      {len(result.documents)}")
    print(f"terms extracted:     {len(result.terms)}")
    print(f"confidential, unread: {len(result.blocked)}  (D-01)")
    if result.d05_extracted:
        print(f"confidential, dates only: {len(result.d05_extracted)}  (D-05)")
    print(f"unreadable/scanned:   {len(result.unreadable)}  (OCR needed)")
    if result.from_cache:
        print(f"reused from cache:    {result.from_cache}")
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
    import shutil

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
        if config_count < 15:
            ok = False
            print("    run: python -m control init --control-root <path>")
    else:
        print("\nNo CONTROL_ROOT given (--control-root or $CONTROL_ROOT)")
        ok = False

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
        print("  NOTE: the engine is present but Stage C does not call it yet; "
              "scanned files")
        print("        are still recorded as gaps. Confidential documents must "
              "never be")
        print("        OCR'd outside D-05 (§12.1.2).")

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
        loaded = load_for_cycle(report.config, conn, today)
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
    contracts.add_argument("--source", default=os.environ.get("UB_ROOT", ""),
                           help="folder(s) to scan, comma-separated (default: "
                                "UB_ROOT — the whole "
                                "drive, so a guarantee filed somewhere nobody "
                                "remembered is still found)")
    contracts.add_argument("--no-cache", action="store_true",
                           help="re-read every document instead of reusing "
                                "cached per-document outcomes")
    contracts.add_argument("--ocr", action="store_true",
                           help="§5.5: OCR scanned documents (ara+eng). Never "
                                "applied to confidential documents")
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
    if args.command in ("startup", "discovery", "cycle") and (
            not args.control_root or not args.ub_root):
        parser.error("--control-root and --ub-root are required "
                     "(or set CONTROL_ROOT / UB_ROOT)")
    if (args.command in ("verify", "outlook-scan", "analyse", "phase0", "init",
                         "contracts", "registers", "classify", "classify-scan",
                         "backup", "manuals")
            and not args.control_root):
        parser.error("--control-root is required (or set CONTROL_ROOT)")
    try:
        return args.fn(args)
    except HaltError as e:
        print(f"HALT: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
