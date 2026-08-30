"""What each OCR confidence floor would admit — §5.5, §14.4.

The floor sits at 60 because 60 is the default, which §5.5 names as the
wrong reason: it is a governance number to be set from this estate's own
documents. The first live run produced the distribution — 92 of 157
trusted, 55 below, readings from 30.7 to 94.6 — and nothing read it.
"""

import json

from control.discovery.ocr_floor import gather, render


def cache(tmp_path, readings, confidential_every=0):
    directory = tmp_path / "stage-c-cache"
    directory.mkdir()
    for index, confidence in enumerate(readings):
        read = confidence >= 60
        (directory / f"{index}.json").write_text(json.dumps({
            "relative": f"doc{index}.pdf",
            "d05": bool(confidential_every) and index % confidential_every == 0,
            "ocr": {"attempted": True, "read": read, "failed": "",
                    "confidence": confidence}}), encoding="utf-8")
    return directory


def test_each_candidate_floor_is_costed_in_documents(tmp_path):
    evidence = gather(cache(tmp_path, [35.0, 55.0, 62.0, 71.0, 88.0]))
    text = render(evidence)
    assert "5 document(s) OCR'd: 3 trusted, 2 below" in text
    # A floor of 50 admits four of the five; 70 admits two.
    assert "floor  50       4 admitted       1 unreadable" in text
    assert "floor  70       2 admitted       3 unreadable" in text


def test_the_floor_in_force_is_marked(tmp_path):
    text = render(gather(cache(tmp_path, [62.0, 71.0]), floor_in_force=60.0))
    assert "<- in force" in text


def test_below_floor_confidential_documents_are_called_out(tmp_path):
    """D-05 exists for those specifically, and §2.2 puts the most
    expensive class of miss in them. A below-floor count that does not
    separate them understates what is being lost."""
    evidence = gather(cache(tmp_path, [35.0, 40.0, 45.0, 90.0],
                            confidential_every=2))
    assert evidence.below_confidential == 2
    assert "client-confidential" in render(evidence)


def test_it_says_what_it_cannot_tell_you(tmp_path):
    """A document below the floor was never read, so its text was never
    kept. Lowering the floor is a decision to trust readings at a stated
    confidence taken before knowing what they say — and a tool that
    implied otherwise would be recommending, not reporting."""
    text = " ".join(render(gather(cache(tmp_path, [50.0, 80.0]))).split())
    assert "WHAT THIS DOES NOT TELL YOU" in text
    assert "never read, so its text was never kept" in text


def test_it_states_the_rule_that_does_not_move(tmp_path):
    # Normalised: the report is wrapped for a terminal, so a sentence
    # that matters can sit across two lines.
    text = " ".join(render(gather(cache(tmp_path, [50.0, 80.0]))).split())
    assert "§14.4" in text
    assert "never lowered by learning" in text
    assert "Nothing here changes a setting" in text


def test_no_readings_says_so_rather_than_reporting_a_clean_estate(tmp_path):
    assert "No OCR readings in the cache" in render(gather(tmp_path / "none"))


def test_a_failed_document_is_not_counted_as_a_reading(tmp_path):
    """A failure is not a low confidence. Averaging it in would move the
    distribution the floor is being chosen from."""
    directory = tmp_path / "stage-c-cache"
    directory.mkdir()
    (directory / "a.json").write_text(json.dumps({
        "ocr": {"attempted": True, "read": False, "failed": "engine crashed",
                "confidence": 0.0}}), encoding="utf-8")
    (directory / "b.json").write_text(json.dumps({
        "ocr": {"attempted": True, "read": True, "failed": "",
                "confidence": 82.0}}), encoding="utf-8")
    evidence = gather(directory)
    assert evidence.failed == 1
    assert evidence.confidences == [82.0]
