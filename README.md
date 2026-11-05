# Nuxeo MCP Server

![Build and Unit Tests](https://github.com/nuxeo/nuxeo-mcp-server/actions/workflows/build-and-unit-tests.yml/badge.svg)
![Integration Tests](https://github.com/nuxeo/nuxeo-mcp-server/actions/workflows/integration-tests.yml/badge.svg)

A Model Context Protocol (MCP) server for interacting with a Nuxeo Content Repository Server. This server provides tools, resources, and prompt templates for AI assistants to interact with Nuxeo content repositories.

## Features

- 🔄 Connect to a Nuxeo Content Repository Server
- 🛠️ MCP Tools for common Nuxeo operations (query, retrieve, create, update, delete documents)
- 🔍 Document search with NXQL, returning a normalized result envelope; search by meaning is [experimental](#experimental-features)
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

> **Note:** read and write tools are still subject to per-document ACLs enforced by Nuxeo — a user only sees documents they have `Read` on, and can only modify documents where they have `Write`. The `nuxeo_search_documents_with_query_dsl` tool additionally requires the Nuxeo `/site/es` passthrough to be accessible to non-admin users (a server-side configuration decision); the tool returns a clear `"Permission denied"` error if it is not.

## Authentication Mode

The server calls Nuxeo as **one identity, fixed at startup** from the configured credentials. Every client that reaches the server acts as that Nuxeo user, over stdio and over HTTP alike. This is the `local` mode, set with `NUXEO_MCP_AUTH_MODE`: `local` is the default and the only supported value, and any other value stops the server at startup.

Local mode is single-tenant. It is safe on your own machine or a trusted network; it is not safe exposed to callers who should not all act as the configured Nuxeo user.

| Credential | Use it for | Notes |
|---|---|---|
| Basic (`NUXEO_USERNAME` / `NUXEO_PASSWORD`) | Any transport, including the Docker image | The supported configuration for containers. Both variables are required. |
| OAuth2 (`--oauth2` or `NUXEO_AUTH_METHOD=oauth2`) | A server running where your browser can reach it: typically a desktop MCP client over stdio, or a remote host through an SSH tunnel | The transport does not matter, stdio or HTTP. Sign-in waits for the browser's redirect on `http://localhost:<port>/callback`, listening on the server's loopback interface. Not supported in containers: a published port does not reach that listener. |

With OAuth2, the server keeps the tokens it obtains so you do not sign in on every start: in the operating system's keyring when one is available, otherwise in an encrypted `tokens.enc` file whose key sits beside it, both readable only by your user. The fallback directory is `nuxeo-mcp/tokens` under `~/Library/Application Support` on macOS, `$XDG_DATA_HOME` (default `~/.local/share`) on Linux, and `%APPDATA%` on Windows.

## Read-Only Mode

Set `NUXEO_MCP_READ_ONLY=true` to expose only the read tools. The tools that change the repository (`nuxeo_create_document`, `nuxeo_update_metadata`, `nuxeo_move_document`, `nuxeo_delete_document`, `nuxeo_execute_operation`) are not registered, so a client cannot list or call them. Accepted values: `true`/`false` (also `1`/`0`, `yes`/`no`, `on`/`off`); unset means `false`; any other value stops the server. `/health` reports `read_only`.

This limits what the MCP server exposes, not what the Nuxeo account may do: the account's ACLs still apply, and over HTTP anyone who reaches the server reads as that account.

## Experimental Features

Set `NUXEO_MCP_EXPERIMENTAL=true` to expose features that depend on Nuxeo features no release ships yet: today, the `semantic`, `image` and `similar` modes of `nuxeo_search_documents`, which need the experimental Nuxeo vector search (never on LTS 2023). Off by default, the tool describes `mode="nxql"` only and refuses the other modes. Same accepted values as `NUXEO_MCP_READ_ONLY`; `/health` reports `experimental`. See [USAGE](USAGE.md#modesemantic).

## Local Files (`file_path`)

`nuxeo_create_document` and `nuxeo_execute_operation` accept a `file_path`: a file on the machine running the MCP server, not the caller's. The server uploads it to Nuxeo, where any caller can read it back.

| Transport | `NUXEO_MCP_UPLOAD_DIR` unset | `NUXEO_MCP_UPLOAD_DIR` set |
|---|---|---|
| stdio | Any file the server can read | Only regular files inside the folder |
| HTTP | Refused | Only regular files inside the folder |

Paths are checked after resolving `..` and symlinks; a relative path is taken from the folder. A folder that does not exist stops the server at startup. `/health` reports `file_path` as `any`, `upload_dir` or `disabled`.

Over HTTP, an unrestricted `file_path` would let any caller read the server's own files through Nuxeo: its environment (including `NUXEO_PASSWORD`), the OAuth2 token store, credentials and mounted secrets. Only point `NUXEO_MCP_UPLOAD_DIR` at a folder holding files meant to be shared, and writable only by trusted parties: the path is checked, then the file is opened again for the upload, so a local process able to write there could swap it in between.

## Quick Start

### Basic Authentication (Default)

```bash
# Credentials are required; there is no default identity
NUXEO_URL="http://mynuxeo.example.com/nuxeo" NUXEO_USERNAME="admin" NUXEO_PASSWORD="secret" nuxeo-mcp
```

### OAuth2 Authentication (where your browser can reach the server)

```bash
# Configure OAuth2 credentials
export NUXEO_URL="https://mynuxeo.example.com/nuxeo"
export NUXEO_OAUTH_CLIENT_ID="your-client-id"
export NUXEO_OAUTH_CLIENT_SECRET="your-client-secret"

# Start with OAuth2 (browser will open for authentication)
nuxeo-mcp --oauth2

# Or use environment variable
NUXEO_AUTH_METHOD=oauth2 nuxeo-mcp

# On a remote host: print the sign-in URL instead of opening a browser, and
# forward the callback port from your machine (ssh -L 8888:localhost:8888 host)
nuxeo-mcp --oauth2 --no-browser
```

See the [Authentication Guide](AUTHENTICATION.md) for registering the OAuth2 client in Nuxeo and the sign-in flow.

## Documentation

- [Authentication Guide](AUTHENTICATION.md) - OAuth2 and authentication setup
- [Developer Guide](DEVELOPER.md) - How to build, run tests, and extend the project
- [Usage Guide](USAGE.md) - How to use the MCP Server
- [Test Scenario](nuxeo_mcp_test_scenario.md) - Agent-run check of every tool against a live Nuxeo server

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

### Server Settings

The container serves MCP over streamable HTTP at `http://<host>:<port>/mcp`, with `/health` beside it:

- `MCP_PORT`: Server port (default: `8181`)
- `MCP_HOST`: Server host (default: `0.0.0.0`)

OAuth2 is not supported in the container; see [Authentication Mode](#authentication-mode). Over HTTP, `file_path` uploads are refused unless `NUXEO_MCP_UPLOAD_DIR` is set (see [Local Files](#local-files-file_path)).

### Nuxeo and the MCP Server Together

`docker-compose-demo.yml` starts the `nuxeo-mcp-demo` image (Nuxeo with embedded OpenSearch, showcase content and Web UI, see [ci/docker/nuxeo](ci/docker/nuxeo/README.md)) beside the MCP server, on `http://localhost:8081/mcp`:

```bash
docker compose -f docker-compose-demo.yml up --build
```

Inside Docker, point `NUXEO_URL` at the Nuxeo service name (`http://nuxeo:8080/nuxeo`), not `localhost`, and set `NUXEO_PUBLIC_URL` to the URL users open (`http://localhost:8080/nuxeo`): the document links the tools return are built on it.

## Configuring an MCP Client

See [Client Configuration](nuxeo_mcp_config.md) for stdio and HTTP examples.

## License

Licensed under the [Apache License, Version 2.0](LICENSE). Copyright Hyland and
others; see [NOTICE](NOTICE).

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Report
vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).
