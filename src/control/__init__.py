"""Control — adaptive obligation & deadline control engine (charter v4.10).

Core invariants enforced at this layer, not left to discipline:
- append-only system of record (§5.2)
- hash-chained audit log (§1.9, §13.3)
- legal-state validation at startup (§16, §5.6)
- halt on missing config or failed integrity (§5.6)
"""

CHARTER_VERSION = "4.10"


class HaltError(Exception):
    """Raised when §5.6 requires the cycle to halt rather than continue.

    A halt is not a crash: the caller logs it, sends one CEO failure
    notice, and stops. Never operate on a partial view.
    """
