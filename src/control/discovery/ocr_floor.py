"""What each OCR confidence floor would admit — §5.5, §14.4.

The floor is at 60 because 60 is the default, and the charter is
explicit that this is the wrong reason:

> *OCR with Arabic support and a **confidence floor**. Below it:
> `UNREADABLE — MANUAL REVIEW REQUIRED`, not evaluated, not posted.*

§5.5 makes it a governance number, set from this estate's own documents
rather than from a value chosen without seeing them. The first live run
produced the distribution to set it from: 92 of 157 documents trusted,
55 below the floor, readings spanning 30.7 to 94.6 with a median of
71.4. Fifty-five documents post nothing, and some of them are legal
documents belonging to the largest clients.

**This reports; it never changes anything.** §14.4 is unambiguous — the
confidence floor is never lowered by learning, at any confidence level,
at any maturity level. The floor moves when a human moves it in
`config`, or it does not move.

WHAT THIS CAN AND CANNOT TELL YOU

It says how many documents each floor would admit. It cannot say what
those documents contain, and does not pretend to: a document below the
floor was never read, so its text was never kept. Lowering the floor is
therefore a decision to trust readings at a stated confidence, made
before knowing what they say — which is exactly the shape of decision
§5.5 reserves for a person.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Bands to report the distribution in. Ten points wide: narrow enough to
# see where the mass sits, wide enough that a band is not one document.
_BANDS = ((0, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80),
          (80, 90), (90, 101))

# The floors worth costing. Anything below 40 is not a floor, it is the
# absence of one.
_CANDIDATES = (40, 50, 55, 60, 65, 70, 75, 80)


@dataclass
class FloorEvidence:
    attempted: int = 0
    read: int = 0
    below: int = 0
    failed: int = 0
    confidences: list = field(default_factory=list)
    bands: Counter = field(default_factory=Counter)
    # Below-floor documents that are client-confidential. Called out
    # because D-05 exists for those specifically and the guarantee
    # expiries §2.2 rates most expensive are in them.
    below_confidential: int = 0
    floor_in_force: float = 0.0


def gather(cache_dir: Path, floor_in_force: float = 60.0) -> FloorEvidence:
    evidence = FloorEvidence(floor_in_force=floor_in_force)
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return evidence

    for entry in sorted(cache_dir.glob("*.json")):
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        info = payload.get("ocr") or {}
        if not info.get("attempted"):
            continue

        evidence.attempted += 1
        if info.get("failed"):
            evidence.failed += 1
            continue

        confidence = float(info.get("confidence") or 0.0)
        evidence.confidences.append(confidence)
        for low, high in _BANDS:
            if low <= confidence < high:
                evidence.bands[f"{low}-{high - 1}"] += 1
                break

        if info.get("read"):
            evidence.read += 1
        else:
            evidence.below += 1
            if payload.get("d05") or payload.get("confidential"):
                evidence.below_confidential += 1
    return evidence


def render(evidence: FloorEvidence) -> str:
    if not evidence.attempted:
        return ("No OCR readings in the cache. Run `contracts --ocr` first — "
                "this reads the confidences that run recorded, so the floor "
                "is set from this estate's documents rather than from a "
                "default (§5.5).")

    values = sorted(evidence.confidences)
    lines = [
        "OCR CONFIDENCE FLOOR — what each choice would admit",
        "",
        f"  {evidence.attempted} document(s) OCR'd: {evidence.read} trusted, "
        f"{evidence.below} below the floor in force "
        f"({evidence.floor_in_force:g}), {evidence.failed} failed outright.",
    ]
    if evidence.below_confidential:
        lines.append(
            f"  {evidence.below_confidential} of the below-floor documents "
            "are client-confidential — the population D-05 exists for, and "
            "where §2.2 puts the most expensive class of miss.")

    if values:
        lines += [
            "",
            f"  readings: min {values[0]:.1f}, median "
            f"{values[len(values) // 2]:.1f}, max {values[-1]:.1f}",
            "",
            "  DISTRIBUTION",
        ]
        widest = max(evidence.bands.values()) if evidence.bands else 1
        for low, high in _BANDS:
            key = f"{low}-{high - 1}"
            count = evidence.bands.get(key, 0)
            if not count:
                continue
            bar = "#" * max(1, round(count * 40 / widest))
            lines.append(f"    {key:>7}  {count:>5}  {bar}")

    lines += ["", "  WHAT EACH FLOOR WOULD ADMIT", ""]
    for candidate in _CANDIDATES:
        admitted = sum(1 for c in values if c >= candidate)
        rejected = len(values) - admitted
        marker = "  <- in force" if candidate == evidence.floor_in_force else ""
        lines.append(f"    floor {candidate:>3}   {admitted:>5} admitted   "
                     f"{rejected:>5} unreadable{marker}")

    lines += [
        "",
        "  WHAT THIS DOES NOT TELL YOU",
        "    How many of those admitted documents contain anything useful. A",
        "    document below the floor was never read, so its text was never",
        "    kept — lowering the floor is a decision to trust readings at a",
        "    stated confidence, taken before knowing what they say. That is",
        "    the shape of decision §5.5 reserves for a person.",
        "",
        "  THE RULE THAT DOES NOT MOVE",
        "    §14.4: the confidence floor is never lowered by learning, at any",
        "    confidence level, at any maturity level. Nothing here changes a",
        "    setting. Edit `ocr_floor` in the run, or the default, by hand.",
        "",
        "    A wrong value in a register is worse than no value (§5.5). The",
        "    floor is what turns an unreadable document into a stated gap",
        "    instead of a confident mistake, so raising it costs coverage and",
        "    lowering it costs exactly that guarantee.",
    ]
    return "\n".join(lines)
