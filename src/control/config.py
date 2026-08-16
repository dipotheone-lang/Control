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
