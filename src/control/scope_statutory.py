"""Statutory-only operation — decision D-15.

The CEO narrowed the project on 30-Aug-2026 after reading the status
page. Control operates on class 1 statutory obligations and reads no
mailbox: deadlines computed from `statutory-calendar.yaml`, alerts to
the named owner and the CEO on the §2.1 schedule, nothing else.

WHY THIS IS ENFORCED RATHER THAN DOCUMENTED

A narrowing that lives only in a decision document is a narrowing until
somebody runs the wrong command. The whole basis for operating without
the §12 pre-conditions is that no mailbox is read and no person's work
is evaluated — so a single `cycle` that swept a mailbox would not be an
inconvenience, it would process personal data with no lawful basis
documented and no employee notified (§12.2, §12.4).

So the scope refuses. `assert_scope_permits` raises `HaltError` on any
capability outside it, the same way D-08 refuses an interim transport
rather than trusting the operator to remember the phase.

WHAT IT DOES NOT DO

It does not relax anything. §1 holds in full, §10's external gate never
opens, and D-08 still requires Graph before anything sends on a
schedule — a missed class 1 alert is the failure this scope exists to
prevent, and a transport needing a powered laptop cannot carry it.

Nothing is deleted either. The evaluation engine, the watchdog, the
class 2 registers and the learning layer stay in the repository under
test. Widening means closing the §12 pre-conditions and moving the scope
back, not rebuilding.
"""

from . import HaltError

FULL = "FULL"
STATUTORY_ONLY = "STATUTORY_ONLY"

SCOPES = (FULL, STATUTORY_ONLY)

# Capabilities a scope may or may not exercise. Named rather than
# inferred from the run mode: the point of D-15 is that a narrowed scope
# and a phase are different things, and conflating them is how a
# narrowing quietly widens.
MAILBOX_READ = "mailbox_read"
SUBMISSION_EVALUATION = "submission_evaluation"
EXTERNAL_WATCHDOG = "external_watchdog"
ANOMALY_SIGNALS = "anomaly_signals"
CLASS3_LADDER = "class3_ladder"
CLASS2_REGISTERS = "class2_registers"
LEARNING = "learning"
STATUTORY_ALERTS = "statutory_alerts"
# Opening the transport to SEND. Separate from MAILBOX_READ on
# purpose: D-58 lets Outlook carry class 1 alerts out of this
# machine while nothing is ever read back in, and one capability
# covering both would have made that indistinguishable from
# reopening the mailbox.
TRANSPORT_SEND = "transport_send"

_WITHHELD = {
    MAILBOX_READ: (
        "reads a mailbox. The basis for operating without the §12 "
        "pre-conditions is that none is read — no PDPL lawful basis is "
        "documented and no employee has been notified (§12.2, §12.4)"),
    SUBMISSION_EVALUATION: (
        "evaluates a person's work. §12.4's usage policy governs exactly "
        "that and is not circulated (0 of 11)"),
    EXTERNAL_WATCHDOG: (
        "tracks external correspondence, which needs the mailbox"),
    ANOMALY_SIGNALS: (
        "reads transaction data Control is not receiving in this scope. "
        "The §3.2 segregation-of-duties exposure is unchanged — narrowing "
        "the software does not narrow it, and it stands in the discovery "
        "record"),
    CLASS3_LADDER: (
        "chases internal reports. Out of scope under D-15"),
    CLASS2_REGISTERS: (
        "alerts on commercial registers. 130 of 314 documents in the "
        "contract folders were unreadable, so these could not be "
        "populated from the archive — a property of the estate, not of "
        "the engine"),
    LEARNING: (
        "adapts from operating history. §14 needs disputes, overrides and "
        "variance history, none of which this scope produces"),
}


def normalise(value: str | None) -> str:
    scope = str(value or FULL).strip().upper()
    if scope not in SCOPES:
        raise HaltError(
            f"OPERATING_SCOPE={value!r} is not one of {', '.join(SCOPES)}. "
            "An unrecognised scope halts rather than defaulting: defaulting "
            "would pick the wider one (§5.6).")
    return scope


def permits(scope: str, capability: str) -> bool:
    if normalise(scope) == FULL:
        return True
    return capability not in _WITHHELD


def assert_scope_permits(scope: str, capability: str) -> None:
    """Refuse a capability the scope does not carry.

    Raises rather than returning False, because the callers are commands
    a person runs and a silently skipped step reads as a completed one.
    """
    if permits(scope, capability):
        return
    raise HaltError(
        f"OPERATING_SCOPE=STATUTORY_ONLY does not permit {capability}: "
        f"this {_WITHHELD[capability]}. Decision D-15 narrowed "
        "Control to class 1 statutory obligations. Nothing is deleted — "
        "widening means closing the §12 pre-conditions and moving the "
        "scope back.")


def summary(scope: str) -> list[str]:
    """What this scope does and does not do, for the operator."""
    if normalise(scope) == FULL:
        return ["OPERATING_SCOPE=FULL — the charter as written."]
    return [
        "OPERATING_SCOPE=STATUTORY_ONLY (D-15, charter v4.12)",
        "  Doing:     class 1 statutory deadlines — §0's first priority,",
        "             'no statutory deadline is missed'.",
        "  Not doing: report chasing, external SLA, verdicts, anomaly and",
        "             fraud signals, commercial registers, learning.",
        "  Not read:  any mailbox. Nothing is fetched, classified or",
        "             evaluated — that is the basis for operating without",
        "             the §12 pre-conditions, and it is enforced rather",
        "             than remembered.",
        "  Sends via: Outlook on this machine (D-58), class 1 alerts only.",
        "             Opening the transport to send is not reading: no",
        "             message comes back in. An alert only leaves while",
        "             the laptop is awake and Outlook is running — when it",
        "             is not, the alert is written UNDELIVERED and tried",
        "             again on the next run, never marked sent.",
        "  Unchanged: §1 in full, §10's external gate — no message ever",
        "             leaves for an address outside ubcsis.com — and",
        "             §2.1's advisor verification (O-03).",
        "  Accepted:  D-08 said a transport needing a powered laptop",
        "             cannot hold a class 1 schedule. That is still true.",
        "             D-58 accepts it, because the alternative here was",
        "             no delivery at all rather than Graph.",
        "  Standing:  the §3.2 segregation-of-duties exposure. Narrowing",
        "             the software does not narrow it.",
    ]
