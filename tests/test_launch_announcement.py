"""The launch announcement — §16, execution order step 6.

§12.4 says the technical build is not the risk and this letter is:
*"Managed openly it becomes infrastructure; managed quietly it becomes
a grievance and people route around it within a week."*

§16 lists six things the announcement must carry. A document with no
test is a document that gets shortened — someone trims the paragraph
about what the system learns because the letter is long, and the one
paragraph that distinguishes a tool from a watcher is gone. These tests
are the reason it cannot be trimmed silently.

The bilingual pair is checked structurally too. §4 makes the Arabic
authoritative and warns that a discrepancy is exploitable in a labour
dispute — so a heading present in one language and absent in the other
is a defect, not a formatting choice.
"""

import re
from pathlib import Path

import pytest

DOC = (Path(__file__).resolve().parent.parent / "docs" / "governance"
       / "LAUNCH-ANNOUNCEMENT.md")


@pytest.fixture(scope="module")
def text():
    return DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def halves(text):
    english = text.split("──────── العربية ────────")[0]
    arabic = text.split("──────── العربية ────────")[1].split(
        "## Notes for Ahmed")[0]
    return english, arabic


def flat(half: str) -> str:
    """Content with the line wrapping taken out.

    Where a sentence breaks across lines is a formatting choice; these
    tests are about what the letter says. Matching raw text would make
    every reflow a test failure and teach the next person to delete the
    assertion rather than fix the letter.

    Blockquote markers go too — the learning-asymmetry rule is quoted,
    so its continuation lines each start with `>` and a naive join puts
    one in the middle of the sentence.
    """
    lines = [line.lstrip("> ").rstrip() for line in half.splitlines()]
    return " ".join(" ".join(lines).split())


# ---- §16's six required points ----------------------------------------

@pytest.mark.parametrize("requirement,english,arabic", [
    ("what it is", "### What it is", "### ما هو"),
    ("what it checks", "### What it checks", "### ما الذي يفحصه"),
    ("what each verdict means",
     "### What each verdict means", "### معنى كل قرار"),
    ("how to dispute", "### How to disagree with it", "### كيفية الاعتراض"),
    ("what it learns and what it can change by itself",
     "### What it learns, and what it can change by itself",
     "### ما الذي يتعلمه، وما الذي يجوز له تغييره بنفسه"),
    ("it audits the system rather than the people",
     "### What it is not", "### ما ليس هو"),
])
def test_every_required_section_is_present_in_both_languages(
        halves, requirement, english, arabic):
    """§16 lists these six. Each one is here because leaving it out
    changes how the system is received, not because the charter likes
    lists."""
    en, ar = halves
    assert english in en, requirement
    assert arabic in ar, requirement


def test_all_five_verdicts_are_explained(halves):
    """A verdict nobody understands produces no correction (§4)."""
    en, ar = halves
    for verdict in ("ACCEPTED", "ACCEPTED WITH OBSERVATIONS",
                    "RETURNED FOR REVISION", "NOT ACCEPTED", "UNREADABLE"):
        assert verdict in en, verdict
    for verdict in ("مقبول", "مقبول مع ملاحظات", "مُعاد للمراجعة",
                    "غير مقبول", "غير مقروء"):
        assert verdict in ar, verdict


def test_both_dispute_markers_appear_in_both_halves(halves):
    """§8.4 accepts either word on the first line, and a reader of
    either language has to know both work."""
    en, ar = halves
    for half in (en, ar):
        assert "DISPUTE" in half
        assert "اعتراض" in half


def test_the_learning_asymmetry_is_stated_as_the_rule_it_is(halves):
    """§14.1's safety spine is the single sentence that distinguishes
    this from a system that can quietly relax its own controls."""
    en, ar = halves
    assert "stricter on its own" in flat(en)
    assert "only become more lenient with my written approval" in flat(en)
    assert "يزيد من صرامته من تلقاء نفسه" in flat(ar)
    assert "بموافقتي الكتابية" in flat(ar)


