# Client Configuration

Examples for MCP clients that read an `mcpServers` JSON file, such as Claude
Desktop:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

Other clients use the same `command`/`args`/`env` or `url` entries under their
own file names.

## stdio

The client starts the server as a subprocess. Basic authentication needs both
`NUXEO_USERNAME` and `NUXEO_PASSWORD`; there is no default identity.

From a checkout, with [uv](https://docs.astral.sh/uv/):

```json
{
  "mcpServers": {
    "nuxeo": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/nuxeo-mcp-server", "--frozen", "nuxeo-mcp"],
      "env": {
        "NUXEO_URL": "http://localhost:8080/nuxeo",
        "NUXEO_USERNAME": "Administrator",
        "NUXEO_PASSWORD": "Administrator"
      }
    }
  }
}
```

With the package installed in a virtual environment, use its `nuxeo-mcp`
executable as `command`, for example `/path/to/.venv/bin/nuxeo-mcp`, with the
same `env`.

To sign in with OAuth2 instead, add `"--oauth2"` to `args` and set the
`NUXEO_OAUTH_*` variables; see [AUTHENTICATION.md](AUTHENTICATION.md).

## HTTP

The server runs on its own, for example in Docker (see the
[README](README.md#docker)) or with `nuxeo-mcp --http --port 8181`, and the client
connects to its `/mcp` endpoint:

```json
{
  "mcpServers": {
    "nuxeo": {
      "url": "http://127.0.0.1:8181/mcp"
    }
  }
}
```

With `docker-compose-demo.yml`, the port is `8081`. Clients that only launch
stdio servers need a bridge such as
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote):
`"command": "npx", "args": ["mcp-remote", "http://127.0.0.1:8181/mcp"]`.

Every client reaching the HTTP endpoint acts as the configured Nuxeo user: only
expose it on a trusted network (see
[Authentication Mode](README.md#authentication-mode)).
