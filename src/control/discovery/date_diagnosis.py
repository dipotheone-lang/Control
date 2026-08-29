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

**Nothing here reads a confidential document.** It works on cached text,
which is retained for ordinary documents only (D-14), so confidential
contracts are absent by construction rather than by filtering.

**Nothing here prints document text.** A date shape is reported as its
shape — `NN.NN.NNNN` — so the report says what the estate writes without
reproducing what any document says (§12.1.2).
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .stage_c import _DATE_PATTERNS, _parse_date

# Deliberately broader than _DATE_PATTERNS: this is looking for things a
# human would read as a date, including the ones the engine cannot parse.
# That difference is the whole measurement.
_CANDIDATES = (
    re.compile(r"\d{1,4}\s*[./\-]\s*\d{1,2}\s*[./\-]\s*\d{2,4}"),
    re.compile(r"\d{1,2}\s+[^\W\d_]{3,12}\.?\s+\d{2,4}"),
    re.compile(r"[^\W\d_]{3,12}\s+\d{1,2},?\s+\d{4}"),
)

# Digits to N, letters to A: enough to see "NN.NN.NNNN" or "NN AAA NNNN"
# without carrying a value out of a document.
_SHAPE = str.maketrans({})


def _shape(text: str) -> str:
    out = []
    for char in text.strip():
        if char.isdigit():
            out.append("N")
        elif char.isalpha():
            out.append("A" if char.isascii() else "ع")
        else:
            out.append(char)
    # Collapse runs so "NNNN" and "NN" stay distinct but "AAAAAAA" and
    # "AAAA" do not — the month name's length is not the point.
    return re.sub(r"A{2,}", "A+", re.sub(r"ع{2,}", "ع+", "".join(out)))


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
            continue                      # confidential (D-14), or unreadable

        result.documents += 1
        terms = payload.get("terms") or []
        result.terms += len(terms)
        dated_terms = sum(1 for t in terms if t.get("found_date"))
        result.terms_dated += dated_terms

        found: list[str] = []
        for pattern in _CANDIDATES:
            found.extend(pattern.findall(text) if pattern.groups == 0
                         else [m.group(0) for m in pattern.finditer(text)])
        # findall returns tuples when a pattern has groups; these have
        # none, so the strings come back directly.
        found = [f if isinstance(f, str) else "".join(f) for f in found]

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
                result.parsed_shapes[_shape(candidate)] += 1
                document_has_parseable = True
            else:
                result.unparsed += 1
                result.unparsed_shapes[_shape(candidate)] += 1

        if document_has_parseable:
            result.terms_undated_in_dated_documents += len(terms) - dated_terms
        else:
            result.terms_in_documents_with_no_date += len(terms)

    return result


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

    lines += [
        "",
        f"  The engine knows {len(_DATE_PATTERNS)} date patterns. This "
        "counts what the estate writes,",
        "  so the two can be compared instead of assumed equal (§1.1).",
    ]
    return "\n".join(lines)
