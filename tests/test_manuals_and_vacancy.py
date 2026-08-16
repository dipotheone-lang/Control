"""Manual discovery (§6 Stage C) and the vacancy burden (§3.2).

Two things the charter asks for that had no implementation.

C6 asks whether a submission conforms to the manual and §1.2 requires
the clause quoted. With no manuals indexed, C6 cannot honestly return
CONFORMS — so the first job is to find candidates and have a human
confirm which ones actually govern, because a document with "manual" in
its name is a candidate, not an authority.

§3.2 asks for a standing monthly line quantifying both vacancies as
hiring evidence. A structural gap nobody measures is a gap nobody fills.
"""

from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from control.db import init_db
from control.discovery.manuals import (
    competing_revisions, extract_mandates, render_manual_inventory,
    score_candidate,
)
from control.discovery.stage_c import classify_confidential, match_tokens
from control.report import vacancy_burden

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
CLIENTS = ["Air Liquide", "Suez Steel", "IVL Dhunseri", "Enova", "KNAUF",
           "Canal Sugar", "Siemens Energy"]


# ---- folder classification, and the noise it must not make -----------

def test_a_folder_named_for_a_client_makes_its_contents_confidential():
    confidential, reason = classify_confidential(
        Path("Projects/Enova/2026/progress report.xlsx"), CLIENTS, [])
    assert confidential
    assert "folder named for the client" in reason and "Enova" in reason


def test_a_generic_word_from_a_client_name_does_not_match_everything():
    """"Air Liquide" must not confidentialise every air-conditioning file.

    The docstring on classify_confidential warns that noise hides the gap
    it pretends to protect. First-token matching produced exactly that.
    """
    confidential, _ = classify_confidential(
        Path("Maintenance/air conditioning repair schedule.xlsx"), CLIENTS, [])
    assert not confidential


def test_a_generic_word_inside_another_word_does_not_match():
    confidential, _ = classify_confidential(
        Path("Sites/repair log.pdf"), CLIENTS, [])
    assert not confidential


def test_but_the_distinctive_half_of_the_name_still_matches():
    confidential, reason = classify_confidential(
        Path("Clients/Liquide/prequalification.pdf"), CLIENTS, [])
    assert confidential and "Air Liquide" in reason


def test_an_industry_word_does_not_confidentialise_every_supplier():
    """"Suez Steel" must not catch every steel supplier on the drive."""
    confidential, _ = classify_confidential(
        Path("Suppliers/steel prices 2026.xlsx"), CLIENTS, [])
    assert not confidential
    confidential, reason = classify_confidential(
        Path("Clients/Suez Steel/contract.pdf"), CLIENTS, [])
    assert confidential and "Suez Steel" in reason


def test_a_short_client_token_is_not_used_alone():
    """IVL is three characters and would match inside anything."""
    assert "ivl" not in match_tokens("IVL Dhunseri")
    assert "dhunseri" in match_tokens("IVL Dhunseri")
    assert "ivl dhunseri" in match_tokens("IVL Dhunseri")


def test_a_project_mapped_to_a_client_is_confidential():
    confidential, reason = classify_confidential(
        Path("Jobs/PRJ-2214/boq.xlsx"), [], [], ["PRJ-2214"])
    assert confidential and "project mapped" in reason


def test_the_filename_case_is_still_reported_as_a_filename():
    confidential, reason = classify_confidential(
        Path("Quotations/enova quotation.pdf"), CLIENTS, [])
    assert confidential and "filename references" in reason


def test_markings_still_win_regardless_of_client():
    confidential, reason = classify_confidential(
        Path("Misc/restricted pricing.pdf"), [], [])
    assert confidential and "restricted" in reason


# ---- manual scoring ---------------------------------------------------

def test_a_document_that_mandates_scores_above_one_that_mentions():
    manual = score_candidate(
        "QMS/Quality Manual Rev 3.pdf",
        "Table of contents. Clause 4.2.1 The Site Engineer shall submit the "
        "weekly progress report using Form FRM-WPR-01. Approved by: CEO.")
    mention = score_candidate(
        "Reports/weekly progress report.xlsx",
        "Progress this week was satisfactory. See the manual for details.")
    assert manual.score > mention.score
    assert manual.confidence == "HIGH"


def test_the_revision_is_read_from_the_filename():
    candidate = score_candidate("QMS/HSE Manual Rev 2.1.pdf", "")
    assert candidate.revision == "2.1"


def test_an_unread_document_says_so_rather_than_scoring_zero_quietly():
    """A confidential or scanned manual is still a manual (§1.1)."""
    candidate = score_candidate("QMS/Operations Manual.pdf", None)
    assert candidate.readable is False
    assert any("scored on filename only" in r for r in candidate.reasons)
    assert candidate.score > 0


def test_arabic_mandating_language_is_recognised():
    candidate = score_candidate(
        "دليل الجودة.pdf", "يجب على المهندس تقديم التقرير الأسبوعي")
    assert candidate.score >= 5


# ---- competing revisions ---------------------------------------------

def test_competing_revisions_are_grouped_not_resolved():
    """§6: AMBIGUOUS — CEO DECISION. Most-recent-wins is a guess, and a
    verdict against the wrong revision is confident and wrong."""
    conflicts = competing_revisions([
        score_candidate("QMS/Quality Manual Rev 2.pdf", ""),
        score_candidate("QMS/Quality Manual Rev 3.pdf", ""),
        score_candidate("QMS/HSE Manual.pdf", ""),
    ])
    assert len(conflicts) == 1
    paths = next(iter(conflicts.values()))
    assert paths == ["QMS/Quality Manual Rev 2.pdf", "QMS/Quality Manual Rev 3.pdf"]


