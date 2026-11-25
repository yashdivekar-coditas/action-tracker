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

from actiontrack.followup import FollowupDraft

if TYPE_CHECKING:
    from mcp_types import CallToolResult, Tool

TIMEOUT_SECONDS = 60  # bounds every wait on the server, so a hung one cannot hang the CLI


class GmailError(Exception):
    """The server could not be started or cannot create drafts; no draft was attempted."""


@dataclass(frozen=True)
class Outcome:
    """One draft: its id as the server returned it, or why it failed."""

    draft_id: str | None = None
    error: str | None = None


def create_drafts(command: Sequence[str], draft_tool: str, drafts: Sequence[FollowupDraft]) -> list[Outcome]:
    """One Outcome per draft, in order; a failing draft does not stop the others.

    Drafts already created are never lost: if the server dies or the transport fails part-way, the
    drafts not yet made come back as failures. Raises `GmailError` only if no draft was attempted.
    """
    from mcp import MCPError  # lazy: see the module docstring

    outcomes: list[Outcome] = []  # filled by the session, so it survives a failure part-way
    try:
        asyncio.run(_create_drafts(command, draft_tool, drafts, outcomes))
    except (Exception, BaseExceptionGroup) as exc:  # the SDK nests failures in (several) groups
        failure: BaseException = exc
        while isinstance(failure, BaseExceptionGroup):
            failure = failure.exceptions[0]
        if not outcomes and not isinstance(failure, (OSError, MCPError, GmailError)):
            raise
        reason = _failure_message(failure, command)
        if not outcomes:
            raise GmailError(reason) from failure
        outcomes.extend(Outcome(error=reason) for _ in drafts[len(outcomes) :])
    return outcomes


async def _create_drafts(
    command: Sequence[str], draft_tool: str, drafts: Sequence[FollowupDraft], outcomes: list[Outcome]
) -> None:
    from mcp import Client, MCPError, StdioServerParameters

    # env: the SDK passes only a minimal safe environment otherwise, and the server needs HOME for its OAuth tokens.
    server = StdioServerParameters(command=command[0], args=list(command[1:]), env=dict(os.environ))
    async with Client(server, read_timeout_seconds=TIMEOUT_SECONDS) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        if draft_tool not in tools:
            raise GmailError(f"the server offers no tool named {draft_tool!r}")
        to_is_list = _takes_recipients_as_list(tools[draft_tool])
        for draft in drafts:
            arguments = {"to": [draft.to] if to_is_list else draft.to, "subject": draft.subject, "body": draft.body}
            try:
                outcomes.append(_outcome(await client.call_tool(draft_tool, arguments)))
            except MCPError as exc:  # e.g. this one call timed out
                outcomes.append(Outcome(error=exc.error.message))


def _takes_recipients_as_list(tool: Tool) -> bool:
    """Servers differ on `to`: a plain address, or a list of them (the tool's input schema says which)."""
    return tool.input_schema.get("properties", {}).get("to", {}).get("type") == "array"


def _outcome(result: CallToolResult) -> Outcome:
    text = "".join(part.text for part in result.content if part.type == "text")
    # The production server reports some failures as "Error: ..." text without setting is_error.
    if result.is_error or text.startswith("Error:"):
        return Outcome(error=text or "the server reported an error")
    draft_id = (result.structured_content or {}).get("id", text)
    return Outcome(draft_id=str(draft_id)) if draft_id else Outcome(error="the server returned no draft id")


def _failure_message(exc: BaseException, command: Sequence[str]) -> str:
    if isinstance(exc, FileNotFoundError):
        return f"cannot start {command[0]!r}: not found"
    return getattr(getattr(exc, "error", None), "message", None) or str(exc) or type(exc).__name__
