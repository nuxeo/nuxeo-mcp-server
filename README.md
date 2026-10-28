# Nuxeo MCP Server

![Build and Unit Tests](https://github.com/nuxeo/nuxeo-mcp-server/actions/workflows/build-and-unit-tests.yml/badge.svg)
![Integration Tests](https://github.com/nuxeo/nuxeo-mcp-server/actions/workflows/integration-tests.yml/badge.svg)

A Model Context Protocol (MCP) server for interacting with a Nuxeo Content Repository Server. This server provides tools, resources, and prompt templates for AI assistants to interact with Nuxeo content repositories.

## Features

- 🔄 Connect to a Nuxeo Content Repository Server
- 🛠️ MCP Tools for common Nuxeo operations (query, retrieve, create, update, delete documents)
- 🔍 Document search with NXQL, or by meaning on servers with vector search, returning a normalized result envelope
- ⚡ Query DSL search - raw Elasticsearch/OpenSearch request bodies for aggregations, highlighting and sorting
- 🔐 Audit log search - Query DSL against the audit index (admin only)
- 🔒 OAuth2 authentication - browser-based, with token storage
- 📚 MCP Resources for accessing Nuxeo content
- 🧩 MCP Resource Templates for dynamic content access
- 📖 Guide resources - NXQL syntax, and the indexed field names for both Query DSL tools
- 🐳 Docker support for testing with a Nuxeo server
- 🧪 Comprehensive test suite with pytest

## Requirements

- Python 3.11+
- Nuxeo Server (can be run via Docker)
- Docker (for testing)

## Account Privileges

The MCP server connects to Nuxeo using the credentials you provide through configuration — the `NUXEO_USERNAME`/`NUXEO_PASSWORD` environment variables, or OAuth2 (see below). There is no default: with Basic authentication the server refuses to start unless both `NUXEO_USERNAME` and `NUXEO_PASSWORD` are set. Whichever account is configured is the identity Nuxeo uses to enforce ACLs — the server does not assume or force an administrator. Most tools work with **any authenticated Nuxeo user**; administrator privileges are not required for day-to-day operations.

| Privilege | Tools |
|---|---|
| **Any authenticated user** | `nuxeo_get_repository_info`, `nuxeo_list_children`, `nuxeo_search_documents`, `nuxeo_search_documents_with_query_dsl`, `nuxeo_get_document`, `nuxeo_create_document`, `nuxeo_update_metadata`, `nuxeo_delete_document`, `nuxeo_move_document`, `nuxeo_list_document_types`, `nuxeo_get_metadata_schema`, `nuxeo_list_operations` |
| **Administrator only** | `nuxeo_search_audit_with_query_dsl` — the Nuxeo ES passthrough enforces this server-side and returns HTTP 403 for non-admins, which the MCP tool surfaces as a clear permission error |
| **Depends on operation** | `nuxeo_execute_operation` — privilege is determined by the specific Nuxeo Automation operation invoked; enforced server-side |

Using a least-privilege account (a regular Nuxeo user) is recommended for production deployments.

> **Note:** read and write tools are still subject to per-document ACLs enforced by Nuxeo — a user only sees documents they have `Read` on, and can only modify documents where they have `Write`. The `nuxeo_search_documents_with_query_dsl` tool additionally requires the Nuxeo `/site/es` passthrough to be accessible to non-admin users (a server-side configuration decision); the tool's probe returns a clear `"Permission denied"` error if it is not.

## Authentication Mode

The server calls Nuxeo as **one identity, fixed at startup** from the configured credentials. Every client that reaches the server acts as that Nuxeo user, over stdio and over HTTP alike. This is the `local` mode, set with `NUXEO_MCP_AUTH_MODE`: `local` is the default and the only supported value, and any other value stops the server at startup.

Local mode is single-tenant. It is safe on your own machine or a trusted network; it is not safe exposed to callers who should not all act as the configured Nuxeo user.

| Credential | Use it for | Notes |
|---|---|---|
| Basic (`NUXEO_USERNAME` / `NUXEO_PASSWORD`) | Any transport, including the Docker image | The supported configuration for containers. Both variables are required. |
| OAuth2 (`--oauth2` or `NUXEO_AUTH_METHOD=oauth2`) | stdio, from a desktop MCP client | Not supported in containers: sign-in opens a browser and waits for the redirect on a callback server bound to `localhost`, and inside a container that listener is not reachable from the host's browser. |

With OAuth2, the server keeps the tokens it obtains so you do not sign in on every start: in the operating system's keyring when one is available, otherwise in an encrypted `tokens.enc` file whose key sits beside it, both readable only by your user. The fallback directory is `nuxeo-mcp/tokens` under `~/Library/Application Support` on macOS, `$XDG_DATA_HOME` (default `~/.local/share`) on Linux, and `%APPDATA%` on Windows.


## Quick Start

### Basic Authentication (Default)

```bash
# Credentials are required; there is no default identity
NUXEO_URL="http://mynuxeo.example.com/nuxeo" NUXEO_USERNAME="admin" NUXEO_PASSWORD="secret" nuxeo-mcp
```

### OAuth2 Authentication (stdio, desktop only)

```bash
# Configure OAuth2 credentials
export NUXEO_URL="https://mynuxeo.example.com/nuxeo"
export NUXEO_OAUTH_CLIENT_ID="your-client-id"
export NUXEO_OAUTH_CLIENT_SECRET="your-client-secret"

# Start with OAuth2 (browser will open for authentication)
nuxeo-mcp --oauth2

# Or use environment variable
NUXEO_AUTH_METHOD=oauth2 nuxeo-mcp
```

See the [Authentication Guide](specs/20_authentication.md) for detailed OAuth2 setup instructions.

## Documentation

- [Authentication Guide](specs/20_authentication.md) - OAuth2 and authentication setup
- [Developer Guide](DEVELOPER.md) - How to build, run tests, and extend the project
- [Usage Guide](USAGE.md) - How to use the MCP Server

## Docker

### Building the Docker Image

You can build a Docker image for the nuxeo-mcp server using the Dockerfile provided at the root of the project:

```bash
# Build the Docker image with the name nuxeo-mcp-server
docker build -t nuxeo-mcp-server .
```

To build a x86 compatible image on a arm device:

```bash
docker buildx build --platform linux/amd64 -t nuxeo-mcp-server:latest .
```


### Running the Docker Container

Once built, you can run the nuxeo-mcp server in a Docker container. The image uses Basic authentication and refuses to start without `NUXEO_USERNAME` and `NUXEO_PASSWORD`. Every client that reaches the container acts as that Nuxeo user (see [Authentication Mode](#authentication-mode)).

```bash
# Run the container, exposing port 8181
docker run -p 8181:8181 --name nuxeo-mcp \
  -e NUXEO_URL="http://mynuxeo.example.com/nuxeo" \
  -e NUXEO_USERNAME="admin" \
  -e NUXEO_PASSWORD="secret" \
  nuxeo-mcp-server
```

### Environment Variables

You can configure the nuxeo-mcp server using environment variables:

#### Authentication Settings

```bash
# Basic Authentication (required in the container)
docker run -p 8181:8181 \
  -e NUXEO_URL="http://mynuxeo.example.com/nuxeo" \
  -e NUXEO_USERNAME="admin" \
  -e NUXEO_PASSWORD="secret" \
  nuxeo-mcp-server
```

OAuth2 is not supported in the container; see [Authentication Mode](#authentication-mode).

#### Server Mode Configuration

The Docker container supports configurable server modes through environment variables:

- `MCP_MODE`: Server mode (`sse` or `http`, default: `sse`)
- `MCP_PORT`: Server port (default: `8181`)
- `MCP_HOST`: Server host (default: `0.0.0.0`)

> **Note:** The `sse` transport is deprecated in FastMCP and scheduled for
> removal in a future release. New deployments should use `MCP_MODE=http`
> (streamable-HTTP). The `sse` default is retained for backward compatibility.

These examples leave out the credentials; add the `NUXEO_URL`, `NUXEO_USERNAME` and `NUXEO_PASSWORD` variables shown above.

```bash
# Run in HTTP mode
docker run -p 8181:8181 \
  -e MCP_MODE=http \
  --name nuxeo-mcp \
  nuxeo-mcp-server

# Run in SSE mode (default)
docker run -p 8181:8181 \
  -e MCP_MODE=sse \
  --name nuxeo-mcp \
  nuxeo-mcp-server

# Run on a different port
docker run -p 9000:9000 \
  -e MCP_PORT=9000 \
  --name nuxeo-mcp \
  nuxeo-mcp-server
```

## Configuring with Cline

To use the Nuxeo MCP server with Cline, you need to add a configuration to your Cline MCP settings file. See the [Nuxeo MCP Server Configuration Examples](./nuxeo_mcp_config.md) for detailed examples of how to configure the server with different transport options.

The configuration file is typically located at:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%/Claude/claude_desktop_config.json`
- **Cline**: `~/.config/cline/cline_mcp_settings.json` or `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

## License

This project is licensed under the MIT License.
