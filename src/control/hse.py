"""HSE reporting, split by what the record contains — B5, D-17, D-18.

Two kinds of document arrive from the same function and need opposite
treatment. A monthly statistics return is a class 3 operational report
and gets all seven checks. An individual incident report is
special-category health data (D-17) and is never read at all (D-18) —
so it gets the §12.1.3 reduced set, exactly as a client-confidential
item does, for a completely different reason.

The reason matters in the output even though the treatment is the same.
A report line saying "not assessed — confidential scope" about an
injury record would be describing an NDA that does not exist, and would
lose the fact that the restriction is a data-protection one the CEO
took a decision about.

**Classification is on metadata only** — subject line and attachment
filenames. Deciding whether a document may be read by reading it is not
a control.

**The asymmetry is deliberate and matches §12.1.1.** Treating an
aggregate as restricted costs a check. Treating an incident as an
aggregate processes health data with no lawful basis for it, and
reading incident content is a §7 stop condition of the execution order.
So an incident marker anywhere wins, and anything unmatched is
restricted.
"""

from dataclasses import dataclass, field

HSE_INCIDENT = "HSE_INCIDENT"


@dataclass(frozen=True)
class HseVerdict:
    restricted: bool
    reason: str


@dataclass
class HseScope:
    """The B5 split, loaded from `config/hse.yaml`."""

    incident_markers: tuple = ()
    aggregate_markers: tuple = ()
    restricted_when_unmatched: bool = True
    cc_excluded: bool = True
    cc_exclusion_status: str = ""
    configured: bool = False

    @classmethod
    def from_config(cls, config: dict | None) -> "HseScope":
        config = config or {}
        return cls(
            incident_markers=tuple(
                str(m).lower() for m in (config.get("incident_markers") or [])),
            aggregate_markers=tuple(
                str(m).lower() for m in (config.get("aggregate_markers") or [])),
            restricted_when_unmatched=(
                str(config.get("default_when_unmatched") or "restricted").lower()
                == "restricted"),
            cc_excluded=bool(config.get("cc_excluded", True)),
            cc_exclusion_status=str(config.get("cc_exclusion_status") or ""),
            configured=bool(config),
        )

    def classify(self, subject: str, attachments=()) -> HseVerdict:
        """Restricted or not, and the sentence that says why.

        Call this only for items already known to be HSE. It does not
        decide whether something is HSE — an "incident" in a procurement
        thread is not a health record.
        """
        if not self.configured:
            # No config is not permission. An HSE item with no rule to
            # classify it by is restricted, and says so (§1.1, §1.3).
            return HseVerdict(True, (
                "hse.yaml is missing, so HSE items cannot be split into "
                "incident and aggregate. Every HSE item is treated as an "
                "incident record and read metadata-only (D-18) — the "
                "conservative direction, not a working control."))

        haystack = " ".join([subject or ""] + [a or "" for a in attachments]).lower()

        hits = [m for m in self.incident_markers if m in haystack]
        if hits:
            return HseVerdict(True, (
                f"individual incident record — special-category health data "
                f"(D-17), read metadata-only and never opened (D-18). "
                f"Matched on {', '.join(sorted(hits)[:3])}."))

        if any(m in haystack for m in self.aggregate_markers):
            return HseVerdict(False, (
                "aggregate HSE statistics — no individual health data, so "
                "the full check set applies (D-17 does not reach counts)."))

        if self.restricted_when_unmatched:
            return HseVerdict(True, (
                "HSE item matching neither the incident nor the aggregate "
                "markers. Treated as an incident record: misclassifying an "
                "aggregate costs a check, misclassifying an incident "
                "processes health data with no basis (D-17, D-18)."))
        return HseVerdict(False, "no incident marker matched")


def cc_exclusion_note(scope: HseScope) -> list[str]:
    """The disclosure that goes with applying an unconfirmed tightening.

    D-04's exclusion list predates D-17 and does not name special
    category data. Control applies the exclusion — §14.1 permits
    tightening without approval — and says that it did, because a
    control applied quietly is indistinguishable from one nobody
    decided on.
    """
    if not (scope.configured and scope.cc_excluded):
        return []
    return [
        "CONTINUITY CC: HSE incident notices are withheld from the "
        f"{scope.cc_exclusion_status or 'continuity CC'}. D-04's exclusion "
        "list was written before D-17 and does not name special-category "
        "health data; Control applies the exclusion anyway, because "
        "§14.1 permits tightening without approval and requires it only "
        "to loosen. This is a tightening applied and disclosed, not a "
        "decision taken — the CEO is asked to confirm it as an extension "
        "of D-04."
    ]
