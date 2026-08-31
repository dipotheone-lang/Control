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
    assert "templates gained that your copy has not" in joined
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


def test_adopting_adds_a_key_the_local_copy_lacks(machine):
    """This test used to assert the opposite, on the reasoning that an
    absent key might be absent on purpose.

    That reasoning was wrong in the direction that costs something.
    Adding a key the local file does not have cannot discard a decision
    — there is nothing there to discard — and refusing to add it left a
    real machine running for weeks on a config from before the
    decisions it was missing, with a list of homework instead of a
    working system. What is still refused is a real local value against
    a real template value; that is two decisions disagreeing.
    """
    path = machine / "config" / "materiality.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.pop("ceo_flag_budget_per_week", None)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    adopt_drift(machine, REPO_CONFIG)

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "ceo_flag_budget_per_week" in after
    assert not [line for line in config_drift(machine, REPO_CONFIG)
                if "ceo_flag_budget_per_week" in line]


def test_a_real_local_value_is_never_replaced(machine):
    """Two decisions disagreeing. Control saying which is current would
    be Control deciding, and a local value may be the NEWER one."""
    path = machine / "config" / "materiality.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["ceo_flag_budget_per_week"] = 25
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    adopt_drift(machine, REPO_CONFIG)

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["ceo_flag_budget_per_week"] == 25
    assert any("yours to say" in line
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


# ---- the case this was rebuilt for -------------------------------------

def test_a_placeholder_rule_is_replaced_by_the_real_one(machine):
    """The failure that made the old design worthless in practice.

    A live machine's statutory calendar had `rule: UNVERIFIED — CONFIRM
    WITH ADVISOR` on every row. Additive-only adoption filled in owner,
    preparer, cadence and escalation around each rule and left the rule
    itself untouched — so `parse_due` still refused every one of them,
    zero deadlines alerted, and the report looked exactly as broken as
    before. A placeholder is the absence of a decision, so replacing it
    reverts nothing.
    """
    path = machine / "config" / "statutory-calendar.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for row in data["obligations"]:
        row["rule"] = "UNVERIFIED — CONFIRM WITH ADVISOR"
        row.pop("provenance", None)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    adopt_drift(machine, REPO_CONFIG)

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    vat = next(r for r in after["obligations"] if r["id"] == "STAT-VAT")
    assert vat["rule"] == "end of the following month, -5 working days"
    assert vat["provenance"] == "ceo_stated"


def test_after_adopting_the_calendar_actually_alerts(machine):
    """End to end, and the only measure that matters: does a deadline
    come out of the other end? Adoption that leaves nothing alerting is
    adoption that wasted the user's time."""
    from datetime import date

    from control.loader import build_statutory

    path = machine / "config" / "statutory-calendar.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["obligations"] = [
        {"id": r["id"], "name": r.get("name", r["id"]),
         "rule": "UNVERIFIED — CONFIRM WITH ADVISOR"}
        for r in data["obligations"]]
    data["ceo_stated"] = False
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    before, _ = build_statutory(
        yaml.safe_load(path.read_text(encoding="utf-8")), date(2026, 8, 18))
    assert before == [], "the machine's starting state: nothing alerts"

    adopt_drift(machine, REPO_CONFIG)

    after, _ = build_statutory(
        yaml.safe_load(path.read_text(encoding="utf-8")), date(2026, 8, 18))
    assert {t.item_id for t in after} == {
        "STAT-VAT", "STAT-WHT", "STAT-SOCINS", "STAT-CIT", "STAT-PDPL-REGS",
        "STAT-PAYROLL-REM", "STAT-PAYROLL-RET"}


