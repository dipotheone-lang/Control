"""§5.6 order and the §3.1a mailbox gate on the scan commands.

`outlook-scan` and `phase0` are the commands that touch the mailbox
hardest — the full historical sweep — and they went straight to the
Outlook namespace. No state check, no integrity check, no roots check,
no scope check. §5.6 lists those five steps and ends "Only then touch
the mailbox", which is the one order those commands ruled out.

`scope.assert_readable` existed for the gate and had no caller, so
`--mailbox anything@anywhere` was limited only by what the Windows
profile happened to hold. D-08 names that exact hazard as the reason
Graph is required: Outlook COM sees whatever the profile sees, and a
permission the system grants itself is not a control.

The distinction these tests hold is the one §3.1a draws itself: a Phase
0 archive read under DISCOVERY is permitted and recorded; the same read
in any other mode is refused.
"""

from pathlib import Path

import pytest

from control import HaltError
from control.scope import MailboxScope, assert_readable, load_scope_file

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
CONTROL = "control@ubcsis.com"


def option_a() -> MailboxScope:
    return load_scope_file(REPO_CONFIG)


# ---- the gate ----------------------------------------------------------

def test_the_control_mailbox_is_readable_in_every_mode():
    for mode in ("DISCOVERY", "DRY_RUN", "SUPERVISED", "LIVE"):
        assert assert_readable(CONTROL, option_a(), mode) == ""


def test_a_phase_0_archive_read_is_permitted_and_recorded():
    """§3.1a permits exactly this, and limits it in the same sentence."""
    note = assert_readable("ahmed@ubcsis.com", option_a(), "DISCOVERY")
    assert "historical archive" in note
    assert "metadata only" in note
    assert "not authority for live processing" in note


def test_the_same_read_is_refused_once_discovery_is_over():
    for mode in ("DRY_RUN", "SUPERVISED", "LIVE"):
        with pytest.raises(HaltError) as e:
            assert_readable("ahmed@ubcsis.com", option_a(), mode)
        assert "not in the operative mailbox scope" in str(e.value)
        assert f"RUN_MODE={mode}" in str(e.value)


def test_the_refusal_names_why_the_profile_is_not_authority():
    """D-08's reasoning belongs in the message, not only in the charter."""
    with pytest.raises(HaltError) as e:
        assert_readable("sales@ubcsis.com", option_a(), "LIVE")
    assert "Windows profile" in str(e.value)
    assert "D-08" in str(e.value)


def test_a_d07_mailbox_is_still_refused_while_the_decision_is_pending():
    """The decision was taken; it is not in effect (§3.1a)."""
    scope = option_a()
    assert "sales@ubcsis.com" in scope.declared      # decided
    assert "sales@ubcsis.com" not in scope.effective  # not in effect
    with pytest.raises(HaltError):
        assert_readable("sales@ubcsis.com", scope, "SUPERVISED")


def test_a_live_scope_readable_without_a_note():
    scope = MailboxScope(
        option="C", state="LIVE", control_mailbox=CONTROL,
        declared=["sales@ubcsis.com"], open_preconditions=[])
    assert assert_readable("sales@ubcsis.com", scope, "LIVE") == ""


# ---- the commands run startup first -----------------------------------

def test_the_scan_commands_take_the_startup_arguments():
    """They cannot check the state without knowing it."""
    import argparse

    from control.__main__ import main

    # An illegal state must be refused before Outlook is ever dispatched.
    # DISCOVERY with ADAPTIVE is not a row in the §16 table.
    with pytest.raises((SystemExit, HaltError, argparse.ArgumentError)):
        main(["outlook-scan", "--mailbox", CONTROL,
              "--control-root", "/nonexistent", "--ub-root", "/nonexistent",
              "--run-mode", "DISCOVERY", "--learning-mode", "ADAPTIVE"])


def test_an_illegal_state_stops_phase0_before_the_mailbox(tmp_path, capsys):
    """§5.6: state first, mailbox last. A halt here means Outlook was
    never dispatched — which is the whole point of the ordering."""
    from control.__main__ import main

    code = main(["phase0", "--control-root", str(tmp_path),
                 "--ub-root", str(tmp_path),
                 "--run-mode", "LIVE", "--learning-mode", "OBSERVE",
                 "--level", "1"])
    assert code == 2
    # No discovery output: nothing got as far as scanning.
    assert not (tmp_path / "discovery").exists()
