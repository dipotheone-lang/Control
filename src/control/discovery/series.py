"""Recurring document series — Stage D, from the drive rather than the mail.

§6 Stage D asks for obligations proposed with "owner, observed cadence
measured from timestamps, form, governing clause, historical volume, last
occurrence, observed compliance rate, and confidence". `analyse.py` does
that against the mailboxes, and against these mailboxes it finds almost
nothing: the high-confidence recurring senders are the tax portal and the
e-invoicing gateway, and the internal reporting that Stage D exists to
find leaves no repeating trace in `control@` because it was never sent
there.

It is on the drive. `1. Invoices/2022 In/Progress Reports - 2022 In/`
holds thirty-three workbooks named to a pattern, one or two a month for
two years, and that is an obligation whether or not anybody wrote it
down. A register built from the mailboxes alone would have missed the
company's actual reporting and reported an empty class 3 with a clean
conscience.

**What counts as evidence here is the filename and the timestamp, nothing
else.** No document is opened. That keeps the scan inside §12.1.2 for
confidential items by construction rather than by a check that could be
forgotten, and it means the series detector says *"thirty-three documents
named to one pattern arrived roughly monthly"* — an observation — rather
than *"the monthly progress report obligation exists"*, which is a
conclusion for the CEO.

**Dormancy is reported, never resolved.** A series that ran for two years
and stopped is either a retired obligation or an unmet one, and the
difference is invisible from the filesystem. §6 names both outcomes —
*dead reports* and *ghost requirements* — and asks for them to be listed
separately rather than merged into a count of things that look fine.
"""

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Tokens that vary between instances of the same series and must be
# removed before two filenames can be compared: the period the document
# covers, and the sequence number it carries.
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|"
    "يناير|فبراير|مارس|أبريل|ابريل|مايو|يونيو|يوليو|يوليه|أغسطس|اغسطس|"
    "سبتمبر|أكتوبر|اكتوبر|نوفمبر|ديسمبر"
)
_MONTH_RE = re.compile(r"(?i)\b(?:%s)\b" % _MONTHS)
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_DIGITS_RE = re.compile(r"\d+")
_PUNCT_RE = re.compile(r"[^0-9a-z؀-ۿ#]+")

# Below this a "pattern" is two files that happen to be named alike.
MIN_INSTANCES = 3

# How far past its own rhythm a series may fall before it is dormant. Two
# missed cycles rather than a fixed number of days, so a quarterly series
# is not called dead for being three months quiet.
DORMANT_CYCLES = 2
DORMANT_FLOOR_DAYS = 120

# Cadence buckets, by the median gap in days between consecutive
# instances. Wide, because real filing is irregular and a narrow bucket
# would report "irregular" for everything the company actually does.
_CADENCE_BUCKETS = (
    (0, 2, "daily"),
    (2, 10, "weekly"),
    (10, 20, "fortnightly"),
    (20, 45, "monthly"),
    (45, 135, "quarterly"),
    (135, 260, "semi-annual"),
    (260, 460, "annual"),
)


@dataclass
class Series:
    template: str
    folder: str
    paths: list = field(default_factory=list)
    dates: list = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.paths)

    @property
    def first(self) -> date:
        return min(self.dates)

    @property
    def last(self) -> date:
        return max(self.dates)

    @property
    def median_gap_days(self) -> float:
        ordered = sorted(self.dates)
        gaps = [(b - a).days for a, b in zip(ordered, ordered[1:])]
        gaps = [g for g in gaps if g > 0]
        return statistics.median(gaps) if gaps else 0.0

    @property
    def cadence(self) -> str:
        gap = self.median_gap_days
        if not gap:
            return "irregular"
        for low, high, name in _CADENCE_BUCKETS:
            if low <= gap < high:
                return name
        return "irregular"

    @property
    def months_covered(self) -> int:
        return len({(d.year, d.month) for d in self.dates})

    def dormant_since(self, today: date) -> int:
        """Days past the point where the next instance was due, or 0."""
        gap = self.median_gap_days or DORMANT_FLOOR_DAYS
        allowance = max(gap * DORMANT_CYCLES, DORMANT_FLOOR_DAYS)
        overdue = (today - self.last).days - allowance
        return int(overdue) if overdue > 0 else 0

    @property
    def confidence(self) -> str:
        """§6 Stage D: HIGH >=12 regular, MEDIUM 4-11 or irregular, LOW <4."""
        if self.count >= 12 and self.cadence != "irregular":
            return "HIGH"
        if self.count >= 4 or self.cadence != "irregular":
            return "MEDIUM"
        return "LOW"

    @property
    def example(self) -> str:
        """One real path from the series.

        The earliest by date rather than the alphabetically first: a
        register row is read alongside "observed since", and an example
        from the middle of the run makes the two look inconsistent.
        """
        return min(zip(self.dates, self.paths))[1]

    @property
    def folder_label(self) -> str:
        """The real folder, not the normalised template.

        The template exists to group instances and is unreadable by
        design — every digit and month name in it has been replaced.
        Putting it in front of the CEO would be asking someone to
        approve `# quotations # q # canal sugar`, so the register shows
        where the documents actually are.
        """
        parent = Path(self.example.replace("\\", "/")).parent.as_posix()
        return "" if parent == "." else parent

    @property
    def label(self) -> str:
        """A name for the series, taken from a document in it."""
        return Path(self.example.replace("\\", "/")).stem

    @property
    def extensions(self) -> list:
        return sorted({Path(p.replace("\\", "/")).suffix.lower()
                       for p in self.paths})


