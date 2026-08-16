"""The roster defect — found on the live machine, 16-Aug-2026.

`people.yaml` holds four lists: `people`, `vacancies`, `leavers` and
`special_addresses`. The cycle built its recognised-sender set from
`people` alone.

The consequence was not cosmetic. §13.2 says a sender not in the roster
is never evaluated — it is drafted and flagged as new joiner or
impersonation. `procure@` and `sales@` are vacant posts covered on an
interim basis by Ahmed Hassan, carrying 589 and 166 messages in the
scanned period. Every submission from the two mailboxes he actually
works from would have been refused and flagged.

That is the failure §13.1 says costs the system its authority
permanently, aimed at the person already carrying both vacancies.

The tests below are the regression net, and one of them is the sharp
edge in the other direction: a leaver must NOT be recognised.
"""

from pathlib import Path

import pytest
import yaml

from control.config import deactivated_addresses, known_addresses

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def people():
    return yaml.safe_load((REPO_CONFIG / "people.yaml").read_text(encoding="utf-8"))


# ---- the defect itself ------------------------------------------------

def test_vacant_posts_are_recognised_senders(people):
    """The bug. Both carry live traffic under an interim holder."""
    addresses = known_addresses(people)
    assert "procure@ubcsis.com" in addresses
    assert "sales@ubcsis.com" in addresses


def test_special_addresses_are_recognised(people):
    addresses = known_addresses(people)
    assert "elevate@ubcsis.com" in addresses          # SYSTEM_PEER
    assert "contact.ubcsis@gmail.com" in addresses    # BACKUP_CHANNEL
    assert "cpanel@ubcsis.com" in addresses           # SYSTEM_NOISE


def test_every_roster_person_is_recognised(people):
    addresses = known_addresses(people)
    for entry in people["people"]:
        assert entry["email"].lower() in addresses


def test_reading_only_the_people_key_misses_six_addresses(people):
    """The exact shape of the defect, pinned so it cannot return."""
    old = {p["email"].lower() for p in people["people"]}
    missed = known_addresses(people) - old
    assert missed == {
        "procure@ubcsis.com", "sales@ubcsis.com", "cpanel@ubcsis.com",
        "elevate@ubcsis.com", "contact.ubcsis@gmail.com",
    }


# ---- the sharp edge the other way -------------------------------------

def test_a_leaver_is_not_a_recognised_sender(people):
    """Mail from a departed employee's address IS the §13.2 case.

    Folding leavers back into the roster to be tidy would silence
    exactly the signal that matters.
    """
    addresses = known_addresses(people)
    for email in ("mahmoud.diab@ubcsis.com", "rania@ubcsis.com",
                  "mariam@ubcsis.com", "moustafa@ubcsis.com"):
        assert email not in addresses


def test_leavers_are_still_on_record(people):
    """Not recognised is not the same as not known. §3.3 needs them
    listed so reminders suppress AND log."""
    deactivated = deactivated_addresses(people)
    assert set(deactivated) == {
        "mahmoud.diab@ubcsis.com", "rania@ubcsis.com",
        "mariam@ubcsis.com", "moustafa@ubcsis.com"}


def test_deactivating_in_place_works_too():
    """A human editing the roster should not have to know which of the
    two representations the code prefers."""
    inline = {"people": [{"email": "gone@ubcsis.com", "active": False},
                         {"email": "here@ubcsis.com"}]}
    assert known_addresses(inline) == {"here@ubcsis.com"}
    assert set(deactivated_addresses(inline)) == {"gone@ubcsis.com"}


# ---- the leaver records themselves ------------------------------------

def test_leaver_dates_are_marked_inferred_not_stated(people):
    """The CEO's instruction: use last-seen, marked as inferred. An
    inferred date suppresses a reminder and does nothing else — if one
    ever matters in a labour context, the real date comes from HR."""
    for entry in people["leavers"]:
        assert entry["left_on"] is None
        assert entry["left_on_source"] == "INFERRED_FROM_MAIL"
        assert entry["hr_confirmation_pending"] is True


def test_leaver_names_are_not_invented(people):
    """Only the addresses were observed. A plausible name would be a
    fabrication in a record about a real person (§1.1)."""
    assert all(e["name"] == "NOT PROVIDED" for e in people["leavers"])


def test_cpanel_is_a_system_address_not_a_leaver(people):
    """It was still sending in Aug-2026, including to control@ itself.
    Deactivating it would suppress an address that is legitimately
    active."""
    entry = next(e for e in people["special_addresses"]
                 if e["address"] == "cpanel@ubcsis.com")
    assert entry["type"] == "SYSTEM_NOISE"
    assert "not a person" in entry["rules"]
    assert "cpanel@ubcsis.com" not in deactivated_addresses(people)


# ---- degenerate input -------------------------------------------------

def test_missing_or_empty_config_yields_nothing_without_crashing():
    assert known_addresses(None) == set()
    assert known_addresses({}) == set()
    assert deactivated_addresses(None) == {}


def test_addresses_are_lowercased():
    assert known_addresses(
        {"people": [{"email": "Ahmed@UBCSIS.com"}]}) == {"ahmed@ubcsis.com"}


# ---- the live path ----------------------------------------------------

def test_the_cycle_recognises_a_vacant_post_sender(tmp_path):
    """End to end: a submission from procure@ is classified as internal
    rather than refused as a possible impersonation."""
    import shutil

    from control.classify import Classifier, InboundMessage
    from control.config import load_config

    control_root = tmp_path / "CONTROL"
    (control_root / "config").mkdir(parents=True)
    shutil.copytree(REPO_CONFIG, control_root / "config", dirs_exist_ok=True)
    config = load_config(control_root / "config")

    classifier = Classifier(
        roster_emails=known_addresses(config["people"]),
        obligation_forms={}, confidential_domains=set(), known_domains=set())

    result = classifier.classify(InboundMessage(
        sender="procure@ubcsis.com", to="control@ubcsis.com", cc="",
        subject="Purchase order log", first_line="attached", attachments=[]))
    assert result.category != "SUSPECTED_FRAUD"
    assert not any("not in roster" in flag.lower() for flag in result.flags)
