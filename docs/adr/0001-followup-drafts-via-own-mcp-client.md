# Follow-up drafts go through the CLI's own MCP client

`followup` must create Gmail drafts "through the Gmail MCP connector", but the claude.ai Gmail connector only exists inside a Claude session and a standalone CLI cannot reach it. We considered shelling out to `claude -p` with only `create_draft` allowed, and having the CLI emit draft files for a human to push through Claude Code. We chose to make actiontrack itself an MCP client that talks to a configurable Gmail MCP server, so the command creates the draft on its own without depending on Claude Code being installed and logged in.

## Consequences

- actiontrack owns the MCP connection and the Gmail server's auth setup, which is more code and setup than the `claude -p` route.
- The CLI only ever calls the server's create-draft tool; never-send is enforced in actiontrack, not by a host's tool permissions.
