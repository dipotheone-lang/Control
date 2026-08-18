"""Config drift — a decision that never reached the machine.

`bootstrap` never overwrites a live config file, and that is right: the
file carries decisions someone made, and a template would discard them.
But it reported only a count of files kept, never that a copy was
BEHIND. So a machine set up before a decision runs on the configuration
from before it, forever, with nothing saying so.

That is not hypothetical. The CEO confirmed five further clients as
confidential on 16-Aug-2026; a CONTROL_ROOT created before that ran with
seven, and the live `contracts` run printed "confidential clients: 7"
with nothing to indicate anything was missing. Five clients had less
protection than had been decided (§12.1.1).

The rules the fix has to respect: report only what the template gained,
never what the live file has extra — extra is where decisions live —
and add only list entries, never whole keys, because an absent key may
be absent on purpose.
"""

import shutil
from pathlib import Path

import pytest
import yaml

from control.bootstrap import (
    adopt_drift, bootstrap, config_drift, render_drift,
)

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def machine(tmp_path):
    """A CONTROL_ROOT set up from an older template set."""
    template = tmp_path / "old-templates"
    shutil.copytree(REPO_CONFIG, template)

    data = yaml.safe_load(
        (template / "confidential.yaml").read_text(encoding="utf-8"))
    # As it stood before the 16-Aug additions.
    data["confidential_clients"] = [
        c for c in data["confidential_clients"]
        if c["name"] in {"Siemens Energy", "Saint-Gobain", "KNAUF",
                         "Galaxy Chemicals", "Canal Sugar",
                         "Sukari Gold Mines", "Air Liquide"}]
    (template / "confidential.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8")

    control_root = tmp_path / "CONTROL"
    bootstrap(control_root, template)
    return control_root


# ---- detection ---------------------------------------------------------

def test_a_client_added_after_setup_is_reported(machine):
    drift = config_drift(machine, REPO_CONFIG)
    joined = " ".join(drift)
    assert "confidential.yaml" in joined
    assert "confidential_clients" in joined
    for name in ("Enova", "Suez Steel", "Lafarge", "IVL Dhunseri",
                 "Fertiglobe"):
        assert name in joined


def test_a_matching_config_reports_nothing(tmp_path):
    control_root = tmp_path / "CONTROL"
    bootstrap(control_root, REPO_CONFIG)
    assert config_drift(control_root, REPO_CONFIG) == []


def test_local_extras_are_never_reported(machine):
    """Extra is where decisions live. Reporting it would invite someone
    to 'fix' their own config back to the template."""
    path = machine / "config" / "confidential.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["confidential_clients"].append({"name": "A Client Only We Know"})
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    assert not any("A Client Only We Know" in line
                   for line in config_drift(machine, REPO_CONFIG))


def test_a_new_config_key_is_reported_by_name(machine):
    path = machine / "config" / "materiality.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    removed = data.pop("ceo_flag_budget_per_week", None)
    assert removed is not None, "fixture assumption: the key exists upstream"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    drift = config_drift(machine, REPO_CONFIG)
    assert any("ceo_flag_budget_per_week" in line for line in drift)


def test_an_unparseable_file_is_reported_not_crashed(machine):
    (machine / "config" / "sla.yaml").write_text("{{ not yaml",
                                                 encoding="utf-8")
    assert any("sla.yaml" in line and "could not be compared" in line
               for line in config_drift(machine, REPO_CONFIG))


def test_the_message_says_what_it_costs(machine):
    lines = render_drift(config_drift(machine, REPO_CONFIG))
    joined = " ".join(lines)
    assert "never overwritten" in joined
    assert "less protection than was decided" in joined


# ---- adoption ----------------------------------------------------------

def test_adopting_adds_the_missing_clients(machine):
    added = adopt_drift(machine, REPO_CONFIG)
    assert any("Enova" in line for line in added)

    data = yaml.safe_load(
        (machine / "config" / "confidential.yaml").read_text(encoding="utf-8"))
    names = {c["name"] for c in data["confidential_clients"]}
    assert {"Enova", "Suez Steel", "Lafarge", "IVL Dhunseri",
            "Fertiglobe"} <= names


def test_adopting_never_removes_or_reorders_what_was_there(machine):
    path = machine / "config" / "confidential.yaml"
    before = yaml.safe_load(path.read_text(encoding="utf-8"))
    original = [c["name"] for c in before["confidential_clients"]]

    adopt_drift(machine, REPO_CONFIG)

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    names = [c["name"] for c in after["confidential_clients"]]
    assert names[:len(original)] == original, "existing entries moved"


