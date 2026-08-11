import os
import time
from datetime import date

from control.discovery.stage_b import build_inventory, run_stage_b


def _make_tree(tmp_path):
    root = tmp_path / "UB"
    (root / "reports").mkdir(parents=True)
    (root / "old-project").mkdir()
    (root / "CONTROL").mkdir()

    # Duplicate content in two places
    (root / "reports" / "boq.xlsx").write_bytes(b"same-bytes")
    (root / "old-project" / "boq-copy.xlsx").write_bytes(b"same-bytes")
    # Competing revisions: same logical name, different content
    (root / "reports" / "progress rev1.docx").write_bytes(b"one")
    (root / "reports" / "progress rev2.docx").write_bytes(b"two")
    # System output that must be excluded
    (root / "CONTROL" / "control.db").write_bytes(b"db")
    # A dormant folder
    old = root / "old-project" / "notes.txt"
    old.write_bytes(b"old")
    stale = time.mktime((2025, 1, 1, 0, 0, 0, 0, 0, 0))
    os.utime(old, (stale, stale))
    os.utime(root / "old-project" / "boq-copy.xlsx", (stale, stale))
    return root


def test_inventory_classification_and_flags(tmp_path):
    root = _make_tree(tmp_path)
    result = build_inventory(root, exclude=[root / "CONTROL"], today=date(2026, 8, 11))
    paths = {r.path for r in result["records"]}

    assert "CONTROL/control.db" not in paths
    assert result["duplicate_groups"] == 1
    dup = [r for r in result["records"] if r.duplicate_group]
    assert len(dup) == 2 and {r.category for r in dup} == {"spreadsheet"}

    assert result["revision_conflicts"] == [
        ["reports/progress rev1.docx", "reports/progress rev2.docx"]
    ]
    assert result["dormant_folders"] == ["old-project"]


def test_csv_written(tmp_path):
    root = _make_tree(tmp_path)
    out = tmp_path / "discovery"
    summary = run_stage_b(root, out, exclude=[root / "CONTROL"], today=date(2026, 8, 11))
    assert summary["files"] == 5
    content = (out / "file-inventory.csv").read_text(encoding="utf-8")
    assert "progress rev1.docx" in content
    assert "control.db" not in content
