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
    # Optional in `config.py` — their absence is fail-safe rather than a
    # §5.6 halt — but a machine that never receives them runs the
    # restrictive default forever with nothing saying why.
    "hse.yaml", "filing-evidence.yaml",
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
    # Statutory rows. Without this the twelve class 1 obligations the
    # CEO stated on 18-Aug-2026 were invisible to drift on any machine
    # set up before them: the file existed, so it was "kept", and the
    # rows inside it were never compared.
    "obligations": "id",
}


def _entry_key(entry, field_name: str | None) -> str:
    if field_name and isinstance(entry, dict):
        return str(entry.get(field_name) or entry)
    return str(entry)


# A value that records no decision. Replacing one of these is not
# overwriting a decision — it is filling a blank that was waiting for
# the decision that has now arrived.
_PLACEHOLDER_MARKERS = ("UNVERIFIED", "TO BE CONFIRMED", "TBC", "PENDING",
                        "NOT PROVIDED", "TO BE SET")


# Fields that only decide how a row PRINTS. Identity is the `id`; a
# `name` is a label. Reporting "Payroll tax" against "Payroll tax —
# return and remittance" as two decisions disagreeing is technically
# true and practically noise, and noise is what turns an adoption step
# into homework nobody does. A wrong label is a cosmetic defect; a
# wrong `rule` is a missed filing, and only the second is protected.
_DISPLAY_FIELDS = {"name"}


