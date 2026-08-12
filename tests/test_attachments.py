import io
import zipfile
from datetime import datetime

import openpyxl
import pytest

from control.attachments import (
    build_submission_doc,
    extract_xlsx_fields,
    quarantine,
    validate_attachment,
)


def _xlsx_bytes(cells: dict[str, object], sheet: str = "Sheet1") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for ref, value in cells.items():
        ws[ref] = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _with_vba(xlsx: bytes) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(xlsx))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name in src.namelist():
            z.writestr(name, src.read(name))
        z.writestr("xl/vbaProject.bin", b"\x00macro")
    return out.getvalue()


def test_macro_extensions_refused():
    for ext in (".xlsm", ".xlsb", ".docm"):
        v = validate_attachment(f"report{ext}", b"PK\x03\x04data")
        assert not v.ok and "macro" in v.reason


def test_executables_refused_even_with_double_extension():
    v = validate_attachment("report.xlsx.exe", b"MZ\x90\x00")
    assert not v.ok and "executable" in v.reason


def test_allowlist_and_size_cap():
    assert not validate_attachment("notes.rar", b"Rar!").ok
    v = validate_attachment("big.csv", b"x" * 101, size_cap=100)
    assert not v.ok and "size" in v.reason


def test_content_sniffing_catches_renamed_binary():
    v = validate_attachment("invoice.xlsx", b"MZ\x90\x00 not a zip")
    assert not v.ok and "does not match" in v.reason
    assert not validate_attachment("scan.pdf", b"PK\x03\x04").ok


def test_macro_workbook_renamed_xlsx_caught():
    poisoned = _with_vba(_xlsx_bytes({"A1": 1}))
    v = validate_attachment("harmless.xlsx", poisoned)
    assert not v.ok and "VBA" in v.reason


def test_valid_xlsx_passes_and_extracts():
    content = _xlsx_bytes({"B2": 100.0, "B10": 6.0})
    assert validate_attachment("FRM-WPR_w32.xlsx", content).ok
    fields = extract_xlsx_fields(content, {"B2": "Sheet1!B2", "B10": "Sheet1!B10"})
    assert fields == {"B2": 100.0, "B10": 6.0}


def test_quarantine_writes_file_and_reason(tmp_path):
    target = quarantine("bad.exe", b"MZ", "executable format (§5.4)", tmp_path / "q")
    assert target.exists()
    reason = target.with_suffix(target.suffix + ".reason.txt").read_text(encoding="utf-8")
    assert "§5.4" in reason


def test_confidential_never_extracted():
    content = _xlsx_bytes({"B2": 999.0})
    doc = build_submission_doc(
        "SIEMENS-progress.xlsx", content, datetime(2026, 8, 13, 9, 0),
        mapping={"B2": "Sheet1!B2"}, confidential=True,
    )
    assert doc.confidential
    assert doc.fields == {}          # §12.1.2: body never opened
    assert doc.attachment_name == "SIEMENS-progress.xlsx"


def test_corrupt_content_becomes_unreadable():
    doc = build_submission_doc(
        "FRM-WPR.xlsx", b"PK\x03\x04 corrupt", datetime(2026, 8, 13, 9, 0),
        mapping={"B2": "Sheet1!B2"},
    )
    assert doc.unreadable              # §5.5: manual review, never a guess


def test_missing_attachment_doc():
    doc = build_submission_doc("x", None, datetime(2026, 8, 13, 9, 0))
    assert doc.attachment_name is None
