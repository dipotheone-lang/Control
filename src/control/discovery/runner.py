"""Discovery runner — orchestrates Phase 0 stages under §6 discipline.

Requires a successful §5.6 startup in DISCOVERY state before touching
anything. Writes only inside CONTROL_ROOT/discovery/; the walked roots
are treated as read-only. Every limitation the stages report is written
to DISCOVERY-LIMITATIONS.md — a gap is a finding, not an omission (§1.1).
"""

from datetime import date
from pathlib import Path

from .. import HaltError
from ..startup import StartupReport
from .stage_a import run_stage_a
from .stage_b import run_stage_b


def run_discovery(
    report: StartupReport,
    ub_root: Path,
    control_root: Path,
    extra_mail_roots: list[Path] | None = None,
    today: date | None = None,
) -> dict:
    if report.state.run_mode != "DISCOVERY":
        raise HaltError(
            f"discovery requires RUN_MODE=DISCOVERY; startup state is {report.state.run_mode}"
        )
    ub_root, control_root = Path(ub_root), Path(control_root)
    out_dir = control_root / "discovery"
    out_dir.mkdir(parents=True, exist_ok=True)

    mail_roots = [ub_root, *(extra_mail_roots or [])]
    a = run_stage_a(mail_roots, out_dir)
    report.audit.append("discovery.stage_a", a)

    # CONTROL_ROOT is system output, not company records — excluded.
    b = run_stage_b(ub_root, out_dir, exclude=[control_root], today=today)
    report.audit.append(
        "discovery.stage_b",
        {k: (len(v) if isinstance(v, list) else v) for k, v in b.items()},
    )

    _write_limitations(out_dir, a, b)
    return {"stage_a": a, "stage_b": b}


def _write_limitations(out_dir: Path, a: dict, b: dict) -> None:
    lines = [
        "# DISCOVERY-LIMITATIONS",
        "",
        "Every unreadable archive, unresolved ambiguity, and assumption made",
        "(charter §6 Stage J item 9). A visible gap is a finding; a filled gap",
        "is a fabrication (§1.1).",
        "",
        "## Mail archives not parsed",
        "",
    ]
    if a["limitations"]:
        lines += [f"- {item}" for item in a["limitations"]]
    else:
        lines.append("- None — every archive found was parsed.")
    lines += ["", "## Competing revisions (AMBIGUOUS — CEO DECISION)", ""]
    if b["revision_conflicts"]:
        lines += ["- " + " · ".join(group) for group in b["revision_conflicts"]]
    else:
        lines.append("- None detected.")
    lines += ["", "## Dormant folders (no file modified in 180+ days)", ""]
    if b["dormant_folders"]:
        lines += [f"- {folder}" for folder in b["dormant_folders"]]
    else:
        lines.append("- None detected.")
    lines.append("")
    (out_dir / "DISCOVERY-LIMITATIONS.md").write_text("\n".join(lines), encoding="utf-8")
