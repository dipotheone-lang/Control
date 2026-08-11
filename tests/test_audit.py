import json

from control.audit import AuditLog


def test_chain_appends_and_verifies(tmp_path):
    log = AuditLog(tmp_path)
    log.append("startup", {"run_mode": "DISCOVERY"})
    log.append("classify", {"message": "abc", "as": "EXTERNAL_INBOUND"})
    ok, detail = log.verify()
    assert ok, detail
    assert "2 entries" in detail


def test_chain_survives_reopen(tmp_path):
    AuditLog(tmp_path).append("one", {})
    log2 = AuditLog(tmp_path)
    log2.append("two", {})
    ok, detail = log2.verify()
    assert ok, detail
    assert "2 entries" in detail


def test_tampered_entry_detected(tmp_path):
    log = AuditLog(tmp_path)
    log.append("one", {"amount": 100})
    log.append("two", {})
    path = next(tmp_path.glob("*.jsonl"))
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["data"]["amount"] = 999  # the fraudster edits history
    lines[0] = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, detail = AuditLog(tmp_path).verify()
    assert not ok
    assert "hash mismatch" in detail


def test_truncation_detected(tmp_path):
    log = AuditLog(tmp_path)
    log.append("one", {})
    log.append("two", {})
    log.append("three", {})
    path = next(tmp_path.glob("*.jsonl"))
    lines = path.read_text(encoding="utf-8").splitlines()
    # Drop the middle entry: seq gap must be caught.
    path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    ok, detail = AuditLog(tmp_path).verify()
    assert not ok
