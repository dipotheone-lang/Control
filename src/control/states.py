"""Legal operating states — charter §16 state table, enforced per §5.6.

Any combination of (phase, maturity level, RUN_MODE, LEARNING_MODE) not in
the table is illegal and must halt at startup, same as failed integrity.
Illegal-but-representable states are where control systems rot.
"""

from dataclasses import dataclass

from . import HaltError

RUN_MODES = ("DISCOVERY", "DRY_RUN", "SUPERVISED", "LIVE")
LEARNING_MODES = ("OBSERVE", "PROPOSE", "ADAPTIVE")


@dataclass(frozen=True)
class State:
    phase: int
    level: int
    run_mode: str
    learning_mode: str


# One row per phase — charter §16.
LEGAL_STATES: tuple[State, ...] = (
    State(0, 0, "DISCOVERY", "OBSERVE"),
    State(1, 1, "DRY_RUN", "OBSERVE"),
    State(2, 2, "SUPERVISED", "OBSERVE"),
    State(3, 3, "LIVE", "PROPOSE"),
    State(4, 4, "LIVE", "ADAPTIVE"),
    State(5, 5, "LIVE", "ADAPTIVE"),
)


def validate_state(level: int, run_mode: str, learning_mode: str) -> State:
    """Return the matching legal state or raise HaltError (§5.6 rule 4)."""
    for s in LEGAL_STATES:
        if (s.level, s.run_mode, s.learning_mode) == (level, run_mode, learning_mode):
            return s
    raise HaltError(
        f"illegal state: level={level} RUN_MODE={run_mode} "
        f"LEARNING_MODE={learning_mode} is not a row of the §16 state table"
    )


def demotion_target(current_level: int, trigger: str) -> State:
    """Demotion target per trigger — charter §15 (v4.3).

    - missed class 1/2 traced to system failure, or a security event
      -> Level 2 (autonomous sending revoked, alerts stay live)
    - dispute-upheld rate above threshold, or failed self-audit
      -> one level down
    """
    if trigger in ("missed_class_1_2_system_failure", "security_event"):
        target_level = min(current_level, 2)
    elif trigger in ("dispute_rate", "failed_self_audit"):
        target_level = max(current_level - 1, 0)
    else:
        raise ValueError(f"unknown demotion trigger: {trigger}")
    for s in LEGAL_STATES:
        if s.level == target_level:
            return s
    raise AssertionError("state table has no row for target level")