def test_the_previous_version_is_kept_before_a_rewrite(machine):
    """`safe_dump` does not preserve comments, and a config file may
    carry a paragraph explaining why a value is what it is. Losing that
    quietly is its own version of the failure this module prevents."""
    path = machine / "config" / "statutory-calendar.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["obligations"] = [r for r in data["obligations"]
                           if r["id"] != "STAT-VAT"]
    path.write_text(
        "# a comment that safe_dump will not keep\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    original = path.read_text(encoding="utf-8")

    adopt_drift(machine, REPO_CONFIG)

    kept = list((machine / "config" / ".superseded").glob(
        "statutory-calendar.*.yaml"))
    assert len(kept) == 1
    assert kept[0].read_text(encoding="utf-8") == original
    assert "a comment that safe_dump will not keep" in \
        kept[0].read_text(encoding="utf-8")
    assert "a comment that safe_dump will not keep" not in \
        path.read_text(encoding="utf-8")


def test_a_label_difference_is_not_treated_as_two_decisions(machine):
    """Identity is the `id`; `name` is how the row prints.

    Reporting "Payroll tax" against "Payroll tax — return and
    remittance" as two decisions disagreeing is technically true and
    practically noise — and noise is what turns an adoption step into
    homework nobody does. A wrong label is cosmetic; a wrong `rule` is
    a missed filing, and only the second is protected.
    """
    path = machine / "config" / "statutory-calendar.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for row in data["obligations"]:
        if row["id"] == "STAT-VAT":
            row["name"] = "VAT"
            row["owner"] = "someone.else@ubcsis.com"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    adopt_drift(machine, REPO_CONFIG)

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    row = next(r for r in after["obligations"] if r["id"] == "STAT-VAT")
    assert row["name"] == "VAT return and payment", "the label follows"
    assert row["owner"] == "someone.else@ubcsis.com", \
        "a real decision about who owns it does not"


def test_a_conflict_is_taken_only_when_the_human_names_the_file(machine):
    """The friction this removes is real and the safety it keeps is too.

    Ten conflicts in `people.yaml` all encoded one decision — O-01,
    closed 16-Aug-2026, moving two reporting lines to the CEO. Asking
    for ten hand edits to apply one decision is how the adoption step
    stops being run at all. Naming the file is the human deciding once.
    """
    path = machine / "config" / "people.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for person in data["people"]:
        if person["email"] == "shymaa@ubcsis.com":
            person["reports_to"] = "ghareeb@ubcsis.com"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    # Not named: the conflict stands and is reported.
    adopt_drift(machine, REPO_CONFIG)
    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    shymaa = next(p for p in after["people"]
                  if p["email"] == "shymaa@ubcsis.com")
    assert shymaa["reports_to"] == "ghareeb@ubcsis.com"
    assert any("shymaa" in line for line in config_drift(machine, REPO_CONFIG))

    # Named: taken.
    adopt_drift(machine, REPO_CONFIG, accept_template=["people.yaml"])
    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    shymaa = next(p for p in after["people"]
                  if p["email"] == "shymaa@ubcsis.com")
    assert shymaa["reports_to"] == "ahmed@ubcsis.com"


def test_naming_one_file_does_not_touch_another(machine):
    """Deciding about the roster is not deciding about thresholds."""
    path = machine / "config" / "materiality.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["ceo_flag_budget_per_week"] = 25
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    adopt_drift(machine, REPO_CONFIG, accept_template=["people.yaml"])

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["ceo_flag_budget_per_week"] == 25


def test_accepting_the_template_never_removes_a_local_only_value(machine):
    """Drift is one-directional: a value the local copy holds and the
    template does not was never in question, and taking the template
    side for the conflicts must not quietly become taking the file."""
    path = machine / "config" / "people.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["people"].append({"email": "newjoiner@ubcsis.com", "name": "New",
                           "tier": 1})
    data["local_only_key"] = "kept"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    adopt_drift(machine, REPO_CONFIG, accept_template=["people.yaml"])

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["local_only_key"] == "kept"
    assert any(p["email"] == "newjoiner@ubcsis.com" for p in after["people"])


# ---- removal under an explicit acceptance -----------------------------

def _root_with(tmp_path, live_rows, template_rows, retired=()):
    import yaml

    machine = tmp_path / "CONTROL"
    (machine / "config").mkdir(parents=True)
    templates = tmp_path / "templates"
    templates.mkdir()
    (machine / "config" / "statutory-calendar.yaml").write_text(
        yaml.safe_dump({"obligations": live_rows}), encoding="utf-8")
    body = {"obligations": template_rows}
    if retired:
        body["retired_ids"] = list(retired)
    (templates / "statutory-calendar.yaml").write_text(
        yaml.safe_dump(body), encoding="utf-8")
    return machine, templates


def test_a_superseded_row_is_removed_only_when_the_template_is_accepted(tmp_path):
    """STAT-PAYROLL was split into two rows on 30-Aug-2026. Adoption
    added both and kept the original, leaving three payroll rules where
    the register says two — and the third went on asking a question the
    split had already answered."""
    import yaml

    from control.bootstrap import adopt_drift

    live = [{"id": "STAT-PAYROLL", "rule": "UNVERIFIED — pending"},
            {"id": "STAT-VAT", "rule": "day 20"}]
    template = [{"id": "STAT-PAYROLL-REM", "rule": "end of the following month"},
                {"id": "STAT-PAYROLL-RET", "rule": "end of the month after each quarter"},
                {"id": "STAT-VAT", "rule": "day 20"}]
    machine, templates = _root_with(tmp_path, live, template,
                                    retired=["STAT-PAYROLL"])

    applied = adopt_drift(machine, templates,
                          accept_template=["statutory-calendar.yaml"])

    rows = yaml.safe_load(
        (machine / "config" / "statutory-calendar.yaml").read_text(
            encoding="utf-8"))["obligations"]
    assert {r["id"] for r in rows} == {
        "STAT-PAYROLL-REM", "STAT-PAYROLL-RET", "STAT-VAT"}
    assert any("-= STAT-PAYROLL" in line for line in applied), \
        "a removal that is not named is a decision taken silently"