def _is_placeholder(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        upper = stripped.upper()
        return any(marker in upper for marker in _PLACEHOLDER_MARKERS)
    return False


@dataclass(frozen=True)
class Difference:
    """One way this machine's config is behind the templates.

    `adoptable` decides whether `adopt_drift` may close it, and the
    three kinds are three different risks:

    **Additive** — a key, a list entry or a field the local copy simply
    does not have. Adding it cannot discard anything, because there is
    nothing there to discard.

    **Placeholder** — the local value records no decision:
    `UNVERIFIED — CONFIRM WITH ADVISOR`, an empty string, a null.
    Replacing it cannot revert a decision, because a placeholder is the
    absence of one. This is the case that matters in practice: without
    it, a machine adopts every field around a rule and the rule itself
    still says UNVERIFIED, so nothing alerts and the adoption was
    theatre.

    **Conflict** — a real local value against a real template value.
    Two decisions disagreeing. Never adopted; a human decides which is
    current, and Control saying which would be Control deciding.
    """

    file: str
    kind: str                 # key | entry | field | placeholder | conflict
    text: str
    adoptable: bool


def differences(control_root: Path, template_config: Path) -> list[Difference]:
    """Every way the live config is behind the templates, typed.

    Deliberately one-directional. A local file holding MORE than the
    template is the normal case — that is where decisions live — and is
    never reported. Only what the template gained is.
    """
    import yaml

    control_root = Path(control_root)
    template_config = Path(template_config)
    out: list[Difference] = []

    for name in CONFIG_FILES:
        source, target = template_config / name, control_root / "config" / name
        if not source.is_file() or not target.is_file():
            continue
        try:
            template = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
            live = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        except Exception as e:
            out.append(Difference(name, "unreadable",
                                  f"{name}: could not be compared "
                                  f"({str(e)[:60]})", False))
            continue
        if not isinstance(template, dict) or not isinstance(live, dict):
            continue

        for key, value in template.items():
            if key not in live:
                out.append(Difference(
                    name, "key",
                    f"{name}: key {key!r} is in the template and not in "
                    "your copy", True))
                continue

            if key in _NAMED_LISTS and isinstance(value, list) \
                    and isinstance(live.get(key), list):
                out += _list_differences(name, key, value, live[key])
                continue

            if value != live[key] and _is_placeholder(live[key]):
                out.append(Difference(
                    name, "placeholder",
                    f"{name}: {key} is {live[key]!r} locally and "
                    f"{value!r} in the template", True))
            elif value != live[key] and not isinstance(value, (list, dict)):
                out.append(Difference(
                    name, "conflict",
                    f"{name}: {key} is {live[key]!r} locally and "
                    f"{value!r} in the template — two decisions, and "
                    "which is current is yours to say", False))
    return out


def _list_differences(name: str, key: str, template_list: list,
                      live_list: list) -> list[Difference]:
    field_name = _NAMED_LISTS[key]
    out: list[Difference] = []

    have = {_entry_key(e, field_name) for e in live_list}
    missing = [_entry_key(e, field_name) for e in template_list
               if _entry_key(e, field_name) not in have]
    if missing:
        out.append(Difference(
            name, "entry",
            f"{name}: {key} is missing {len(missing)} entry(ies) the "
            f"template has — {', '.join(sorted(missing))}", True))

    by_key = {_entry_key(e, field_name): e for e in live_list
              if isinstance(e, dict)}
    for entry in template_list:
        if not isinstance(entry, dict):
            continue
        local = by_key.get(_entry_key(entry, field_name))
        if local is None:
            continue
        label = _entry_key(entry, field_name)
        new_fields = sorted(f for f in entry if f not in local)
        if new_fields:
            out.append(Difference(
                name, "field",
                f"{name}: {key} entry {label!r} gained "
                + ", ".join(new_fields) + " in the template", True))
        for field_key, value in entry.items():
            if field_key not in local or value == local[field_key]:
                continue
            if field_key in _DISPLAY_FIELDS:
                out.append(Difference(
                    name, "field",
                    f"{name}: {key} entry {label!r} is named "
                    f"{local[field_key]!r} locally and {value!r} in the "
                    "template — a label, not a decision", True))
            elif _is_placeholder(local[field_key]):
                out.append(Difference(
                    name, "placeholder",
                    f"{name}: {key} entry {label!r} has {field_key} "
                    f"{local[field_key]!r} locally, waiting for the "
                    f"{value!r} the template now carries", True))
            else:
                out.append(Difference(
                    name, "conflict",
                    f"{name}: {key} entry {label!r} has {field_key} "
                    f"{local[field_key]!r} locally and {value!r} in the "
                    "template — two decisions, and which is current is "
                    "yours to say", False))
    return out


def config_drift(control_root: Path, template_config: Path) -> list[str]:
    """The differences as lines, for reporting. See `differences`."""
    return [d.text for d in differences(control_root, template_config)]


def render_drift(drift: list[str]) -> list[str]:
    if not drift:
        return ["config matches the templates — no decisions left behind."]
    lines = [
        f"CONFIG BEHIND THE TEMPLATES — {len(drift)} difference(s).",
        "These are things the templates gained that your copy has not:",
        "",
    ]
    lines += [f"  - {item}" for item in drift]
    lines += [
        "",
        "A confidentiality list missing a client gives that client less "
        "protection than was decided (§12.1.1).",
    ]
    return lines


def _backup(target: Path) -> Path:
    """Keep the file as it was, before changing it.

    `yaml.safe_dump` does not preserve comments, so an adoption rewrites
    a file that may carry a paragraph explaining why a value is what it
    is. Losing that quietly would be its own version of the failure
    this module exists to prevent.
    """
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = target.parent / ".superseded"
    folder.mkdir(exist_ok=True)
    kept = folder / f"{target.stem}.{stamp}{target.suffix}"
    shutil.copy2(target, kept)
    return kept


def adopt_drift(control_root: Path, template_config: Path,
                only: str = "") -> list[str]:
    """Close every difference that cannot discard a decision.

    Detection alone leaves the work as hand-editing YAML on a machine
    where that is awkward enough not to happen — which is the same
    friction that let the decision go missing in the first place. So
    this closes what is safe to close, and only that.

    Three things are adopted, and none of them can lose a decision:

    - a key, entry or field the local copy does not have. Adding it
      discards nothing, because nothing is there.
    - a local value that records no decision — `UNVERIFIED`, empty,
      null — where the template now carries a real one. A placeholder
      is the absence of a decision, so replacing it reverts nothing.
      **This is the case that makes the command worth running:** adopt
      every field around a statutory rule and leave the rule itself
      saying UNVERIFIED, and nothing alerts.

    A real local value against a real template value is NOT adopted.
    That is two decisions disagreeing, and Control saying which is
    current would be Control deciding.

    The file is copied to `config/.superseded/` before it is rewritten,
    because `safe_dump` does not keep comments.
    """
    import yaml

    control_root = Path(control_root)
    template_config = Path(template_config)
    applied: list[str] = []

    pending = [d for d in differences(control_root, template_config)
               if d.adoptable and (not only or d.file == only)]
    by_file: dict[str, list[Difference]] = {}
    for item in pending:
        by_file.setdefault(item.file, []).append(item)

    for name, items in by_file.items():
        source = template_config / name
        target = control_root / "config" / name
        template = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        live = yaml.safe_load(target.read_text(encoding="utf-8")) or {}

        for key, value in template.items():
            if key not in live:
                live[key] = value
                applied.append(f"{name}: key {key!r} added")
                continue
            if key in _NAMED_LISTS and isinstance(value, list) \
                    and isinstance(live.get(key), list):
                applied += _adopt_list(name, key, value, live[key])
                continue
            if value != live[key] and _is_placeholder(live[key]):
                applied.append(
                    f"{name}: {key} {live[key]!r} -> {value!r}")
                live[key] = value

        kept = _backup(target)
        target.write_text(
            yaml.safe_dump(live, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        applied.append(f"{name}: previous version kept at "
                       f"{kept.parent.name}/{kept.name}")
    return applied


def _adopt_list(name: str, key: str, template_list: list,
                live_list: list) -> list[str]:
    field_name = _NAMED_LISTS[key]
    applied: list[str] = []

    have = {_entry_key(e, field_name) for e in live_list}
    by_key = {_entry_key(e, field_name): e for e in live_list
              if isinstance(e, dict)}

    for entry in template_list:
        label = _entry_key(entry, field_name)
        if label not in have:
            live_list.append(entry)
            applied.append(f"{name}: {key} += {label}")
            continue
        local = by_key.get(label)
        if local is None:
            continue
        for field_key, value in entry.items():
            if field_key not in local:
                local[field_key] = value
                applied.append(f"{name}: {key} {label} += {field_key}")
            elif value != local[field_key] and (
                    field_key in _DISPLAY_FIELDS
                    or _is_placeholder(local[field_key])):
                applied.append(
                    f"{name}: {key} {label} {field_key} "
                    f"{local[field_key]!r} -> {value!r}")
                local[field_key] = value
    return applied


def adopt_key(control_root: Path, template_config: Path, spec: str) -> str:
    """Copy ONE named config key across, because a human named it.

    `adopt_drift` deliberately refuses to add whole keys: an absent key
    may be absent on purpose, and filling it silently would be the
    system deciding something that belongs to a human.

    Naming the key IS the human deciding. What this removes is only the
    friction of hand-editing YAML on a machine where that is awkward
    enough to not happen — which is the same friction that let the
    decision go missing in the first place.

    `spec` is "file.yaml:key". Refuses to overwrite a key that is
    already present: this adds what is missing, it never replaces what
    is there.
    """
    import yaml

    if ":" not in spec:
        raise HaltError(
            f"--adopt-key wants file.yaml:key, not {spec!r} "
            "(for example: authority.yaml:interim)")
    name, _, key = spec.partition(":")
    name, key = name.strip(), key.strip()

    if name not in CONFIG_FILES:
        raise HaltError(f"{name} is not one of the config files "
                        f"({', '.join(CONFIG_FILES)})")

    source = Path(template_config) / name
    target = Path(control_root) / "config" / name
    if not source.is_file():
        raise HaltError(f"no template for {name}")
    if not target.is_file():
        raise HaltError(f"{name} is not in this CONTROL_ROOT — run init first")

    template = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    live = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if key not in template:
        raise HaltError(f"the template for {name} has no key {key!r}")
    if key in live:
        raise HaltError(
            f"{name} already has {key!r}. This adds what is missing; it "
            "never replaces what is there — edit the file directly if you "
            "mean to change it.")

    live[key] = template[key]
    target.write_text(
        yaml.safe_dump(live, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    return f"{name}: {key} added from the template"
