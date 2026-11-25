"""Test seam 2: a fake Gmail MCP server (stdio) that logs every call as a JSON line.

Environment switches (set by the `fake_gmail` fixture):
  FAKE_GMAIL_LOG       file every call is appended to (tool name + arguments)
  FAKE_GMAIL_FAIL_FOR  recipient whose create_draft fails
  FAKE_GMAIL_OMIT      set to leave create_draft out of the tool list
  FAKE_GMAIL_EXIT_AFTER  die (no reply) on the create_draft call after this many have succeeded
  FAKE_GMAIL_CHMOD_DB  database file made read-only by the first create_draft call, so recording fails
  FAKE_GMAIL_TO_LIST   set to mimic the production server: `to` is a list, the result is text
                       only, and a failure is an "Error: ..." text without isError
"""

import json
import os

from mcp.server.mcpserver import MCPServer

server = MCPServer("fake-gmail")
_count = 0


def _log(tool: str, **arguments: object) -> None:
    with open(os.environ["FAKE_GMAIL_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({"tool": tool, "args": arguments}) + "\n")


def _next_id() -> str:
    global _count
    _count += 1
    return f"draft-{_count}"


def _fails(to: str) -> bool:
    return to == os.environ.get("FAKE_GMAIL_FAIL_FOR")


def _misbehave() -> None:
    limit = os.environ.get("FAKE_GMAIL_EXIT_AFTER")
    if limit and _count >= int(limit):
        os._exit(1)  # a crash: the client gets no reply
    if db := os.environ.get("FAKE_GMAIL_CHMOD_DB"):
        os.chmod(db, 0o400)


if "FAKE_GMAIL_OMIT" not in os.environ:
    if "FAKE_GMAIL_TO_LIST" in os.environ:

        @server.tool()
        def create_draft(to: list[str], subject: str, body: str) -> str:
            _log("create_draft", to=to, subject=subject, body=body)
            _misbehave()
            if _fails(to[0]):
                return f"Error: cannot draft for {to[0]}"
            return f"Email draft created successfully with ID: {_next_id()}"

    else:

        @server.tool()
        def create_draft(to: str, subject: str, body: str) -> dict[str, str]:
            _log("create_draft", to=to, subject=subject, body=body)
            _misbehave()
            if _fails(to):
                raise ValueError(f"cannot draft for {to}")
            return {"id": _next_id()}


@server.tool()
def send_message(to: str, subject: str, body: str) -> str:
    """Decoy: actiontrack must never call this (NFR-1)."""
    _log("send_message", to=to, subject=subject, body=body)
    return "sent"


if __name__ == "__main__":
    server.run("stdio")
