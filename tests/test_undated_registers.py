"""Register rows that alert on nothing — §2.2, §1.1.

    "A lapsed prequalification produces silent revenue decline: you stop
     being invited rather than being rejected."

That failure is invisible by construction. The register makes it visible
only if a row with no expiry date is reported as such — because an empty
horizon from twelve undated accreditations looks exactly like an empty
horizon from a company with nothing due, and one of those is fine.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from control import registers as reg
from control.db import init_db

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "control.db")
    yield c
    c.close()


def test_an_undated_accreditation_produces_no_deadline(conn):
    """Confirming the hazard before testing the mitigation."""
    reg.add_accreditation(conn, client="Enova", status="UNKNOWN",
                          renewal_owner="donia@ubcsis.com", source="BACKFILL")
    assert reg.horizon(conn, date(2026, 8, 16), days=3650) == []


def test_but_it_is_reported_as_alerting_on_nothing(conn):
    reg.add_accreditation(conn, client="Enova", status="UNKNOWN",
                          renewal_owner="donia@ubcsis.com", source="BACKFILL")
    rows = reg.undated(conn)
    assert len(rows) == 1
    assert rows[0]["kind"] == "accreditation"
    assert rows[0]["ref"] == "Enova"
    assert rows[0]["missing"] == "expiry_date"
    assert rows[0]["owner"] == "donia@ubcsis.com"
    assert rows[0]["status"] == "UNKNOWN"


def test_a_dated_row_is_not_reported_as_undated(conn):
    reg.add_accreditation(conn, client="Enova", status="ACTIVE",
                          expiry_date="2027-01-31",
                          renewal_owner="donia@ubcsis.com", source="BACKFILL")
    assert reg.undated(conn) == []
    assert len(reg.horizon(conn, date(2026, 11, 1), days=120)) == 1


def test_undated_covers_every_register_that_can_go_silent(conn):
    reg.add_accreditation(conn, client="Enova", status="UNKNOWN",
                          source="BACKFILL")
    reg.add_tender(conn, tender_ref="T-1", client="Enova", status="OPEN",
                   owner="donia@ubcsis.com", source="BACKFILL")
    reg.add_quotation(conn, quote_ref="Q-1", direction="ISSUED",
                      counterparty="Enova", status="OPEN",
                      owner="donia@ubcsis.com", source="BACKFILL")
    kinds = {row["kind"] for row in reg.undated(conn)}
    assert kinds == {"accreditation", "tender", "quotation"}


def test_an_instrument_cannot_be_registered_without_an_expiry(conn):
    """The schema forbids the silent case here rather than reporting it.

    A guarantee with no expiry date is not a register row at all, so
    there is nothing for `undated` to find — the residual risk is a
    guarantee never entered, which Stage C surfaces from documents.
    """
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        reg.add_instrument(conn, instrument_ref="LG-1", instrument_type="LG",
                           status="ACTIVE", owner="accounts@ubcsis.com",
                           source="BACKFILL")


def test_an_unassigned_owner_is_still_reported(conn):
    """A row with no date and no owner is the worst case, not a skip."""
    reg.add_accreditation(conn, client="Orphan", status="UNKNOWN",
                          source="BACKFILL")
    assert reg.undated(conn)[0]["owner"] == ""


def test_append_only_correction_supersedes_the_undated_row(conn):
    """Filling the date later must clear the finding, not duplicate it."""
    first = reg.add_accreditation(conn, client="Enova", status="UNKNOWN",
                                  source="BACKFILL")
    assert len(reg.undated(conn)) == 1
    reg.add_accreditation(conn, client="Enova", status="ACTIVE",
                          expiry_date="2027-03-01",
                          renewal_owner="donia@ubcsis.com", source="LIVE",
                          correction_of=first,
                          correction_reason="prequalification file located")
    assert reg.undated(conn) == []


# ---- the seed file ---------------------------------------------------

def test_the_seed_loads_and_every_row_is_visibly_undated(conn):
    data = yaml.safe_load(
        (REPO_CONFIG / "accreditations-seed.yaml").read_text(encoding="utf-8"))
    for row in data["accreditations"]:
        reg.add_accreditation(conn, **row)

    undated = reg.undated(conn)
    assert len(undated) == 12
    assert all(row["owner"] for row in undated), "every row needs an owner"
    assert reg.horizon(conn, date(2026, 8, 16), days=3650) == []


def test_the_seed_uses_unknown_rather_than_pending():
    """Pending means an application is running. Unknown means nobody
    has checked. Conflating them hides the case §2.2 warns about."""
    data = yaml.safe_load(
        (REPO_CONFIG / "accreditations-seed.yaml").read_text(encoding="utf-8"))
    assert {row["status"] for row in data["accreditations"]} == {"UNKNOWN"}


def test_the_seed_covers_the_confirmed_client_list():
    seed = yaml.safe_load(
        (REPO_CONFIG / "accreditations-seed.yaml").read_text(encoding="utf-8"))
    clients = yaml.safe_load(
        (REPO_CONFIG / "confidential.yaml").read_text(encoding="utf-8"))
    seeded = {row["client"] for row in seed["accreditations"]}
    named = {c["name"] for c in clients["confidential_clients"]}
    missing = named - seeded
    assert not missing, f"clients with no accreditation row: {missing}"


def test_the_seed_is_marked_as_backfill_not_live():
    """These come from Phase 0 evidence, not a received document (§5.2)."""
    data = yaml.safe_load(
        (REPO_CONFIG / "accreditations-seed.yaml").read_text(encoding="utf-8"))
    assert {row["source"] for row in data["accreditations"]} == {"BACKFILL"}


def test_the_charter_clients_that_went_quiet_are_flagged_to_check_first():
    """KNAUF, Canal Sugar, Sukari and Air Liquide barely appear in the
    scanned mail. Not proof of a lapse — but the exact shape of one."""
    data = yaml.safe_load(
        (REPO_CONFIG / "accreditations-seed.yaml").read_text(encoding="utf-8"))
    rows = {row["client"]: row["documents_required"]
            for row in data["accreditations"]}
    for client in ("KNAUF", "Canal Sugar", "Sukari Gold Mines", "Air Liquide"):
        assert "CHECK FIRST" in rows[client]