def template_of(relative_path: str) -> tuple[str, str]:
    """Return (folder template, filename template) for one path.

    The folder is normalised too. `2021 In/Progress Reports - 2021 In` and
    `2022 In/Progress Reports - 2022 In` are one series filed a year
    apart, and treating them as two would halve every count and turn a
    four-year monthly report into a set of short unrelated runs.
    """
    path = Path(relative_path.replace("\\", "/"))
    folder = _normalise(path.parent.as_posix()) if path.parent.as_posix() != "." else ""
    stem = _normalise(path.stem)
    return folder, stem


def _normalise(text: str) -> str:
    lowered = text.lower()
    lowered = _MONTH_RE.sub("#", lowered)
    lowered = _YEAR_RE.sub("#", lowered)
    lowered = _DIGITS_RE.sub("#", lowered)
    lowered = _PUNCT_RE.sub(" ", lowered)
    # Runs of placeholders carry no information and differ between
    # instances ("no. 001 - 2022" vs "no 19 2023"), so they collapse.
    return " ".join(w for w in lowered.split() if w) .replace("# #", "#") \
        .replace("# #", "#")


def detect(rows, *, min_instances: int = MIN_INSTANCES) -> list[Series]:
    """Group inventory rows into series.

    `rows` is anything with `path` and `modified` — the Stage B inventory
    reader yields dicts, and so does a direct walk. Rows whose date will
    not parse are dropped from the timing analysis rather than defaulted
    to today, which would make every stale series look current.
    """
    grouped: dict[tuple[str, str], Series] = {}
    for row in rows:
        relative = str(row.get("path") or "")
        if not relative:
            continue
        try:
            when = date.fromisoformat(str(row.get("modified"))[:10])
        except (TypeError, ValueError):
            continue
        folder, stem = template_of(relative)
        if not stem:
            continue
        key = (folder, stem)
        series = grouped.get(key)
        if series is None:
            series = grouped[key] = Series(template=stem, folder=folder)
        series.paths.append(relative)
        series.dates.append(when)

    return sorted(
        (s for s in grouped.values() if s.count >= min_instances),
        key=lambda s: (-s.count, s.folder, s.template),
    )


def significant(series: list[Series], *, min_months: int = 3) -> list[Series]:
    """Series that look like a repeating obligation rather than a batch.

    Twenty files written on one afternoon are a filing exercise, not a
    cadence. Requiring instances in at least three distinct months is what
    separates "this recurs" from "somebody tidied a folder", and it is the
    same distinction `analyse.py` draws against bulk sends in the mail.
    """
    return [s for s in series if s.months_covered >= min_months]


def read_inventory(path: Path):
    """Stage B's file-inventory.csv, as rows for `detect`."""
    import csv

    with Path(path).open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            yield row


def walk(root: Path):
    """Rows straight from the filesystem, when no inventory exists yet.

    Metadata only: name, size and timestamp. Nothing is opened, so this
    is safe over confidential folders by construction (§12.1.2).
    """
    from datetime import datetime, timezone

    root = Path(root)
    for item in root.rglob("*"):
        try:
            if not item.is_file():
                continue
            stat = item.stat()
        except OSError:
            continue
        yield {
            "path": item.relative_to(root).as_posix(),
            "modified": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc).date().isoformat(),
            "ext": item.suffix.lower(),
            "size_bytes": stat.st_size,
        }
