"""Spec 04: `actiontrack.toml` and the People Roster (FR-18, NFR-1, NFR-4).

Valid-config behaviour (roster fallback, follow-ups) is proven by specs 05 and 09.
Here `ingest` is the command that loads a config when one is found.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import Harness

EXAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "actiontrack.example.toml"

VALID = """\
sender = "Meera Iyer"

[gmail]
command = ["python", "-m", "fake_gmail"]
draft_tool = "create_draft"

[[people]]
name = "Priya Nair"
email = "priya.nair@example.com"
aliases = ["Priya N."]

[[people]]
name = "Anita Desai"
email = "anita.desai@example.com"
aliases = ["anita"]
"""

BAD_TOML = 'sender = "Meera"\n[gmail]\ncommand = = ["npx"]\ndraft_tool = "create_draft"\n'


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def home_config(harness: Harness) -> Path:
    return harness.home / ".config" / "actiontrack" / "actiontrack.toml"


def ingest_with(harness: Harness, config_text: str) -> tuple[int, str]:
    """Ingest with `config_text` passed via --config; return exit code and stderr."""
    config = write(harness.root / "given.toml", config_text)
    result = harness.run("ingest", str(harness.notes), "--config", str(config))
    return result.code, result.err


# --- lookup (FR-18) ---------------------------------------------------------------


def test_ingest_works_without_any_config_fr18(harness: Harness) -> None:
    result = harness.ingest()
    assert result.code == 0
    assert result.err == ""


def test_shipped_example_config_is_valid_fr18(harness: Harness) -> None:
    result = harness.run("ingest", str(harness.notes), "--config", str(EXAMPLE_CONFIG))
    assert result.code == 0, result.err
    assert result.err == ""


def test_explicit_config_beats_local_and_home_fr18(harness: Harness) -> None:
    write(harness.root / "actiontrack.toml", BAD_TOML)
    write(home_config(harness), BAD_TOML)
    code, err = ingest_with(harness, VALID)
    assert (code, err) == (0, "")


def test_local_config_beats_home_fr18(harness: Harness) -> None:
    write(harness.root / "actiontrack.toml", VALID)
    write(home_config(harness), BAD_TOML)
    result = harness.ingest()
    assert (result.code, result.err) == (0, "")


def test_local_config_is_loaded_when_present_fr18(harness: Harness) -> None:
    write(harness.root / "actiontrack.toml", BAD_TOML)
    write(home_config(harness), VALID)
    result = harness.ingest()
    assert result.code == 2
    assert "actiontrack.toml" in result.err
    assert str(harness.home) not in result.err


def test_home_config_is_loaded_when_no_local_one_fr18(harness: Harness) -> None:
    write(home_config(harness), BAD_TOML)
    result = harness.ingest()
    assert result.code == 2
    assert str(home_config(harness)) in result.err


def test_missing_explicit_config_is_an_error_fr18(harness: Harness) -> None:
    missing = harness.root / "nope.toml"
    write(harness.root / "actiontrack.toml", VALID)  # must not be used as a fallback
    result = harness.run("ingest", str(harness.notes), "--config", str(missing))
    assert result.code == 2
    assert str(missing) in result.err
    assert "not found" in result.err


# --- file errors ------------------------------------------------------------------


def test_invalid_toml_reports_path_and_line_fr18(harness: Harness) -> None:
    code, err = ingest_with(harness, BAD_TOML)
    assert code == 2
    assert "given.toml" in err
    assert "line 3" in err


def test_config_that_is_not_utf8_is_an_error_fr18(harness: Harness) -> None:
    config = harness.root / "given.toml"
    config.write_bytes(b'sender = "\xff"\n')
    result = harness.run("ingest", str(harness.notes), "--config", str(config))
    assert result.code == 2
    assert "given.toml" in result.err


def test_bad_config_leaves_no_database_behind_fr18(harness: Harness) -> None:
    code, _ = ingest_with(harness, BAD_TOML)
    assert code == 2
    assert not harness.db.exists()


# --- [gmail] (NFR-1) --------------------------------------------------------------


@pytest.mark.parametrize("tool", ["send_message", "Gmail_SEND", "reply_all", "forwardMessage"])
def test_draft_tool_that_could_send_is_rejected_nfr1(harness: Harness, tool: str) -> None:
    code, err = ingest_with(harness, VALID.replace('"create_draft"', f'"{tool}"'))
    assert code == 2
    assert "given.toml" in err
    assert tool in err


@pytest.mark.parametrize(
    "gmail",
    [
        'command = ["npx"]',  # no draft_tool
        'command = ["npx"]\ndraft_tool = ""',
        'command = ["npx"]\ndraft_tool = 3',
        'draft_tool = "create_draft"',  # no command
        'command = []\ndraft_tool = "create_draft"',
        'command = ["npx", 1]\ndraft_tool = "create_draft"',
    ],
)
def test_invalid_gmail_section_is_rejected_fr18(harness: Harness, gmail: str) -> None:
    code, err = ingest_with(harness, f'sender = "Meera"\n[gmail]\n{gmail}\n')
    assert code == 2
    assert "gmail" in err


def test_gmail_command_must_be_an_argument_list_not_a_shell_string_nfr4(harness: Harness) -> None:
    code, err = ingest_with(harness, 'sender = "Meera"\n[gmail]\ncommand = "npx -y server"\ndraft_tool = "create_draft"\n')
    assert code == 2
    assert "gmail.command" in err


def test_config_schema_has_no_credential_fields_nfr4(harness: Harness) -> None:
    code, err = ingest_with(harness, VALID.replace("[gmail]\n", '[gmail]\npassword = "hunter2"\n'))
    assert code == 0
    assert "unknown key 'password'" in err


def test_missing_gmail_section_is_rejected_fr18(harness: Harness) -> None:
    code, err = ingest_with(harness, 'sender = "Meera"\n')
    assert code == 2
    assert "[gmail]" in err


def test_sender_is_optional_until_followup_fr18(harness: Harness) -> None:
    code, err = ingest_with(harness, VALID.replace('sender = "Meera Iyer"\n', ""))
    assert (code, err) == (0, "")


def test_sender_must_be_text_fr18(harness: Harness) -> None:
    code, err = ingest_with(harness, VALID.replace('"Meera Iyer"', "42"))
    assert code == 2
    assert "sender" in err


# --- [[people]] (FR-7 roster) -----------------------------------------------------


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        ('email = "x@example.com"', "name"),
        ('name = ""\nemail = "x@example.com"', "name"),
        ('name = "Rahul Mehta"', "email"),
        ('name = "Rahul Mehta"\nemail = "rahul.example.com"', "email"),
        ('name = "Rahul Mehta"\nemail = "r@example.com"\naliases = "rahul"', "aliases"),
        ('name = "Rahul Mehta"\nemail = "r@example.com"\naliases = [""]', "aliases"),
    ],
)
def test_invalid_person_is_rejected_with_its_position_fr18(harness: Harness, entry: str, problem: str) -> None:
    code, err = ingest_with(harness, VALID + f"\n[[people]]\n{entry}\n")
    assert code == 2
    assert "[[people]] entry 3" in err
    assert problem in err


@pytest.mark.parametrize(
    "entry",
    [
        'name = "priya nair"\nemail = "p2@example.com"',  # same full name, other case
        'name = "Anita Rao"\nemail = "ar@example.com"\naliases = ["ANITA"]',  # alias shared
        'name = "Priya N."\nemail = "pn@example.com"',  # full name equals another's alias
    ],
)
def test_ambiguous_roster_is_rejected_fr18(harness: Harness, entry: str) -> None:
    code, err = ingest_with(harness, VALID + f"\n[[people]]\n{entry}\n")
    assert code == 2
    assert "[[people]] entry 3" in err
    assert "already used" in err


def test_alias_equal_to_own_name_is_allowed_fr18(harness: Harness) -> None:
    entry = 'name = "Rahul Mehta"\nemail = "r@example.com"\naliases = ["rahul mehta", "Rahul"]'
    code, err = ingest_with(harness, VALID + f"\n[[people]]\n{entry}\n")
    assert (code, err) == (0, "")


def test_people_must_be_an_array_of_tables_fr18(harness: Harness) -> None:
    code, err = ingest_with(harness, 'people = "Priya"\n' + VALID)
    assert code == 2
    assert "people" in err


# --- unknown keys -----------------------------------------------------------------


def test_unknown_keys_warn_but_do_not_block_fr18(harness: Harness) -> None:
    text = VALID.replace("[gmail]\n", "[gmail]\ntimeout = 5\n") + 'phone = "123"\n'
    code, err = ingest_with(harness, "signature = 'x'\n" + text)
    assert code == 0
    assert "warning" in err
    assert "'signature'" in err
    assert "'timeout'" in err
    assert "'phone'" in err and "[[people]] entry 2" in err


def test_unknown_key_warning_keeps_json_stdout_clean_fr18(harness: Harness) -> None:
    config = write(harness.root / "given.toml", "signature = 'x'\n" + VALID)
    result = harness.run("ingest", str(harness.notes), "--config", str(config), "--json")
    assert result.code == 0
    assert result.json["notes_read"] == 0
    assert "'signature'" in result.err
