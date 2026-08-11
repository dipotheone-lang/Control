import pytest

from control import HaltError
from control.states import demotion_target, validate_state


def test_legal_states_pass():
    assert validate_state(0, "DISCOVERY", "OBSERVE").phase == 0
    assert validate_state(3, "LIVE", "PROPOSE").phase == 3
    assert validate_state(4, "LIVE", "ADAPTIVE").phase == 4


def test_illegal_combinations_halt():
    with pytest.raises(HaltError):
        validate_state(3, "LIVE", "ADAPTIVE")      # ADAPTIVE needs level 4+
    with pytest.raises(HaltError):
        validate_state(0, "LIVE", "OBSERVE")       # discovery level can't be LIVE
    with pytest.raises(HaltError):
        validate_state(2, "SUPERVISED", "PROPOSE")  # PROPOSE starts at level 3


def test_demotion_targets_per_trigger():
    assert demotion_target(5, "security_event").level == 2
    assert demotion_target(4, "missed_class_1_2_system_failure").level == 2
    assert demotion_target(4, "dispute_rate").level == 3
    assert demotion_target(3, "failed_self_audit").level == 2
    # Demotion out of level 4+ leaves ADAPTIVE per the state table
    assert demotion_target(4, "dispute_rate").learning_mode == "PROPOSE"