def test_a_local_only_entry_survives_adoption(machine):
    path = machine / "config" / "confidential.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["confidential_clients"].append({"name": "Local Decision Client"})
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    adopt_drift(machine, REPO_CONFIG)

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert any(c["name"] == "Local Decision Client"
               for c in after["confidential_clients"])


def test_adopting_does_not_add_whole_keys(machine):
    """An absent key may be absent on purpose, and adding one silently
    would be the system deciding something that belongs to a human."""
    path = machine / "config" / "materiality.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.pop("ceo_flag_budget_per_week", None)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    adopt_drift(machine, REPO_CONFIG)

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "ceo_flag_budget_per_week" not in after
    # ...and it is still reported, so it cannot be lost silently.
    assert any("ceo_flag_budget_per_week" in line
               for line in config_drift(machine, REPO_CONFIG))


def test_adopting_twice_changes_nothing_the_second_time(machine):
    adopt_drift(machine, REPO_CONFIG)
    assert adopt_drift(machine, REPO_CONFIG) == []


# ---- through the CLI ---------------------------------------------------

def test_init_reports_the_drift_and_offers_the_fix(machine, capsys):
    from control.__main__ import main

    main(["init", "--control-root", str(machine)])
    out = capsys.readouterr().out
    assert "CONFIG BEHIND THE TEMPLATES" in out
    assert "Enova" in out
    assert "--adopt" in out


def test_init_adopt_applies_it(machine, capsys):
    from control.__main__ import main

    main(["init", "--control-root", str(machine), "--adopt"])
    out = capsys.readouterr().out
    assert "adopted" in out
    assert "+ confidential.yaml" in out

    assert not any("confidential_clients" in line
                   for line in config_drift(machine, REPO_CONFIG))


# ---- adopting one named key -------------------------------------------

def test_a_named_key_is_copied_because_a_human_named_it(machine):
    from control.bootstrap import adopt_key

    path = machine / "config" / "authority.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.pop("interim", None)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    adopt_key(machine, REPO_CONFIG, "authority.yaml:interim")

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["interim"]["decision"] == "D-06"
    assert str(after["interim"]["review_due"]) == "2026-09-16"


def test_an_existing_key_is_never_replaced(machine):
    """This adds what is missing. Replacing what is there would discard
    a decision, which is the thing the no-overwrite rule protects."""
    from control import HaltError
    from control.bootstrap import adopt_key

    path = machine / "config" / "authority.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["interim"] = {"active": False, "note": "our own wording"}
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    with pytest.raises(HaltError) as e:
        adopt_key(machine, REPO_CONFIG, "authority.yaml:interim")
    assert "already has" in str(e.value)

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["interim"]["note"] == "our own wording"


def test_a_malformed_or_unknown_spec_is_refused(machine):
    from control import HaltError
    from control.bootstrap import adopt_key

    for spec, expect in (("authority.yaml", "file.yaml:key"),
                         ("nope.yaml:x", "not one of the config files"),
                         ("authority.yaml:nosuchkey", "no key")):
        with pytest.raises(HaltError) as e:
            adopt_key(machine, REPO_CONFIG, spec)
        assert expect in str(e.value)


def test_the_cli_adopts_named_keys_and_says_so(machine, capsys):
    from control.__main__ import main

    for name, key in (("authority.yaml", "interim"),
                      ("materiality.yaml", "ceo_flag_budget")):
        path = machine / "config" / name
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data.pop(key, None)
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8")

    code = main(["init", "--control-root", str(machine),
                 "--adopt-key", "authority.yaml:interim",
                 "--adopt-key", "materiality.yaml:ceo_flag_budget"])
    assert code == 0
    out = capsys.readouterr().out
    assert "authority.yaml: interim added" in out
    assert "materiality.yaml: ceo_flag_budget added" in out


def test_the_d06_review_is_chased_once_the_key_is_there(machine):
    """The point of the key: without it the 16-Sep review never fires."""
    from datetime import date

    from control.bootstrap import adopt_key
    from control.report import interim_reviews_due

    path = machine / "config" / "authority.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.pop("interim", None)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    assert interim_reviews_due(machine / "config", date(2026, 9, 20)) == []

    adopt_key(machine, REPO_CONFIG, "authority.yaml:interim")

    due = interim_reviews_due(machine / "config", date(2026, 9, 20))
    assert due and "O-02" in due[0]