# ---- clause extraction ------------------------------------------------

def test_mandating_clauses_are_extracted_with_cadence_and_reference():
    clauses = extract_mandates(
        "QMS/Quality Manual.pdf",
        "Clause 4.2.1 The Site Engineer shall submit the weekly progress "
        "report to the Technical Office. Clause 5.1 Records must be "
        "maintained monthly by the storekeeper.")
    assert len(clauses) == 2
    assert clauses[0].cadence == "weekly"
    assert clauses[0].clause_ref == "4.2.1"
    assert clauses[1].cadence == "monthly"


def test_descriptive_text_is_not_read_as_a_mandate():
    assert extract_mandates("x.pdf", "The report was submitted last week.") == []


def test_a_fragment_too_short_to_be_a_clause_is_dropped():
    assert extract_mandates("x.pdf", "He shall report.") == []


# ---- the inventory the CEO confirms ----------------------------------

def test_the_inventory_never_treats_a_candidate_as_authoritative():
    text = render_manual_inventory(
        [score_candidate("QMS/Quality Manual.pdf",
                         "Clause 1.1 The engineer shall submit the daily "
                         "report on the approved form.")],
        expected=12)
    assert "Nothing below has been treated as authoritative" in text
    assert "candidate, not an" in text
    assert "☐" in text                     # a tick box, not a decision


def test_a_shortfall_against_the_charter_count_is_a_question_not_a_claim():
    text = render_manual_inventory([], expected=12)
    assert "12 of the 12 manuals" in text
    assert "not written" in text
    assert "changes what C6" in text


def test_unticked_documents_are_explicitly_not_read_for_clauses():
    text = render_manual_inventory([], expected=12)
    assert "Anything left unticked is not read for clauses" in text


# ---- vacancy burden ---------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "control.db")
    yield c
    c.close()


SINCE = datetime(2026, 7, 16)


def test_no_vacancies_means_no_line(conn):
    assert vacancy_burden(conn, {"people": [], "vacancies": []}, SINCE) == []


def test_the_repo_roster_carries_both_vacancies(conn):
    people = yaml.safe_load((REPO_CONFIG / "people.yaml").read_text(encoding="utf-8"))
    lines = vacancy_burden(conn, people, SINCE)
    assert "2 vacant role(s)" in lines[0]
    assert "Procurement Officer" in lines[0] and "Sales Officer" in lines[0]
    assert "info@ubcsis.com" in lines[0]


def test_an_empty_register_is_not_reported_as_a_light_workload(conn):
    """The distinction §1.1 exists for, applied to a person's workload."""
    people = yaml.safe_load((REPO_CONFIG / "people.yaml").read_text(encoding="utf-8"))
    lines = vacancy_burden(conn, people, SINCE)
    assert any("empty register, not a light workload" in line for line in lines)


def test_volume_is_counted_once_it_exists(conn):
    from control import registers as reg

    reg.add_quotation(conn, quote_ref="Q-1", direction="ISSUED",
                      counterparty="Enova", owner="info@ubcsis.com",
                      status="OPEN", amount=250000.0, currency_code="EGP",
                      source="LIVE")
    people = yaml.safe_load((REPO_CONFIG / "people.yaml").read_text(encoding="utf-8"))
    lines = vacancy_burden(conn, people, SINCE)
    assert any("1 quotation(s) on the register (250,000 EGP)" in line
               for line in lines)


def test_mixed_currencies_are_not_totalled_without_a_basis(conn):
    """§5.2: never total across currencies without a stated basis."""
    from control import registers as reg

    reg.add_quotation(conn, quote_ref="Q-1", direction="ISSUED",
                      counterparty="Enova", owner="info@ubcsis.com",
                      status="OPEN", amount=250000.0, currency_code="EGP",
                      source="LIVE")
    reg.add_quotation(conn, quote_ref="Q-2", direction="ISSUED",
                      counterparty="Lafarge", owner="info@ubcsis.com",
                      status="OPEN", amount=9000.0, currency_code="EUR",
                      fx_rate=54.0, fx_rate_date="2026-08-01", source="LIVE")
    people = yaml.safe_load((REPO_CONFIG / "people.yaml").read_text(encoding="utf-8"))
    lines = vacancy_burden(conn, people, SINCE)
    assert any("not totalled, no stated FX basis" in line for line in lines)


def test_the_line_carries_the_standing_recommendation(conn):
    people = yaml.safe_load((REPO_CONFIG / "people.yaml").read_text(encoding="utf-8"))
    lines = vacancy_burden(conn, people, SINCE)
    assert any("filling procurement first" in line for line in lines)
    assert any("splits cost from price" in line for line in lines)


def test_the_line_states_facts_and_never_characterises_conduct(conn):
    """§1.4 — this counts what passed through one pair of hands. It is
    evidence for a hiring decision, not an allegation about a person."""
    people = yaml.safe_load((REPO_CONFIG / "people.yaml").read_text(encoding="utf-8"))
    body = " ".join(vacancy_burden(conn, people, SINCE)).lower()
    for word in ("breach", "failure", "negligen", "concern", "risk of fraud",
                 "unacceptable"):
        assert word not in body


def test_the_burden_appears_in_the_weekly_report(conn, tmp_path):
    from control.report import weekly_report

    report = weekly_report(
        conn, as_of=date(2026, 8, 20), horizon=[], open_items=[],
        open_decisions=[], control_root=tmp_path, config_dir=REPO_CONFIG)
    assert "VACANCY BURDEN" in report["body"]
