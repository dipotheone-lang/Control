

# ---- the gate under a narrowed scope ----------------------------------

def test_rows_the_running_scope_does_not_need_are_named(tmp_path):
    """The gate read "5 open, 1 blocked" on the day the system launched,
    at a moment when the running scope required none of the six. A gate
    that overstates what is blocking is a gate people stop reading."""
    from control.phase1 import BLOCKED, OPEN, GateItem, console_lines

    items = [
        GateItem("usage_policy", "Usage policy circulated", OPEN,
                 "0 of 11", "Mohamed Ali, HR", "§12.4"),
        GateItem("golden_set", "Golden set built and passing", BLOCKED,
                 "no cases", "Control", "§13.1"),
        GateItem("statutory_calendar", "Statutory calendar verified", OPEN,
                 "13 rules, none verified", "tax advisor", "§2.1"),
    ]
    lines = console_lines([], items, "STATUTORY_ONLY")
    text = "\n".join(lines)

    assert "2 of them not required by this scope" in text
    assert "evaluates none" in text
    assert "judges verdicts" in text
    # O-03 is required by this scope and must NOT be excused.
    after_calendar = text.split("Statutory calendar verified")[1]
    assert "NOT REQUIRED" not in after_calendar.split("[")[0]


def test_a_row_the_scope_excuses_is_still_open(tmp_path):
    """It is not closed and must never read as closed — that would be
    the gate lying about a §12 pre-condition, which is the one thing it
    exists not to do."""
    from control.phase1 import OPEN, GateItem, console_lines

    items = [GateItem("pdpl", "PDPL basis documented", OPEN,
                      "not issued", "Ahmed Diab, CEO", "§12.2")]
    text = "\n".join(console_lines([], items, "STATUTORY_ONLY"))

    assert "[OPEN]" in text
    assert "1 closed" not in text
    assert "still what widening would have to close" in text


def test_the_full_scope_excuses_nothing(tmp_path):
    from control.phase1 import OPEN, GateItem, console_lines

    items = [GateItem("usage_policy", "Usage policy circulated", OPEN,
                      "0 of 11", "Mohamed Ali, HR", "§12.4")]
    text = "\n".join(console_lines([], items, "FULL"))

    assert "NOT REQUIRED" not in text
    assert "not required by this scope" not in text
