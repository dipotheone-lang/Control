"""CONTROL_ROOT bootstrap — charter §5.3.

Creates the operational tree on a machine from the repository's config
templates. The repository holds the code and the blank configuration;
CONTROL_ROOT holds the live configuration, the database, the logs and
the outbox — none of which are in git, because they carry mail content
and personal data (§12.1, §12.2).

Existing configuration is NEVER overwritten. A config file on disk may
carry decisions someone made; replacing it with a template would
silently discard them.
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import HaltError

# §5.3 tree.
DIRECTORIES = (
    "config",
    "knowledge/manuals", "knowledge/forms", "knowledge/forms-archive",
    "knowledge/policies", "knowledge/contracts", "knowledge/glossary",
    "discovery",
    "data/exports", "data/submissions", "data/quarantine", "data/backup",
    "learning/proposals", "learning/applied", "learning/rolled-back",
    "learning/baselines",
    "outbox/pending-approval", "outbox/sent",
    "reports/management", "reports/learning",
    "tests/golden-set",
    "logs",
)

CONFIG_FILES = (
    "people.yaml", "obligations.yaml", "authority.yaml", "sla.yaml",
    "escalation.yaml", "distribution.yaml", "absence.yaml",
    "statutory-calendar.yaml", "materiality.yaml", "learning-policy.yaml",
    "confidential.yaml", "mailbox-scope.yaml",
)


@dataclass
class BootstrapResult:
    control_root: Path
    created_dirs: list = field(default_factory=list)
    copied_config: list = field(default_factory=list)
    kept_config: list = field(default_factory=list)
    missing_templates: list = field(default_factory=list)
    db_created: bool = False


def bootstrap(control_root: Path, template_config: Path) -> BootstrapResult:
    control_root = Path(control_root)
    template_config = Path(template_config)
    if not template_config.is_dir():
        raise HaltError(f"config templates not found at {template_config}")

    result = BootstrapResult(control_root=control_root)

    for relative in DIRECTORIES:
        path = control_root / relative
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            result.created_dirs.append(relative)

    for name in CONFIG_FILES:
        source = template_config / name
        target = control_root / "config" / name
        if not source.is_file():
            result.missing_templates.append(name)
            continue
        if target.exists():
            # Never overwrite: this file may carry real decisions.
            result.kept_config.append(name)
            continue
        shutil.copy2(source, target)
        result.copied_config.append(name)

    db_path = control_root / "data" / "control.db"
    if not db_path.exists():
        from .db import init_db
        init_db(db_path).close()
        result.db_created = True

    return result


def render_result(result: BootstrapResult) -> str:
    lines = [f"CONTROL_ROOT: {result.control_root}", ""]
    lines.append(f"directories created: {len(result.created_dirs)}")
    if result.copied_config:
        lines.append(f"config installed: {len(result.copied_config)} files")
    if result.kept_config:
        lines.append(f"config left untouched (already present): "
                     f"{len(result.kept_config)} files")
    if result.missing_templates:
        lines.append("MISSING TEMPLATES: " + ", ".join(result.missing_templates))
    lines.append(f"database: {'created' if result.db_created else 'already present'}")
    lines += [
        "",
        "Operational data lives here and is deliberately not in git:",
        "  control.db, logs/, outbox/, data/submissions, data/quarantine",
        "It carries mail content and personal data (§12.1, §12.2).",
        "Back it up per §5.2 — the whole of CONTROL_ROOT, encrypted, daily.",
    ]
    return "\n".join(lines)
