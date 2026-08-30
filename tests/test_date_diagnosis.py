"""Why terms carry no date — measured rather than guessed (§1.1).

Two full scans produced 525 terms and 2 dated ones. Two fixes made on
reasoning alone — dates crossing clause boundaries, then clauses severed
by line wraps — were both real defects and neither moved that number. A
third guess is not a method, so this counts what the documents write.
"""

import json

from control.discovery.date_diagnosis import diagnose, render


def cache(tmp_path, entries):
    directory = tmp_path / "stage-c-cache"
    directory.mkdir()
    for index, (text, terms) in enumerate(entries):
        (directory / f"{index}.json").write_text(json.dumps({
            "relative": f"doc{index}.txt", "outcome": "terms",
            "text": text, "terms": terms}), encoding="utf-8")
    return directory


def test_terms_in_documents_with_no_date_are_counted_apart(tmp_path):
    directory = cache(tmp_path, [
        ("Retention: ____%  Payment terms: ____",
         [{"kind": "RETENTION", "found_date": ""},
          {"kind": "PAYMENT_TERMS", "found_date": ""}]),
        ("Performance bond valid until 30 November 2026.",
         [{"kind": "GUARANTEE_EXPIRY", "found_date": "2026-11-30"}]),
    ])
    result = diagnose(directory)
    assert result.terms == 3
    assert result.terms_dated == 1
    # No clause-window change can ever date these two.
    assert result.terms_in_documents_with_no_date == 2
    assert result.terms_undated_in_dated_documents == 0


def test_the_dotted_date_this_diagnostic_found_now_parses(tmp_path):
    """What the measurement was for.

    Over 957 documents it counted 159 occurrences of `NN.NN.NNNN` that no
    pattern parsed — more than every recognised format except
    `NN/NN/NNNN` at 172. `31.12.2027` is a date to every reader in Egypt,
    and each one was a guarantee expiry the register never saw.
    """
    directory = cache(tmp_path, [
        ("Letter of guarantee valid until 31.12.2027.",
         [{"kind": "GUARANTEE_EXPIRY", "found_date": "2027-12-31"}]),
    ])
    result = diagnose(directory)
    assert result.parsed == 1
    assert result.parsed_shapes["NN.NN.NNNN"] == 1
    assert result.unparsed == 0


def test_a_shape_the_engine_still_cannot_parse_is_reported(tmp_path):
    """The diagnostic has to keep working after its own first finding is
    fixed, or the next unreadable format is invisible."""
    directory = cache(tmp_path, [
        ("Guarantee valid until 31 ديسمبر 2027.",
         [{"kind": "GUARANTEE_EXPIRY", "found_date": ""}]),
    ])
    result = diagnose(directory)
    assert result.unparsed == 1
    assert any("ع" in shape for shape in result.unparsed_shapes)


def test_the_value_never_leaves_the_document(tmp_path):
    """The report says what the estate writes without reproducing what
    any document says (§12.1.2). A shape, never a date."""
    directory = cache(tmp_path, [
        ("Guarantee valid until 31.12.2027.",
         [{"kind": "GUARANTEE_EXPIRY", "found_date": ""}]),
    ])
    text = render(diagnose(directory))
    assert "NN.NN.NNNN" in text
    assert "31.12.2027" not in text
    assert "31" not in text.replace("NN", "").replace("§12.1.2", "")


def test_a_confidential_document_is_absent_by_construction(tmp_path):
    """D-14 retains no text for a confidential document, so there is
    nothing here to exclude — it never arrives."""
    directory = tmp_path / "stage-c-cache"
    directory.mkdir()
    (directory / "c.json").write_text(json.dumps({
        "relative": "KNAUF/agreement.pdf", "outcome": "terms", "text": None,
        "d05": True,
        "terms": [{"kind": "GUARANTEE_EXPIRY", "found_date": "2026-11-30"}],
    }), encoding="utf-8")
    result = diagnose(directory)
    assert result.documents == 0
    assert result.terms == 0


def test_an_empty_cache_says_so_rather_than_reporting_zero_problems(tmp_path):
    text = render(diagnose(tmp_path / "nothing"))
    assert "No cached document text to diagnose" in text


def test_a_confidential_contract_is_counted_without_retaining_its_text(tmp_path):
    """The population the whole exception exists for, and the one that
    was invisible.

    957 documents produced 525 terms and two dated ones. The diagnosis
    covered 684 of them, because a client-confidential contract retains
    no text under D-14 — so the 208 read under D-05, the largest
    clients' contracts and the guarantees §2.2 calls the most expensive
    class of miss, could not be measured at all. Their counts are now
    taken while the text is in hand and the text dropped, which is the
    same shape as D-05 itself: keep the derived value, discard the
    clause.
    """
    directory = tmp_path / "stage-c-cache"
    directory.mkdir()
    (directory / "c.json").write_text(json.dumps({
        "relative": "KNAUF/agreement.pdf", "outcome": "terms", "text": None,
        "d05": True, "terms": [], "terms_seen": 7, "terms_dated": 1,
        "date_shapes": {"parsed": {"NN/NN/NNNN": 3},
                        "unparsed": {"NNNN/NN/NN": 12}}}), encoding="utf-8")
    (directory / "o.json").write_text(json.dumps({
        "relative": "7. Suppliers/x.txt", "outcome": "terms",
        "text": "Performance bond valid until 30/11/2026.",
        "terms": [{"kind": "GUARANTEE_EXPIRY", "found_date": "2026-11-30"}]}),
        encoding="utf-8")

    result = diagnose(directory)
    assert result.confidential_documents == 1
    assert result.confidential_terms_seen == 7
    assert result.confidential_terms_dated == 1
    assert result.confidential_unparsed_shapes["NNNN/NN/NN"] == 12
    # And it stays out of the ordinary counts, which answer a different
    # question: whether the readable folders parse.
    assert result.documents == 1
    assert result.terms == 1

    text = render(result)
    assert "1 contract(s) read under D-05" in text
    assert "7 term(s) found in them, 1 dated" in text


def test_the_confidential_section_carries_no_document_content(tmp_path):
    directory = tmp_path / "stage-c-cache"
    directory.mkdir()
    (directory / "c.json").write_text(json.dumps({
        "relative": "KNAUF/agreement.pdf", "outcome": "terms", "text": None,
        "d05": True, "terms": [], "terms_seen": 3, "terms_dated": 0,
        "date_shapes": {"parsed": {}, "unparsed": {"NNNN/NN/NN": 4}}}),
        encoding="utf-8")
    (directory / "o.json").write_text(json.dumps({
        "relative": "x.txt", "outcome": "terms", "text": "bond 30/11/2026",
        "terms": []}), encoding="utf-8")
    text = render(diagnose(directory))
    assert "NNNN/NN/NN" in text
    assert "KNAUF" not in text
