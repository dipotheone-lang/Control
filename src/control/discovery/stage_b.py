"""Stage B — folder inventory (charter §6).

Walk UB_ROOT, classify every file, write file-inventory.csv. Flag
duplicates (identical content hash), competing revisions (same
normalised name, different files), and dormant folders. Read-only on
sources; output goes to discovery/ only.
"""

import csv
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path

CATEGORIES = {
    "spreadsheet": {".xlsx", ".xlsm", ".xls", ".csv", ".ods"},
    "document": {".docx", ".doc", ".rtf", ".txt", ".md", ".odt"},
    "pdf": {".pdf"},
    "presentation": {".pptx", ".ppt"},
    "image": {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic"},
    "cad": {".dwg", ".dxf", ".rvt"},
    "mail-archive": {".pst", ".ost", ".msg", ".eml", ".mbox"},
    "archive": {".zip", ".rar", ".7z"},
}
_EXT_TO_CATEGORY = {ext: cat for cat, exts in CATEGORIES.items() for ext in exts}

# Tokens that distinguish revisions of the same logical document:
# "report rev2", "report_v3", "report (1)", "report - final copy".
_REVISION_TOKENS = re.compile(
    r"(?i)[\s_\-.]*(?:rev(?:ision)?|v(?:er(?:sion)?)?)[\s_\-.]*\d+"
    r"|[\s_\-.]*\(\d+\)"
    r"|[\s_\-.]+(?:final|draft|copy|updated|new|latest)(?=[\s_\-.]|$)"
)

DORMANT_DAYS = 180
_HASH_CAP_BYTES = 50 * 1024 * 1024  # hash files up to 50 MB for dup detection


@dataclass
class FileRecord:
    path: str
    size_bytes: int
    modified: str
    ext: str
    category: str
    sha256: str
    duplicate_group: str = ""
    revision_group: str = ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalised_stem(path: Path) -> str:
    stem = _REVISION_TOKENS.sub("", path.stem).strip(" _-.").lower()
    return stem or path.stem.lower()


def build_inventory(ub_root: Path, exclude: list[Path] | None = None, today: date | None = None) -> dict:
    ub_root = Path(ub_root)
    excluded = [Path(e).resolve() for e in (exclude or [])]
    today = today or datetime.now(timezone.utc).date()

    records: list[FileRecord] = []
    folder_latest: dict[Path, date] = {}

    for path in sorted(ub_root.rglob("*")):
        if any(path.resolve().is_relative_to(e) for e in excluded):
            continue
        if not path.is_file():
            continue
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        ext = path.suffix.lower()
        digest = _sha256(path) if stat.st_size <= _HASH_CAP_BYTES else f"size:{stat.st_size}"
        records.append(
            FileRecord(
                # POSIX form always: file-inventory.csv is a deliverable and
                # a record, and a path that changes shape with the operating
                # system makes two runs of the same tree incomparable.
                path=path.relative_to(ub_root).as_posix(),
                size_bytes=stat.st_size,
                modified=mtime.date().isoformat(),
                ext=ext,
                category=_EXT_TO_CATEGORY.get(ext, "other"),
                sha256=digest,
            )
        )
        folder = path.parent
        d = mtime.date()
        if folder not in folder_latest or folder_latest[folder] < d:
            folder_latest[folder] = d

    # Duplicates: identical content hash appearing more than once.
    by_hash: dict[str, list[FileRecord]] = defaultdict(list)
    for r in records:
        if not r.sha256.startswith("size:"):
            by_hash[r.sha256].append(r)
    for digest, group in by_hash.items():
        if len(group) > 1:
            for r in group:
                r.duplicate_group = digest[:12]

    # Competing revisions: same folder + normalised stem + ext, different
    # content. These are AMBIGUOUS — CEO DECISION items in Stage C terms.
    by_stem: dict[tuple, list[FileRecord]] = defaultdict(list)
    for r in records:
        key = (str(Path(r.path).parent), _normalised_stem(Path(r.path)), r.ext)
        by_stem[key].append(r)
    revision_conflicts: list[list[str]] = []
    for key, group in by_stem.items():
        if len(group) > 1 and len({r.sha256 for r in group}) > 1:
            group_id = f"{key[1]}{key[2]}"
            for r in group:
                r.revision_group = group_id
            revision_conflicts.append(sorted(r.path for r in group))

    dormant = sorted(
        folder.relative_to(ub_root).as_posix()
        for folder, latest in folder_latest.items()
        if (today - latest).days >= DORMANT_DAYS
    )

    return {
        "records": records,
        "duplicate_groups": sum(1 for g in by_hash.values() if len(g) > 1),
        "revision_conflicts": sorted(revision_conflicts),
        "dormant_folders": dormant,
    }


def run_stage_b(ub_root: Path, out_dir: Path, exclude: list[Path] | None = None, today: date | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = build_inventory(ub_root, exclude=exclude, today=today)

    with (out_dir / "file-inventory.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "path", "size_bytes", "modified", "ext", "category",
                "sha256", "duplicate_group", "revision_group",
            ],
        )
        writer.writeheader()
        for r in result["records"]:
            writer.writerow(asdict(r))

    return {
        "files": len(result["records"]),
        "duplicate_groups": result["duplicate_groups"],
        "revision_conflicts": result["revision_conflicts"],
        "dormant_folders": result["dormant_folders"],
    }
