# GoLinks MCP Server

An MCP server that exposes [GoLinks](https://www.golinks.io) as tools for AI assistants. Built with [FastMCP](https://gofastmcp.com).

## Hosted HTTP Mode

This server is intended to run as a hosted remote MCP server over Streamable HTTP.

Public endpoint shape:

```text
https://mcp.golinks.io/mcp
```

Local development endpoint shape:

```text
http://localhost:8000/mcp
```

## Authentication

The hosted server does not use a shared `GOLINKS_API_TOKEN`.

MCP clients should send a per-user GoLinks OAuth/API bearer token with each request:

```http
Authorization: Bearer YOUR_TOKEN
```

The MCP server forwards that header to `api.golinks.io`. GoLinks remains responsible for token validation, scope enforcement, refresh, storage, and revocation.

An OAuth client must be pre-registered in your GoLinks workspace with:

- Allowed scopes: `golinks:read`, `golinks:write`, `search:read`
- Redirect URIs: the exact callback URL(s) your MCP client uses

To do so, visit the [OAuth Apps](https://app.golinks.io/developer-tools.php#/oauth-apps) page under Developer Tools, on the GoLinks dashboard

## Local Development

This project uses Python `3.12` and [`uv`](https://docs.astral.sh/uv/).

1. Install Python `3.12`.
2. Install `uv`.
3. Create the local environment and install dependencies:

```bash
uv sync
```

4. Run the MCP server locally:

```bash
uv run python -m golinks_mcp
```

The server binds to `0.0.0.0:8000` by default. Override with `MCP_HOST` and `MCP_PORT` if you need a different host or port:

```bash
MCP_HOST=127.0.0.1 MCP_PORT=9000 uv run python -m golinks_mcp
```

5. Verify health and OAuth discovery:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/.well-known/oauth-authorization-server
```

## Docker

Build and run locally:

```bash
docker build -t golinks-mcp .
docker run --rm -p 8000:8000 golinks-mcp
```

## Tools

| Tool             | Description                                | Scope           |
| ---------------- | ------------------------------------------ | --------------- |
| `list_golinks`   | List all company go links (paginated)      | `golinks:read`  |
| `get_golink`     | Get a single go link by name or numeric ID | `golinks:read`  |
| `search_golinks` | Fuzzy keyword search across go links       | `search:read`   |
| `create_golink`  | Create a new go link (standard only)       | `golinks:write` |
