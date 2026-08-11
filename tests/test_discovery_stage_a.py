import json
import mailbox

from control.discovery.stage_a import find_mail_archives, run_stage_a

EML = b"""From: Donia Ali <donia@ubcsis.com>
To: control@ubcsis.com
Cc: info@ubcsis.com
Subject: RFQ 2026-114 - Canal Sugar piping package
Date: Sun, 09 Aug 2026 10:15:00 +0300
Message-ID: <rfq114@ubcsis.com>
Content-Type: multipart/mixed; boundary="B"

--B
Content-Type: text/plain

Please find attached.
--B
Content-Type: application/pdf
Content-Disposition: attachment; filename="RFQ-114-BOQ.pdf"

JVBERi0=
--B--
"""


def _make_tree(tmp_path):
    root = tmp_path / "UB"
    (root / "mail").mkdir(parents=True)
    (root / "mail" / "rfq114.eml").write_bytes(EML)
    box = mailbox.mbox(str(root / "mail" / "old.mbox"))
    for i in range(2):
        m = mailbox.mboxMessage()
        m["From"] = "hadeer@ubcsis.com"
        m["To"] = "control@ubcsis.com"
        m["Subject"] = f"Trial balance {i}"
        m.set_payload("body")
        box.add(m)
    box.close()
    (root / "mail" / "archive.pst").write_bytes(b"\x21BDN not a real pst")
    (root / "mail" / "broken.eml").write_bytes(b"\x00\x01\x02 not mail at all")
    return root


def test_find_and_parse(tmp_path):
    root = _make_tree(tmp_path)
    out = tmp_path / "discovery"
    summary = run_stage_a([root], out)

    assert summary["archives_found"] == 4
    # eml + mbox parsed; pst indexed-not-parsed; broken.eml unparseable
    assert summary["archives_parsed"] == 2
    assert summary["messages_indexed"] == 3
    assert len(summary["limitations"]) == 2
    assert any("libpff" in l for l in summary["limitations"])

    messages = [
        json.loads(line)
        for line in (out / "mail-messages.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    rfq = next(m for m in messages if "RFQ 2026-114" in m["subject"])
    assert rfq["sender"].endswith("<donia@ubcsis.com>")
    assert rfq["attachments"] == ["RFQ-114-BOQ.pdf"]
    assert (out / "mail-archive-index.csv").exists()


def test_sources_untouched(tmp_path):
    root = _make_tree(tmp_path)
    before = {p: p.read_bytes() for p in (root / "mail").iterdir()}
    run_stage_a([root], tmp_path / "discovery")
    after = {p: p.read_bytes() for p in (root / "mail").iterdir()}
    assert before == after


def test_ost_notes_outlook_lock(tmp_path):
    root = tmp_path / "UB"
    root.mkdir()
    (root / "cache.ost").write_bytes(b"xx")
    records = find_mail_archives([root])
    from control.discovery.stage_a import parse_archive

    parse_archive(records[0], tmp_path / "work")
    assert "Outlook" in records[0].reason
