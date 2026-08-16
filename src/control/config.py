"""Configuration loading — charter §5.6 step 1.

Configuration overrides assumptions. A missing or unparseable required
file is a halt, not a default: the engine never guesses config into
existence (§1.1, §5.6).
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import HaltError

REQUIRED_FILES = (
    "people.yaml",
    "obligations.yaml",
    "authority.yaml",
    "sla.yaml",
    "escalation.yaml",
    "distribution.yaml",
    "absence.yaml",
    "statutory-calendar.yaml",
    "materiality.yaml",
    "learning-policy.yaml",
    "confidential.yaml",
    # What Control may read is not an optional file (§3.1a, D-07).
    "mailbox-scope.yaml",
    # Nor is how it reaches the mailbox (§5.1, D-08).
    "transport.yaml",
    # Nor whether the record survives the machine (§5.2, D-11).
    "backup.yaml",
    # Nor the continuity CC exception (§3.1, D-04/D-09).
    "continuity.yaml",
)


@dataclass
class Config:
    root: Path
    data: dict = field(default_factory=dict)

    def __getitem__(self, name: str) -> dict:
        return self.data[name]


def load_config(config_dir: Path) -> Config:
    config_dir = Path(config_dir)
    if not config_dir.is_dir():
        raise HaltError(f"config directory not found: {config_dir}")
    data: dict[str, dict] = {}
    for filename in REQUIRED_FILES:
        path = config_dir / filename
        if not path.is_file():
            raise HaltError(f"required config missing: {path.name} (§5.6 — halt)")
        try:
            with path.open("r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise HaltError(f"config unparseable: {path.name}: {e}") from e
        if content is None:
            raise HaltError(f"config empty: {path.name} (§5.6 — halt)")
        data[filename.removesuffix(".yaml")] = content
    cfg = Config(root=config_dir, data=data)
    _validate(cfg)
    return cfg


def known_addresses(people: dict | None) -> set[str]:
    """Every internal address Control recognises.

    `people.yaml` holds three lists — `people`, `vacancies` and
    `special_addresses` — and reading only the first was a real defect:
    `procure@` and `sales@` are vacant posts covered on an interim
    basis, so they carry live traffic while appearing nowhere in the
    roster. Under §13.2 an unrecognised internal sender is never
    evaluated, so every submission from the two mailboxes Ahmed Hassan
    actually works from would have been refused and flagged as possible
    impersonation. That is the "wrongly returns correct work" failure
    §13.1 says costs the system its authority permanently.

    **Leavers are deliberately excluded.** A departed employee's
    address is not a recognised sender: mail arriving from it after
    their departure is precisely the impersonation case §13.2 exists
    for, and folding leavers back into the roster would silence it.
    """
    data = people or {}
    addresses: set[str] = set()

    for entry in data.get("people") or []:
        if entry.get("active") is False:
            continue
        email = str(entry.get("email") or "").lower()
        if email:
            addresses.add(email)

    for entry in data.get("vacancies") or []:
        email = str(entry.get("email") or "").lower()
        if email:
            addresses.add(email)

    for entry in data.get("special_addresses") or []:
        address = str(entry.get("address") or entry.get("email") or "").lower()
        if address:
            addresses.add(address)

    return addresses


def deactivated_addresses(people: dict | None) -> dict[str, dict]:
    """Leavers, by address (§3.3).

    Reads the `leavers` list and any `people` entry marked
    `active: false`, so deactivating in place and moving to the leavers
    list both work — a roster edited by a human under time pressure
    should not depend on which of the two they chose.

    Reminders to these suppress **and log**. Silent suppression is
    indistinguishable from a system that simply missed them.
    """
    data = people or {}
    out: dict[str, dict] = {}
    for entry in list(data.get("leavers") or []) + list(data.get("people") or []):
        if entry.get("active") is False:
            email = str(entry.get("email") or "").lower()
            if email:
                out[email] = entry
    return out


def _validate(cfg: Config) -> None:
    people = cfg["people"].get("people", [])
    if not people:
        raise HaltError("people.yaml has no people — the roster is operative (§3)")
    emails = [p.get("email") for p in people]
    if len(emails) != len(set(emails)):
        raise HaltError("people.yaml contains duplicate emails")
    for p in people:
        if not p.get("email") or p.get("tier") not in (1, 2, 3, 4):
            raise HaltError(f"people.yaml entry invalid: {p.get('name') or p}")

    lp = cfg["learning-policy"]
    if lp.get("learning_mode") not in ("OBSERVE", "PROPOSE", "ADAPTIVE"):
        raise HaltError("learning-policy.yaml: learning_mode must be OBSERVE|PROPOSE|ADAPTIVE")

    # Raises if the scope is declared LIVE with an open precondition
    # (§3.1a) — Control never widens its own reach.
    from .scope import load_scope

    load_scope(cfg["mailbox-scope"])

    conf = cfg["confidential"]
    if conf.get("processing") != "DISABLED":
        # D-01 is a locked CEO decision; anything else in the file is
        # either tampering or an un-chartered change. Halt and surface.
        raise HaltError(
            "confidential.yaml: processing must be DISABLED per CEO decision "
            "D-01 — changing it requires a charter amendment, not a config edit"
        )
