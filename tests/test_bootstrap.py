from pathlib import Path

import pytest

from control import HaltError
from control.bootstrap import CONFIG_FILES, DIRECTORIES, bootstrap, render_result

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


def test_creates_the_full_tree_and_installs_config(tmp_path):
    root = tmp_path / "CONTROL"
    result = bootstrap(root, REPO_CONFIG)

    for relative in DIRECTORIES:
        assert (root / relative).is_dir(), relative
    for name in CONFIG_FILES:
        assert (root / "config" / name).is_file(), name
    assert result.missing_templates == []
    assert result.db_created is True
    assert (root / "data" / "control.db").is_file()


def test_existing_config_is_never_overwritten(tmp_path):
    root = tmp_path / "CONTROL"
    bootstrap(root, REPO_CONFIG)

    # Someone records a real decision in the live config.
    people = root / "config" / "people.yaml"
    people.write_text("people:\n  - email: ahmed@ubcsis.com\n    tier: 4\n"
                      "    confirmed: true   # CEO confirmed 15-Aug-2026\n",
                      encoding="utf-8")
    before = people.read_text(encoding="utf-8")

    result = bootstrap(root, REPO_CONFIG)      # re-run
    assert people.read_text(encoding="utf-8") == before
    assert "people.yaml" in result.kept_config
    assert "people.yaml" not in result.copied_config


def test_rerun_is_idempotent(tmp_path):
    root = tmp_path / "CONTROL"
    bootstrap(root, REPO_CONFIG)
    second = bootstrap(root, REPO_CONFIG)
    assert second.created_dirs == []
    assert second.copied_config == []
    assert second.db_created is False
    assert len(second.kept_config) == len(CONFIG_FILES)


def test_startup_succeeds_against_a_bootstrapped_root(tmp_path):
    """The point of the exercise: a bootstrapped root actually runs."""
    from control.startup import run_startup

    ub_root = tmp_path / "UB"
    root = ub_root / "CONTROL"
    root.mkdir(parents=True)
    bootstrap(root, REPO_CONFIG)

    report = run_startup(root, ub_root, "DISCOVERY", "OBSERVE", 0, "2026-08-15")
    assert report.state.phase == 0
    ok, _ = report.audit.verify()
    assert ok


def test_missing_templates_are_reported_not_guessed(tmp_path):
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "people.yaml").write_text("people: []\n", encoding="utf-8")

    result = bootstrap(tmp_path / "CONTROL", templates)
    assert "people.yaml" in result.copied_config
    assert "authority.yaml" in result.missing_templates
    assert "MISSING TEMPLATES" in render_result(result)


def test_absent_template_directory_halts(tmp_path):
    with pytest.raises(HaltError, match="config templates not found"):
        bootstrap(tmp_path / "CONTROL", tmp_path / "nope")


def test_render_names_the_backup_obligation(tmp_path):
    result = bootstrap(tmp_path / "CONTROL", REPO_CONFIG)
    text = render_result(result)
    assert "not in git" in text
    assert "Back it up" in text
