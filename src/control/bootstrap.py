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
    "confidential.yaml", "mailbox-scope.yaml", "transport.yaml",
    "backup.yaml", "continuity.yaml",
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


# ---- config drift -----------------------------------------------------

# Named-list keys whose entries are governance content: a client added
# by CEO decision, a mailbox brought into scope, a prohibition. An entry
# present in the template and absent locally means a decision has not
# reached this machine.
_NAMED_LISTS = {
    "confidential_clients": "name",
    "confidential_projects": "name",
    "people": "email",
    "vacancies": "email",
    "special_addresses": "address",
    "mailboxes": None,          # bare strings
    "preconditions": "id",
}


def _entry_key(entry, field_name: str | None) -> str:
    if field_name and isinstance(entry, dict):
        return str(entry.get(field_name) or entry)
    return str(entry)


def config_drift(control_root: Path, template_config: Path) -> list[str]:
    """What the template has that this machine's config does not.

    Config is never overwritten, and that is right — a live file carries
    decisions someone made, and a template would discard them. But
    silence about the difference has its own failure: a machine set up
    before a decision runs on the configuration from before it, forever,
    with nothing saying so. That is how five clients added by CEO
    decision can end up with less protection than was decided.

    Deliberately one-directional. A local file holding MORE than the
    template is the normal case — that is where decisions live — and is
    never reported. Only what the template gained is.
    """
    import yaml

    control_root = Path(control_root)
    template_config = Path(template_config)
    drift: list[str] = []

    for name in CONFIG_FILES:
        source, target = template_config / name, control_root / "config" / name
        if not source.is_file() or not target.is_file():
            continue
        try:
            template = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
            live = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        except Exception as e:
            drift.append(f"{name}: could not be compared ({str(e)[:60]})")
            continue
        if not isinstance(template, dict) or not isinstance(live, dict):
            continue

        for key in template:
            if key not in live:
                drift.append(f"{name}: key {key!r} is in the template and not "
                             "in your copy")
                continue
            if key in _NAMED_LISTS and isinstance(template[key], list) \
                    and isinstance(live.get(key), list):
                field_name = _NAMED_LISTS[key]
                have = {_entry_key(e, field_name) for e in live[key]}
                missing = [_entry_key(e, field_name) for e in template[key]
                           if _entry_key(e, field_name) not in have]
                if missing:
                    drift.append(
                        f"{name}: {key} is missing {len(missing)} entry(ies) "
                        f"the template has — {', '.join(sorted(missing))}")
    return drift


def render_drift(drift: list[str]) -> list[str]:
    if not drift:
        return ["config matches the templates — no decisions left behind."]
    lines = [
        f"CONFIG BEHIND THE TEMPLATES — {len(drift)} difference(s).",
        "Your files are never overwritten, because they carry decisions.",
        "These are things the templates gained that your copy has not:",
        "",
    ]
    lines += [f"  - {item}" for item in drift]
    lines += [
        "",
        "Copy across what applies. A confidentiality list missing a client "
        "gives that client less protection than was decided (§12.1.1).",
    ]
    return lines


def adopt_drift(control_root: Path, template_config: Path,
                only: str = "") -> list[str]:
    """Add template entries the live config lacks. Never removes.

    Detection alone leaves the work as hand-editing YAML, which is the
    friction that let the decision go missing in the first place. So the
    additive half is offered as a step — but only the additive half.

    Strictly one-directional: entries the template has and the live file
    does not are appended; nothing local is changed, reordered or
    removed, because that is where decisions live. Whole new config
    KEYS are not touched either — a key absent locally may be absent
    deliberately, and adding it silently would be the system deciding
    something for a human. Those stay reported by `config_drift`.
    """
    import yaml

    control_root = Path(control_root)
    template_config = Path(template_config)
    added: list[str] = []

    for name in CONFIG_FILES:
        if only and name != only:
            continue
        source, target = template_config / name, control_root / "config" / name
        if not source.is_file() or not target.is_file():
            continue
        template = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        live = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if not isinstance(template, dict) or not isinstance(live, dict):
            continue

        changed = False
        for key, field_name in _NAMED_LISTS.items():
            if not isinstance(template.get(key), list) \
                    or not isinstance(live.get(key), list):
                continue
            have = {_entry_key(e, field_name) for e in live[key]}
            for entry in template[key]:
                if _entry_key(entry, field_name) not in have:
                    live[key].append(entry)
                    added.append(f"{name}: {key} += "
                                 f"{_entry_key(entry, field_name)}")
                    changed = True

        if changed:
            target.write_text(
                yaml.safe_dump(live, allow_unicode=True, sort_keys=False),
                encoding="utf-8")
    return added