def test_the_never_learnable_list_is_named_not_summarised(halves):
    """§14.2's "never learnable under any circumstance". A letter that
    said "some things need approval" would be true and useless."""
    en, _ = halves
    for item in ("statutory deadline", "approval limit", "who approves what",
                 "legal or HR rule", "how severe a verdict is",
                 "never sends mail outside the company"):
        assert item in flat(en), item


def test_the_what_i_got_wrong_section_is_promised(halves):
    """§14.6.4 — the section that proves the rest is honest. Promising
    it in the announcement is what makes its absence noticeable."""
    en, ar = halves
    assert "What I got wrong" in flat(en) and "never omitted" in flat(en)
    assert "ما أخطأت فيه" in flat(ar) and "لا يُحذف أبداً" in flat(ar)


# ---- what the letter refuses to imply ---------------------------------

def test_the_sole_basis_prohibition_is_in_the_announcement_too(halves):
    """§12.4.3 puts it in the usage policy. It is repeated here because
    the announcement is the document people actually read, and a
    protection they learn about from a policy annex is one they do not
    know they have."""
    en, ar = halves
    assert "never the sole basis" in flat(en)
    assert "الأساس الوحيد" in flat(ar)


def test_the_blind_spot_is_disclosed_rather_than_glossed(halves):
    """M1 keeps Control on control@. A letter that described the system
    without saying what it cannot see would be describing a bigger
    system than the one being switched on."""
    en, ar = halves
    assert "reads `control@` and nothing else" in flat(en)
    assert "Individual mailboxes are not read at all" in flat(en)
    assert "`control@` فقط" in flat(ar)
    assert "صناديق البريد الشخصية لا تُقرأ" in flat(ar) \
        or "لا تُقرأ صناديق البريد الشخصية" in flat(ar)


def test_repeated_defects_are_promised_as_system_findings(halves):
    """§1.6 and §8.6. This is the sentence that answers "so it is
    keeping a file on me", and it has to be in the letter rather than
    inferred from behaviour six weeks later."""
    en, ar = halves
    assert "not about the person" in flat(en)
    assert "لا على الشخص" in flat(ar)


def test_the_letter_is_from_the_ceo_not_from_control():
    """§16: "from the CEO not from Control". A system announcing itself
    is precisely the thing people are worried about."""
    text = DOC.read_text(encoding="utf-8")
    assert "**Send from:** Ahmed Diab, CEO" in text
    assert "Nothing in this letter was sent by Control and nothing could be" \
        in text


def test_the_conditional_claims_are_flagged_for_the_sender():
    """Three sentences in the letter are true only at a particular
    phase. The one that expires — "reads control@ and nothing else" —
    is the dangerous one: §3.1a says repeating a blind-spot claim that
    no longer holds understates what Control holds about people, which
    is the same failure as overstating it, pointed the other way."""
    text = DOC.read_text(encoding="utf-8")
    notes = flat(text.split("## Notes for Ahmed")[1])
    assert "conditional on where the build is" in notes
    assert "this sentence becomes false" in notes
    assert "At Phase 2 verdicts are drafts" in notes
    assert "dispute path has to be live before this goes out" in notes


# ---- the two halves say the same thing --------------------------------

def test_neither_half_carries_a_section_the_other_lacks(halves):
    """§4: the versions must say exactly the same thing, because the
    Arabic is authoritative and a discrepancy is exploitable in a
    labour dispute."""
    en, ar = halves
    assert len(re.findall(r"^### ", en, re.M)) == \
        len(re.findall(r"^### ", ar, re.M))
    # And the verdict table has the same number of rows in each.
    def rows(half):
        return [l for l in half.splitlines()
                if l.startswith("|") and "---" not in l]
    assert len(rows(en.split("### What each verdict means")[1]
                    .split("### How to disagree")[0])) == \
        len(rows(ar.split("### معنى كل قرار")[1].split("### كيفية")[0]))


def test_the_arabic_is_marked_authoritative(text):
    assert "النص العربي هو النص المعتمد" in text
