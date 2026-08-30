"""Why terms carry no date — a measurement, not a guess (§1.1).

Two full scans of 957 documents produced 525 commercial terms and **2
dated ones**. Two fixes had already been made on reasoning alone: dates
migrating across clause boundaries, then clauses severed by line wraps.
Both were real defects; neither moved this number. A third guess is not
a method.

So this counts what is actually in the text, from the cache rather than
from the documents — the text cache exists precisely so a question like
this costs seconds instead of an hour of OCR.

It separates the three explanations that look identical from outside:

1. **The documents hold no dates at all.** A blank inspection report or
   a refund letter template mentions retention and payment terms and
   names no date, because nothing has happened yet. Then the extractor
   is right and the finding is about the folder: those are templates,
   not contracts, and the guarantees are somewhere else.
2. **The dates are there and written in a shape nothing recognises.**
   `31.12.2026` is a date to every reader in Egypt and matches none of
   the three patterns, which know `/`, `-` and month names in Latin
   script only.
3. **The dates are there, in a known shape, but too far from the term
   to be paired.** That is the clause-window question, and it is the
   only one of the three the boundary logic can answer.

**Nothing here reads a confidential document.** Ordinary documents are
measured from their cached text. Client-confidential contracts retain no
text at all (D-14), so they are counted from a shape histogram taken
while the text was in hand and then dropped — the same shape as D-05
itself, which keeps a date and discards the clause around it. They are
reported apart, because the question they answer is different: whether
the exception granted for the largest clients is delivering the
guarantee expiries it was granted for.

**Nothing here prints document text.** A date shape is reported as its
shape — `NN.NN.NNNN` — so the report says what the estate writes without
reproducing what any document says (§12.1.2).
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import date_shapes
from .stage_c import _DATE_PATTERNS, _parse_date


@dataclass
class Diagnosis:
    documents: int = 0
    documents_with_no_candidate: int = 0
    documents_with_candidates: int = 0
    candidates: int = 0
    parsed: int = 0
    unparsed: int = 0
    unparsed_shapes: Counter = field(default_factory=Counter)
    parsed_shapes: Counter = field(default_factory=Counter)
    terms: int = 0
    terms_in_documents_with_no_date: int = 0
    # Client-confidential contracts retain no text (D-14), so they can
    # only be counted from statistics taken during the scan. Reported
    # apart because the D-05 exception exists for them specifically, and
    # whether it is working is a different question from whether the
    # ordinary folders parse.
    confidential_documents: int = 0
    confidential_terms_seen: int = 0
    confidential_terms_dated: int = 0
    confidential_unparsed_shapes: Counter = field(default_factory=Counter)
    confidential_parsed: int = 0
    confidential_unparsed: int = 0
    # How far each term sits from the nearest readable date. The only
    # question left once the dates parse and the terms are found: 11
    # confidential contracts produced 29 terms and 47 readable dates and
    # paired none of them, so the width between them is the answer.
    distance: Counter = field(default_factory=Counter)
    confidential_distance: Counter = field(default_factory=Counter)
    terms_dated: int = 0
    # Terms that are undated in a document which does contain a parseable
    # date somewhere. These are the only ones the clause window could
    # ever have paired, so they bound how much a boundary change can win.
    terms_undated_in_dated_documents: int = 0


def diagnose(cache_dir: Path) -> Diagnosis:
    result = Diagnosis()
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return result

    for entry in sorted(cache_dir.glob("*.json")):
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        text = payload.get("text")
        if not text:
            # Confidential (D-14) or unreadable. A confidential contract
            # carries statistics taken while its text was in hand; that
            # is the only trace of it there will ever be, and without it
            # the population D-05 exists for is invisible.
            shapes = payload.get("date_shapes")
            if shapes and payload.get("d05"):
                result.confidential_documents += 1
                result.confidential_terms_seen += payload.get("terms_seen", 0)
                result.confidential_terms_dated += payload.get("terms_dated", 0)
                result.confidential_parsed += sum(
                    (shapes.get("parsed") or {}).values())
                for name, count in (shapes.get("unparsed") or {}).items():
                    result.confidential_unparsed_shapes[name] += count
                    result.confidential_unparsed += count
                for bucket, count in (payload.get("term_date_distance")
                                      or {}).items():
                    result.confidential_distance[bucket] += count
            continue

        result.documents += 1
        for bucket, count in (payload.get("term_date_distance") or {}).items():
            result.distance[bucket] += count
        terms = payload.get("terms") or []
        result.terms += len(terms)
        dated_terms = sum(1 for t in terms if t.get("found_date"))
        result.terms_dated += dated_terms

        found = date_shapes.candidates(text)

        if not found:
            result.documents_with_no_candidate += 1
            result.terms_in_documents_with_no_date += len(terms)
            continue

        result.documents_with_candidates += 1
        result.candidates += len(found)
        document_has_parseable = False
        for candidate in found:
            if _parse_date(candidate):
                result.parsed += 1
                result.parsed_shapes[date_shapes.shape(candidate)] += 1
                document_has_parseable = True
            else:
                result.unparsed += 1
                result.unparsed_shapes[date_shapes.shape(candidate)] += 1

        if document_has_parseable:
            result.terms_undated_in_dated_documents += len(terms) - dated_terms
        else:
            result.terms_in_documents_with_no_date += len(terms)

    return result


_BUCKET_ORDER = ("<=120", "<=250", "<=500", "<=1000", "<=2500", ">2500",
                "no date in document")


def _distance_lines(counts, indent="  ") -> list[str]:
    total = sum(counts.values())
    if not total:
        return []
    lines = []
    for bucket in _BUCKET_ORDER:
        if counts.get(bucket):
            lines.append(f"{indent}  {counts[bucket]:>6}  "
                         f"{bucket:<20} ({counts[bucket] * 100 // total}%)")
    return lines


def render(result: Diagnosis) -> str:
    if not result.documents:
        return ("No cached document text to diagnose. The text cache is "
                "written by `contracts` for ordinary documents; confidential "
                "ones never retain text (D-14), so a scan of only "
                "confidential folders leaves nothing to measure here.")

    lines = [
        "DATE DIAGNOSIS — why terms carry no date",
        "",
        f"  {result.documents} document(s) with cached text  "
        f"({result.terms} term(s) found in them, {result.terms_dated} dated)",
        "",
        "WHERE THE UNDATED TERMS ARE",
        f"  {result.terms_in_documents_with_no_date} term(s) sit in documents "
        "with no date anywhere.",
        "      No clause-window change can date these. If this is most of "
        "them, the",
        "      finding is about the folder: blank forms and letter templates "
        "name a",
        "      retention and a payment term and no date, because nothing has "
        "happened",
        "      yet. The guarantees are somewhere else.",
        f"  {result.terms_undated_in_dated_documents} term(s) are undated in a "
        "document that does contain a",
        "      readable date. These are the only ones a boundary change could "
        "ever pair,",
        "      so this number bounds what tuning the window can win.",
        "",
        "WHAT THE DOCUMENTS ACTUALLY WRITE",
        f"  {result.documents_with_no_candidate} document(s) contain nothing "
        "date-shaped at all",
        f"  {result.documents_with_candidates} document(s) do — "
        f"{result.candidates} candidate(s): "
        f"{result.parsed} parsed, {result.unparsed} not",
    ]

    if result.unparsed_shapes:
        lines += [
            "",
            "  SHAPES THE ENGINE DOES NOT PARSE — the shape only, never the "
            "value (§12.1.2):",
        ]
        for shape, count in result.unparsed_shapes.most_common(12):
            lines.append(f"    {count:>6}  {shape}")
        lines += [
            "",
            "      A shape here that a person would read as a date is a "
            "missing pattern,",
            "      and every one of them is a guarantee expiry the register "
            "never sees.",
        ]
    if result.parsed_shapes:
        lines += ["", "  SHAPES IT DOES PARSE:"]
        for shape, count in result.parsed_shapes.most_common(6):
            lines.append(f"    {count:>6}  {shape}")

    if result.confidential_documents:
        lines += [
            "",
            "CLIENT-CONFIDENTIAL CONTRACTS — counted apart, and why",
            f"  {result.confidential_documents} contract(s) read under D-05. "
            f"{result.confidential_terms_seen} term(s) found in them, "
            f"{result.confidential_terms_dated} dated.",
            "      These retain no text (D-14), so nothing about them can be",
            "      measured after the fact — these counts were taken while the",
            "      text was in hand and the text dropped. They are the",
            "      population D-05 exists for: the largest clients, and the",
            "      guarantee expiries §2.2 calls the most expensive class of",
            "      miss. A low dated count here is not a finding about a",
            "      folder. It is the exception failing to deliver the thing it",
            "      was granted for.",
            f"  {result.confidential_parsed} date(s) parsed, "
            f"{result.confidential_unparsed} not.",
        ]
        distance = _distance_lines(result.confidential_distance)
        if distance:
            lines += [
                "  HOW FAR EACH TERM SITS FROM THE NEAREST READABLE DATE:",
                *distance,
                "      The window is 120 characters. Everything below that is",
                "      a term the engine can already reach; everything above",
                "      it is a date sitting in the document, readable, and out",
                "      of range. Widening blind is how a date from the clause",
                "      next door enters a register (§2.1) — this says how far",
                "      it would have to go, so the decision is made on the",
                "      number rather than on a guess.",
            ]
        if result.confidential_unparsed_shapes:
            lines.append("  SHAPES THEY WRITE THAT NOTHING PARSES:")
            for name, count in result.confidential_unparsed_shapes.most_common(8):
                lines.append(f"    {count:>6}  {name}")

    distance = _distance_lines(result.distance)
    if distance:
        lines += ["", "HOW FAR EACH TERM SITS FROM THE NEAREST READABLE DATE",
                  *distance]

    lines += [
        "",
        f"  The engine knows {len(_DATE_PATTERNS)} date patterns. This "
        "counts what the estate writes,",
        "  so the two can be compared instead of assumed equal (§1.1).",
    ]
    return "\n".join(lines)