def test_a_local_only_row_survives_a_plain_adopt(tmp_path):
    """Without the explicit acceptance, adoption stays one-directional.
    A local-only entry is where decisions live, and dropping one would
    discard a decision nobody asked about."""
    import yaml

    from control.bootstrap import adopt_drift

    live = [{"id": "STAT-LOCAL", "rule": "day 3"},
            {"id": "STAT-VAT", "rule": "day 20"}]
    template = [{"id": "STAT-VAT", "rule": "day 20"}]
    machine, templates = _root_with(tmp_path, live, template)

    adopt_drift(machine, templates)

    rows = yaml.safe_load(
        (machine / "config" / "statutory-calendar.yaml").read_text(
            encoding="utf-8"))["obligations"]
    assert {r["id"] for r in rows} == {"STAT-LOCAL", "STAT-VAT"}


def test_the_file_is_kept_before_a_removal_rewrites_it(tmp_path):
    """§1.1 and the module's own rule: safe_dump does not keep comments,
    and a removal is the change most worth being able to undo."""
    from control.bootstrap import adopt_drift

    live = [{"id": "STAT-PAYROLL", "rule": "UNVERIFIED — pending"}]
    template = [{"id": "STAT-PAYROLL-REM", "rule": "day 5"}]
    machine, templates = _root_with(tmp_path, live, template,
                                    retired=["STAT-PAYROLL"])

    adopt_drift(machine, templates,
                accept_template=["statutory-calendar.yaml"])

    kept = list((machine / "config" / ".superseded").glob("*"))
    assert kept, "the previous version was not kept"
    assert "STAT-PAYROLL" in kept[0].read_text(encoding="utf-8")


def test_an_acceptance_reaches_a_file_drift_reports_nothing_about(tmp_path):
    """The bug the first version shipped with.

    A superseded local-only row is invisible to `differences` — drift is
    one-directional — so a file whose ONLY problem is such a row had no
    difference to bring it into the adopt loop. `--accept-template`
    reported "config left untouched" while the stale rule sat in the
    file ahead of its replacement, claiming every document that should
    have matched the new one.
    """
    import yaml

    from control.bootstrap import adopt_drift, config_drift

    live = [{"id": "STAT-PAYROLL", "markers": ["payroll tax"]},
            {"id": "STAT-PAYROLL-REM", "markers": ["payroll tax"]}]
    template = [{"id": "STAT-PAYROLL-REM", "markers": ["payroll tax"]}]
    machine = tmp_path / "CONTROL"
    (machine / "config").mkdir(parents=True)
    templates = tmp_path / "templates"
    templates.mkdir()
    (machine / "config" / "filing-evidence.yaml").write_text(
        yaml.safe_dump({"obligations": live}), encoding="utf-8")
    (templates / "filing-evidence.yaml").write_text(
        yaml.safe_dump({"obligations": template,
                        "retired_ids": ["STAT-PAYROLL"]}), encoding="utf-8")

    # Nothing is missing and nothing conflicts — the only finding is the
    # retirement, which is reported so `doctor` names it and is not
    # adoptable without the explicit acceptance.
    drift = config_drift(machine, templates)
    assert len(drift) == 1, drift
    assert "which the template retires" in drift[0]

    applied = adopt_drift(machine, templates,
                          accept_template=["filing-evidence.yaml"])
    rows = yaml.safe_load(
        (machine / "config" / "filing-evidence.yaml").read_text(
            encoding="utf-8"))["obligations"]
    assert [r["id"] for r in rows] == ["STAT-PAYROLL-REM"]
    assert any("-= STAT-PAYROLL" in line for line in applied)


