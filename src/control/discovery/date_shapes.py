"""Date shapes in a document — the statistic, never the value.

Split out of `date_diagnosis` so the scan can compute it while a
document is open. That matters for one population only, and it is the
population that turned out to matter most: **client-confidential
contracts retain no text under D-14**, so nothing can be measured about
them after the fact. The shape histogram has to be taken while the text
is in hand and the text then dropped, exactly as D-05 takes a date and
drops the clause around it.

What is kept is a count per shape — `NNNN/NN/NN: 199`. No date, no
clause, nothing traceable to a document's content. That is a derived
statistic of the same kind as the OCR confidence D-14 already permits
storing, and it is what makes the difference between "the D-05
exception is producing one date from 208 contracts" being visible and
being invisible.
"""

import re

# Deliberately broader than the parser: this looks for what a person
# would read as a date, including what the engine cannot parse. That
# difference is the whole measurement.
CANDIDATES = (
    re.compile(r"\d{1,4}\s*[./\-]\s*\d{1,2}\s*[./\-]\s*\d{2,4}"),
    re.compile(r"\d{1,2}\s+[^\W\d_]{3,12}\.?\s+\d{2,4}"),
    re.compile(r"[^\W\d_]{3,12}\s+\d{1,2},?\s+\d{4}"),
)


def shape(text: str) -> str:
    """`31.12.2027` becomes `NN.NN.NNNN`.

    Digits to N, Latin letters to A, everything else to ع — enough to
    see which formats the estate writes without carrying a value out of
    a document (§12.1.2).
    """
    out = []
    for char in str(text).strip():
        if char.isdigit():
            out.append("N")
        elif char.isalpha():
            out.append("A" if char.isascii() else "ع")
        else:
            out.append(char)
    # Runs of letters collapse: a month name's length is not the point.
    return re.sub(r"A{2,}", "A+", re.sub(r"ع{2,}", "ع+", "".join(out)))


def candidates(text: str) -> list[str]:
    found: list[str] = []
    for pattern in CANDIDATES:
        found.extend(match.group(0) for match in pattern.finditer(text))
    return found


def histogram(text: str, parse) -> tuple[dict, dict]:
    """(parsed shapes, unparsed shapes) for one document's text.

    `parse` is injected so this module never imports the parser it is
    measuring, and so a caller holding confidential text can compute the
    histogram and discard the text in the same breath.
    """
    parsed: dict[str, int] = {}
    unparsed: dict[str, int] = {}
    for candidate in candidates(text):
        bucket = parsed if parse(candidate) else unparsed
        key = shape(candidate)
        bucket[key] = bucket.get(key, 0) + 1
    return parsed, unparsed
