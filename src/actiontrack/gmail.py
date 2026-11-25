"""The Gmail adapter: the only module that knows MCP (FR-17, NFR-1, NFR-7).

It starts the configured stdio MCP server and calls exactly one tool on it, the configured
create-draft tool. No other tool name appears in this module, so it can never send (NFR-1).
`mcp` is imported inside the function, so the other commands work even if it fails to import.
The async session stays in here; callers use the synchronous `create_drafts`.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from actiontrack.followup import Email

if TYPE_CHECKING:
    from mcp_types import CallToolResult

TIMEOUT_SECONDS = 60  # bounds every wait on the server, so a hung one cannot hang the CLI


class GmailError(Exception):
    """The server could not be started or cannot create drafts; no draft was attempted."""


@dataclass(frozen=True)
class Outcome:
    """One draft: its id as the server returned it, or why it failed."""

    draft_id: str | None = None
    error: str | None = None


def create_drafts(command: Sequence[str], draft_tool: str, emails: Sequence[Email]) -> list[Outcome]:
    """One Outcome per email, in order; one failing draft does not stop the others. Raises `GmailError`."""
    from mcp import MCPError  # lazy: see the module docstring

    try:
        return asyncio.run(_create_drafts(command, draft_tool, emails))
    except BaseExceptionGroup as group:  # the SDK nests start-up failures in (several) groups
        failure = group
        while isinstance(failure, BaseExceptionGroup):
            failure = failure.exceptions[0]
        if isinstance(failure, (OSError, MCPError, GmailError)):
            raise GmailError(_why(failure, command)) from failure
        raise
    except (OSError, MCPError) as exc:
        raise GmailError(_why(exc, command)) from exc


async def _create_drafts(command: Sequence[str], draft_tool: str, emails: Sequence[Email]) -> list[Outcome]:
    from mcp import Client, MCPError, StdioServerParameters

    # env: the SDK passes only a minimal safe environment otherwise, and the server needs HOME for its OAuth tokens.
    server = StdioServerParameters(command=command[0], args=list(command[1:]), env=dict(os.environ))
    async with Client(server, read_timeout_seconds=TIMEOUT_SECONDS) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        if draft_tool not in tools:
            raise GmailError(f"the server offers no tool named {draft_tool!r}")
        # Servers differ on `to`: a plain address, or a list of them (the schema says which).
        to_is_list = tools[draft_tool].input_schema.get("properties", {}).get("to", {}).get("type") == "array"
        outcomes = []
        for email in emails:
            arguments = {"to": [email.to] if to_is_list else email.to, "subject": email.subject, "body": email.body}
            try:
                outcomes.append(_outcome(await client.call_tool(draft_tool, arguments)))
            except MCPError as exc:  # e.g. this one call timed out
                outcomes.append(Outcome(error=exc.error.message))
        return outcomes


def _outcome(result: CallToolResult) -> Outcome:
    text = "".join(part.text for part in result.content if part.type == "text")
    # The production server reports some failures as "Error: ..." text without setting is_error.
    if result.is_error or text.startswith("Error"):
        return Outcome(error=text or "the server reported an error")
    draft_id = (result.structured_content or {}).get("id", text)
    return Outcome(draft_id=str(draft_id)) if draft_id else Outcome(error="the server returned no draft id")


def _why(exc: BaseException, command: Sequence[str]) -> str:
    if isinstance(exc, FileNotFoundError):
        return f"cannot start {command[0]!r}: not found"
    return getattr(getattr(exc, "error", None), "message", None) or str(exc) or type(exc).__name__