def test_an_acceptance_with_nothing_to_do_rewrites_nothing(tmp_path):
    """Seeding every accepted file into the loop must not mean rewriting
    it on every run — `safe_dump` strips comments, and a `.superseded/`
    copy per run for no change is noise that hides the real ones."""
    import yaml

    from control.bootstrap import adopt_drift

    rows = [{"id": "STAT-VAT", "markers": ["vat"]}]
    machine = tmp_path / "CONTROL"
    (machine / "config").mkdir(parents=True)
    templates = tmp_path / "templates"
    templates.mkdir()
    body = "# a comment worth keeping\n" + yaml.safe_dump({"obligations": rows})
    for base in (machine / "config", templates):
        (base / "filing-evidence.yaml").write_text(body, encoding="utf-8")

    assert adopt_drift(machine, templates,
                       accept_template=["filing-evidence.yaml"]) == []
    assert not (machine / "config" / ".superseded").exists()
    assert "# a comment worth keeping" in (
        machine / "config" / "filing-evidence.yaml").read_text(encoding="utf-8")


# ---- nested mappings ---------------------------------------------------

def _pair(tmp_path, live_body, template_body, name="distribution.yaml"):
    import yaml

    machine = tmp_path / "CONTROL"
    (machine / "config").mkdir(parents=True)
    templates = tmp_path / "templates"
    templates.mkdir()
    (machine / "config" / name).write_text(
        yaml.safe_dump(live_body), encoding="utf-8")
    (templates / name).write_text(
        yaml.safe_dump(template_body), encoding="utf-8")
    return machine, templates


def test_a_decision_one_level_down_is_reported(tmp_path):
    """The hole this closes, found on the operating machine.

    D-13 narrows the management report to the CEO and COO for Phase 2,
    and distribution.yaml carries it as `management_reports.phase` — one
    level down. A nested dict was compared as a single value, and
    `_is_placeholder` is False for a dict, so the difference was
    invisible. The machine ran with the wider steady-state list while
    drift reported "nothing left differing": the decision was in the
    template and not in force, and the tool built to catch exactly that
    said nothing.
    """
    machine, templates = _pair(
        tmp_path,
        {"management_reports": {"phase": "STEADY_STATE", "format": "xlsx"}},
        {"management_reports": {"phase": "PHASE_2", "format": "xlsx"}})

    drift = config_drift(machine, templates)
    assert len(drift) == 1, drift
    assert "management_reports.phase" in drift[0]
    assert "two decisions" in drift[0]


def test_a_nested_key_the_local_copy_lacks_is_added(tmp_path):
    import yaml

    machine, templates = _pair(
        tmp_path,
        {"management_reports": {"phase": "PHASE_2"}},
        {"management_reports": {"phase": "PHASE_2",
                                "standing_cc": "contact.ubcsis@gmail.com"}})

    applied = adopt_drift(machine, templates)
    assert any("standing_cc" in line for line in applied)
    body = yaml.safe_load(
        (machine / "config" / "distribution.yaml").read_text(encoding="utf-8"))
    assert body["management_reports"]["standing_cc"] == "contact.ubcsis@gmail.com"


def test_a_nested_conflict_needs_the_explicit_acceptance(tmp_path):
    """Same rule at depth as at the top: two real values disagreeing is
    two decisions, and Control saying which is current would be Control
    deciding."""
    import yaml

    live = {"management_reports": {"phase": "STEADY_STATE"}}
    template = {"management_reports": {"phase": "PHASE_2"}}
    machine, templates = _pair(tmp_path, live, template)

    adopt_drift(machine, templates)
    body = yaml.safe_load(
        (machine / "config" / "distribution.yaml").read_text(encoding="utf-8"))
    assert body["management_reports"]["phase"] == "STEADY_STATE"

    adopt_drift(machine, templates, accept_template=["distribution.yaml"])
    body = yaml.safe_load(
        (machine / "config" / "distribution.yaml").read_text(encoding="utf-8"))
    assert body["management_reports"]["phase"] == "PHASE_2"


def test_a_nested_placeholder_is_filled_without_asking(tmp_path):
    import yaml

    machine, templates = _pair(
        tmp_path,
        {"restore_test": {"last_result": None}},
        {"restore_test": {"last_result": "PASS"}}, name="backup.yaml")

    adopt_drift(machine, templates)
    body = yaml.safe_load(
        (machine / "config" / "backup.yaml").read_text(encoding="utf-8"))
    assert body["restore_test"]["last_result"] == "PASS"


def test_every_reported_difference_can_be_closed(tmp_path):
    """A reported-but-unclosable difference is worse than an unreported
    one: it turns the adoption step into homework that never finishes.
    So adoption has to recurse wherever detection does."""
    machine, templates = _pair(
        tmp_path,
        {"a": {"b": {"c": "old", "d": None}}},
        {"a": {"b": {"c": "new", "d": "filled", "e": "added"}}})

    assert config_drift(machine, templates)
    adopt_drift(machine, templates, accept_template=["distribution.yaml"])
    assert config_drift(machine, templates) == []
