"""Attachment security and extraction — charter §5.4, §5.5.

The §5.4 gauntlet, in order, before anything is opened:
1. extension allowlist
2. size cap
3. macros disabled unconditionally — macro-enabled formats are refused
   by extension AND any xlsx/docx container is inspected for an embedded
   vbaProject.bin, so a macro workbook renamed .xlsx still fails
4. content sniffing — the bytes must match the claimed type
5. failure -> quarantine/ with a reason sidecar; the file is copied,
   reported, and never opened

Extraction only ever runs on content that passed the gauntlet, with
openpyxl in read_only/data_only mode (values, never code). A parse
failure is an UNREADABLE submission for manual review (§5.5) — never a
guess. Confidential items (§12.1.2) are never extracted at all: the
SubmissionDoc carries filename metadata only.
"""

import io
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .evaluate import SubmissionDoc

DEFAULT_ALLOWLIST = {".xlsx", ".csv", ".pdf", ".docx", ".jpg", ".jpeg", ".png", ".eml"}
DEFAULT_SIZE_CAP = 25 * 1024 * 1024

# Refused outright: macro-enabled and executable/scriptable formats.
MACRO_EXTENSIONS = {".xlsm", ".xlsb", ".xltm", ".docm", ".dotm", ".pptm"}
EXECUTABLE_EXTENSIONS = {
    ".exe", ".dll", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".vbe",
    ".js", ".jse", ".wsf", ".msi", ".jar", ".hta", ".lnk", ".iso", ".img",
}

_MAGIC = {
    ".xlsx": (b"PK\x03\x04",),
    ".docx": (b"PK\x03\x04",),
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}


@dataclass
class Validation:
    ok: bool
    reason: str = ""


def validate_attachment(
    filename: str,
    content: bytes,
    allowlist: set[str] | None = None,
    size_cap: int = DEFAULT_SIZE_CAP,
) -> Validation:
    ext = Path(filename).suffix.lower()
    allow = allowlist or DEFAULT_ALLOWLIST

    if ext in MACRO_EXTENSIONS:
        return Validation(False, f"macro-enabled format {ext} — macros disabled unconditionally (§5.4)")
    if ext in EXECUTABLE_EXTENSIONS:
        return Validation(False, f"executable/scriptable format {ext} — never executed (§5.4)")
    if ext not in allow:
        return Validation(False, f"extension {ext or '(none)'} not on the allowlist (§5.4)")
    if len(content) > size_cap:
        return Validation(False, f"size {len(content)} exceeds cap {size_cap} (§5.4)")

    magic = _MAGIC.get(ext)
    if magic and not any(content.startswith(m) for m in magic):
        return Validation(False, f"content does not match claimed type {ext} (§5.4)")

    # A macro workbook renamed .xlsx: the container carries vbaProject.bin.
    if ext in (".xlsx", ".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                if any(name.lower().endswith("vbaproject.bin") for name in z.namelist()):
                    return Validation(False, "embedded VBA project — macros disabled unconditionally (§5.4)")
        except zipfile.BadZipFile:
            return Validation(False, f"corrupt container for {ext} (§5.4)")

    return Validation(True)


def quarantine(
    filename: str, content: bytes, reason: str, quarantine_dir: Path
) -> Path:
    """Copy the failed attachment aside with a reason sidecar. The file is
    stored and reported — never opened (§5.4)."""
    quarantine_dir = Path(quarantine_dir)
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    target = quarantine_dir / f"{stamp}_{Path(filename).name}"
    target.write_bytes(content)
    target.with_suffix(target.suffix + ".reason.txt").write_text(reason + "\n", encoding="utf-8")
    return target


# -- extraction (post-validation only) -------------------------------------


def extract_xlsx_fields(content: bytes, mapping: dict[str, str]) -> dict:
    """Extract mapped cells from a validated .xlsx. mapping is
    {field_name: "Sheet1!B2"}. Values only (data_only=True) — formulas'
    cached results, never code, never macros."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        fields: dict = {}
        for field_name, ref in mapping.items():
            sheet_name, _, cell = ref.partition("!")
            if not cell:
                raise ValueError(f"mapping for {field_name!r} must be 'Sheet!Cell', got {ref!r}")
            ws = wb[sheet_name]
            fields[field_name] = ws[cell].value
        return fields
    finally:
        wb.close()


def build_submission_doc(
    filename: str,
    content: bytes | None,
    received_at: datetime,
    mapping: dict[str, str] | None = None,
    form_code: str | None = None,
    revision: str | None = None,
    confidential: bool = False,
    restricted_basis: str = "",
) -> SubmissionDoc:
    """Produce the SubmissionDoc the evaluation engine consumes.

    Restricted items: the body is never opened — metadata only, and the
    doc is marked so evaluation runs the §12.1.3 reduced set. Two
    decisions land here for opposite reasons: a client NDA (D-01) and
    an individual HSE incident record, which is special-category health
    data (D-17) and never read (D-18). `restricted_basis` carries which,
    because the reduced set is the same but the sentence explaining it
    is not.

    A failed parse is UNREADABLE for manual review (§5.5) — a wrong
    number in a register is worse than no number.
    """
    if confidential or restricted_basis:
        return SubmissionDoc(
            received_at=received_at,
            attachment_name=filename,
            confidential=True,
            restricted_basis=restricted_basis,
        )
    if content is None:
        return SubmissionDoc(received_at=received_at, attachment_name=None)

    fields: dict = {}
    unreadable = False
    if mapping:
        try:
            fields = extract_xlsx_fields(content, mapping)
        except Exception:
            unreadable = True
    return SubmissionDoc(
        received_at=received_at,
        attachment_name=filename,
        form_code=form_code,
        revision=revision,
        fields=fields,
        unreadable=unreadable,
    )
