"""Find, load and validate `actiontrack.toml` (FR-18, NFR-1, NFR-4).

The schema has no credential fields: Gmail authorisation belongs to the MCP server
(ADR-0001). Every load validates the whole file, so mistakes surface as one clear
`ConfigError` naming the file instead of as wrong emails later.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

FILE_NAME = "actiontrack.toml"
# NFR-1: a tool name containing any of these could send email, so it is never accepted.
FORBIDDEN_TOOL_WORDS = ("send", "reply", "forward")

_TOP_KEYS = ("sender", "gmail", "people")
_GMAIL_KEYS = ("command", "draft_tool")
_PERSON_KEYS = ("name", "email", "aliases")


class ConfigError(Exception):
    """The config is missing or invalid; the message names the file."""


@dataclass(frozen=True)
class Person:
    """One People Roster entry."""

    name: str
    email: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    path: Path
    sender: str | None  # required only by `followup`
    gmail_command: tuple[str, ...]  # argument list, never run through a shell (NFR-4)
    gmail_draft_tool: str
    people: tuple[Person, ...]
    warnings: tuple[str, ...]  # unknown keys: reported, never fatal


def search_paths() -> list[Path]:
    """Where a config is looked for when `--config` is not given, in order."""
    return [Path(FILE_NAME), Path.home() / ".config" / "actiontrack" / FILE_NAME]


def load(explicit: Path | None, *, required: bool = False) -> Config | None:
    """Load `--config` if given, else the first file in `search_paths()`.

    An explicit path must exist. With no config found, return None, or raise when
    `required` (as `followup` is), listing where it looked.
    """
    if explicit is not None:
        if not explicit.is_file():
            raise ConfigError(f"{explicit}: config file not found")
        return _load_file(explicit)
    candidates = search_paths()
    for path in candidates:
        if path.is_file():
            return _load_file(path)
    if required:
        raise ConfigError(f"no config found; looked for {' and '.join(map(str, candidates))}")
    return None


def _load_file(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_bytes().decode("utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read config: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path}: config is not valid UTF-8") from exc
    except tomllib.TOMLDecodeError as exc:  # its message ends with "(at line N, column M)"
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc
    return _Validator(path).config(data)


class _Validator:
    """Turns parsed TOML into a `Config`, failing on the first error and collecting warnings."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.warnings: list[str] = []

    def config(self, data: dict[str, Any]) -> Config:
        self._warn_unknown(data, _TOP_KEYS, "")
        sender = data.get("sender")
        if sender is not None and not _is_text(sender):
            self._fail("sender must be a non-empty string")

        gmail = data.get("gmail")
        if not isinstance(gmail, dict):
            self._fail("missing [gmail] table")
        self._warn_unknown(gmail, _GMAIL_KEYS, " in [gmail]")
        command = gmail.get("command")
        if not (isinstance(command, list) and command and all(_is_text(arg) for arg in command)):
            self._fail("gmail.command must be a non-empty list of strings")
        draft_tool = gmail.get("draft_tool")
        if not _is_text(draft_tool):
            self._fail("gmail.draft_tool must be a non-empty string")
        if any(word in draft_tool.lower() for word in FORBIDDEN_TOOL_WORDS):
            self._fail(
                f"gmail.draft_tool {draft_tool!r} looks like it could send email; "
                f"actiontrack only creates drafts, so a name containing "
                f"{', '.join(FORBIDDEN_TOOL_WORDS)} is refused"
            )

        return Config(
            path=self.path,
            sender=sender.strip() if sender is not None else None,
            gmail_command=tuple(command),
            gmail_draft_tool=draft_tool.strip(),
            people=self._people(data.get("people", [])),
            warnings=tuple(self.warnings),
        )

    def _people(self, entries: Any) -> tuple[Person, ...]:
        if not (isinstance(entries, list) and all(isinstance(entry, dict) for entry in entries)):
            self._fail("people must be [[people]] tables")
        people: list[Person] = []
        owner_of: dict[str, str] = {}  # casefolded name or alias -> full name of its Person
        for position, entry in enumerate(entries, start=1):
            where = f"[[people]] entry {position}"
            self._warn_unknown(entry, _PERSON_KEYS, f" in {where}")
            name, email, aliases = entry.get("name"), entry.get("email"), entry.get("aliases", [])
            if not _is_text(name):
                self._fail(f"{where}: name must be a non-empty string")
            if not (_is_text(email) and "@" in email):
                self._fail(f"{where}: email must be an address containing '@'")
            if not (isinstance(aliases, list) and all(_is_text(alias) for alias in aliases)):
                self._fail(f"{where}: aliases must be a list of non-empty strings")
            person = Person(name.strip(), email.strip(), tuple(alias.strip() for alias in aliases))
            # Names and aliases share one namespace, so the roster itself is never ambiguous.
            for key, written in {label.casefold(): label for label in (person.name, *person.aliases)}.items():
                if key in owner_of:
                    self._fail(f"{where}: {written!r} is already used by {owner_of[key]}")
                owner_of[key] = person.name
            people.append(person)
        return tuple(people)

    def _warn_unknown(self, table: dict[str, Any], known: tuple[str, ...], where: str) -> None:
        for key in table:
            if key not in known:
                self.warnings.append(f"{self.path}: unknown key {key!r}{where} ignored")

    def _fail(self, message: str) -> NoReturn:
        raise ConfigError(f"{self.path}: {message}")


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
