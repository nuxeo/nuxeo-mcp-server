# AGENTS.md — Nuxeo MCP Server

> Guidance for AI coding agents working in this repository.

## Project Overview

Nuxeo MCP Server is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that exposes Nuxeo Content Repository operations to AI assistants. It lets AI tools create, read, update, delete, search, and manage documents on a Nuxeo server through a standardised MCP interface.

**Tech stack:** [FastMCP 4](https://github.com/jlowin/fastmcp), Nuxeo Python client, FastAPI/Uvicorn, Docker.

## Repository Layout

```
nuxeo-mcp-server/
├── src/nuxeo_mcp/          # Package source
│   ├── server.py           # MCP server entry-point & FastMCP setup
│   ├── tools.py            # All MCP tools
│   ├── resources.py        # MCP resources (nuxeo:// URIs)
│   ├── prompts.py          # MCP prompt templates
│   ├── es_passthrough.py   # Search-engine passthrough
│   ├── query_dsl.py        # Query DSL guardrails & field guides
│   ├── search_models.py    # Normalized search envelope
│   ├── annotations.py      # Tool safety annotations
│   ├── auth.py             # OAuth2 / Basic auth handlers
│   ├── middleware.py       # Authentication middleware
│   ├── config.py           # Configuration dataclasses & enums
│   ├── token_store.py      # OAuth2 token storage
│   ├── utility.py          # Document formatting helpers
│   └── __main__.py         # CLI entry-point
├── tests/                  # pytest test suite
├── ci/                     # CI helper files (Docker, etc.)
├── specs/                  # Specification documents
├── .github/workflows/      # GitHub Actions CI/CD
├── pyproject.toml          # Project metadata & dependencies
├── Dockerfile              # Container image
├── docker-compose.yml      # Local multi-container setup
└── seed_nuxeo.py           # Test data seeding script
```

## Development Setup

```bash
# Recommended (fast, reproducible)
uv sync --frozen --extra dev

# Alternative
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

> **Note:** `fastmcp` (4.1.x) and its `fastmcp-slim` dependency install into the
> same `fastmcp/` import namespace. Repeated in-place `uv sync` / reinstall churn
> can leave that namespace in a broken state (`ImportError: cannot import name
> 'FastMCP' from 'fastmcp'`, missing `__init__.py`). If that happens, rebuild the
> environment cleanly: `rm -rf .venv && uv sync --frozen --extra dev`. A clean
> install always resolves it, which is why CI (fresh env) is unaffected.

## Build

```bash
uv build          # Produces sdist + wheel in dist/
```

## Running Tests

```bash
# Unit tests only (no Nuxeo server required)
uv run pytest tests/ -v --no-integration

# Integration tests (requires Docker + Nuxeo image)
uv run pytest tests/ -v --integration

# Debug mode with live log output
uv run pytest -s --log-cli-level=INFO
```

## Code Style

```bash
uv run black src/ tests/     # Format (88 char line length)
uv run isort src/ tests/     # Sort imports (black-compatible)
uv run mypy src/             # Type-check (strict mode)
```

All three must pass before merging.

## Key Conventions

- **Type hints everywhere** — mypy strict mode is enforced.
- **snake_case** for functions and variables; **PascalCase** for classes; **UPPER_SNAKE_CASE** for constants.
- **Decorator-based registration** — tools, resources, and prompts use `@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`.
- **Single Responsibility** — each module has one clear purpose; do not mix concerns.
- **Docstrings** on every public module, class, and function.

---

## MCP Surface

### Tools (`src/nuxeo_mcp/tools.py`)

Tools are registered via `register_tools(mcp, nuxeo)`.

<!-- BEGIN GENERATED TOOLS -->

14 tools, generated from the registered MCP schema by `scripts/generate_tool_reference.py` -- do not edit by hand.

| Tool | Read-only | Destructive | Open-world | Description |
|------|-----------|-------------|------------|-------------|
| `nuxeo_create_document` | no | no | no | Create a new document in the Nuxeo repository with optional file attachment. To confirm the result, read it back with nuxeo_get_document; search may not see it yet. |
| `nuxeo_delete_document` | no | yes | no | Delete a document from the Nuxeo repository, by UID. To delete by path, read the UID with nuxeo_get_document first. |
| `nuxeo_execute_operation` | no | yes | yes | Execute a Nuxeo Operation with the specified parameters and input |
| `nuxeo_get_document` | yes | no | no | Get a document from the Nuxeo repository |
| `nuxeo_get_metadata_schema` | yes | no | no | Get detailed information about schemas defined in the Nuxeo server |
| `nuxeo_get_repository_info` | yes | no | no | Get information about the Nuxeo repository |
| `nuxeo_list_children` | yes | no | no | list children of a folder document |
| `nuxeo_list_document_types` | yes | no | no | Get information about document types and schemas defined in the Nuxeo server |
| `nuxeo_list_operations` | yes | no | no | Get information about available Automation Operations in the Nuxeo server |
| `nuxeo_move_document` | no | yes | no | Move a document, identified by UID, under the folder at target_path. Not idempotent: repeating the call renames the document. To move by path, read the UID with nuxeo_get_document first. |
| `nuxeo_search_audit_with_query_dsl` | yes | no | yes | Run a raw OpenSearch/Elasticsearch Query DSL request against the Nuxeo audit log index and return the engine response, plus two server-added keys: _nuxeo_executed_query (the guarded request) and _nuxeo_hint (set on empty results). Administrators only. Read nuxeo://audit-query-dsl-guide first for the field names. |
| `nuxeo_search_documents` | yes | no | no | Search documents in the Nuxeo repository. mode='nxql' (default) runs a NXQL statement: read nuxeo://nxql-guide first, it gives the default filter that keeps versions and system documents out. mode='semantic' matches a question or phrase on meaning, only on servers with vector search; elsewhere it fails with an error saying so. Returns a normalized result envelope. For counts, groupings or aggregations, use nuxeo_search_documents_with_query_dsl instead. Recently created or modified documents may take a few seconds to appear; read them by uid or path with nuxeo_get_document instead. |
| `nuxeo_search_documents_with_query_dsl` | yes | no | yes | Run a raw OpenSearch/Elasticsearch Query DSL request against the Nuxeo repository index and return the engine response, plus two server-added keys: _nuxeo_executed_query (the guarded request) and _nuxeo_hint (set on empty results). Use this for aggregations, highlighting, sorting and any query the normalized search cannot express. Read nuxeo://query-dsl-guide first for the field names. Recently created or modified documents may take a few seconds to appear; read them by uid or path with nuxeo_get_document instead. |
| `nuxeo_update_metadata` | no | yes | no | Update an existing document in the Nuxeo repository |

<!-- END GENERATED TOOLS -->

**Adding a new tool:**

Tool names must be `nuxeo_{verb}_{object}`, and every tool must declare its
safety hints in `annotations.py` — registration raises at startup otherwise.
Both rules are asserted by `tests/test_tool_contracts.py`.

```python
# 1. declare the hints in annotations.py
TOOL_ANNOTATIONS["nuxeo_my_tool"] = _read("Do the thing")

# 2. register in tools.py, inside register_tools()
@tool(
    name="nuxeo_my_tool",
    description="What this tool does",
)
def nuxeo_my_tool(param: str) -> dict:
    """Docstring describing the tool."""
    result = nuxeo_client.some_operation(param)
    return {"result": result}
```

### Resources (`src/nuxeo_mcp/resources.py`)

Resources are registered via `register_resources(mcp, nuxeo)` and use the `nuxeo://` URI scheme:

| URI pattern | Description |
|-------------|-------------|
| `nuxeo://info` | Server information |
| `nuxeo://{uid}` | Document by UUID |
| `nuxeo://{path*}` | Document by repository path |
| `nuxeo://{uid}@{adapter}/{adapter_param}` | Document with adapter |
| `nuxeo://nxql-guide` | Embedded NXQL reference |
| `nuxeo://query-dsl-guide` | Repository index field reference for the Query DSL tool |
| `nuxeo://audit-query-dsl-guide` | Audit index field reference for the Query DSL tool |

**Adding a new resource:**

```python
@mcp.resource("nuxeo://my-resource")
def get_my_resource() -> dict:
    """Docstring describing the resource."""
    return {"data": nuxeo_client.fetch_something()}
```

### Prompts (`src/nuxeo_mcp/prompts.py`)

Prompts are registered via `register_prompts(mcp, nuxeo)`:

| Prompt | Description |
|--------|-------------|
| `list_doc_by_type` | Generate a search prompt for a given document type |

**Adding a new prompt:**

```python
@mcp.prompt(name="my_prompt")
def my_prompt(arg: str) -> str:
    """Return a formatted prompt string."""
    return f"List all documents related to {arg}"
```

---

## Architecture

### Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `server.py` | Instantiates `FastMCP`, builds the Nuxeo client for the configured auth method, calls all `register_*()` functions |
| `tools.py` | Implements every MCP tool; delegates to the Nuxeo Python client |
| `resources.py` | Implements every MCP resource; formats documents for consumption |
| `prompts.py` | Defines reusable prompt templates |
| `config.py` | `NuxeoServerConfig`, `OAuth2Config`, `MCPAuthConfig` dataclasses; `AuthMethod` and `AuthMode` enums |
| `auth.py` | `OAuth2AuthHandler` (PKCE flow), `BasicAuthHandler`; browser-based callback server |
| `middleware.py` | `AuthenticationManager` runs the OAuth2 sign-in at startup and hands the server an authenticated Nuxeo client; it does not wrap tools |
| `token_store.py` | `TokenManager` — persists and refreshes OAuth2 tokens |
| `es_passthrough.py` | `ElasticsearchPassthrough` — forwards Query DSL to Nuxeo `/site/es`; Nuxeo applies the ACLs |
| `query_dsl.py` | Guardrails (size/from/response caps, script rejection) and field guides for the Query DSL tools |
| `search_models.py` | `SearchResult`/`SearchHit` — the normalized envelope shared by every search mode |
| `annotations.py` | `TOOL_ANNOTATIONS` — declared safety hints, one entry per tool |
| `utility.py` | `format_document()`, UUID detection, blob helpers |

### Startup Sequence

```
__main__.py  →  main()
  └─ server.py: NuxeoMCPServer.__init__()
       ├─ server.py main(): read NUXEO_URL / NUXEO_AUTH_METHOD / NUXEO_MCP_AUTH_MODE / credentials from env
       ├─ auth.py / middleware.py: build Nuxeo client (basic or OAuth2); basic refuses to start without credentials
       ├─ server.py: create FastMCP instance + /health endpoint
       ├─ tools.py: register_tools()
       ├─ resources.py: register_resources()
       └─ prompts.py: register_prompts()
```

### Authentication Flow

Authentication happens once, at startup. The server then holds one Nuxeo client and every tool call uses it, so every caller acts as the same Nuxeo identity (`NUXEO_MCP_AUTH_MODE=local`, the default and only mode).

```
Startup
  ├─ basic  (NUXEO_AUTH_METHOD=basic, the default)
  │    └─ Nuxeo client from NUXEO_USERNAME / NUXEO_PASSWORD (both required, no default)
  └─ oauth2 (--oauth2 or NUXEO_AUTH_METHOD=oauth2)
       └─ AuthenticationManager → OAuth2AuthHandler
            ├─ TokenManager: check stored token
            ├─ If expired: refresh it, save the rotated token (Nuxeo unreachable: keep it)
            └─ If none: launch PKCE browser flow → callback server
```

Set `NUXEO_AUTH_METHOD=oauth2` (or `basic`) in the environment to select the authentication method. OAuth2 needs the server to run where the browser can reach its `localhost` callback (a desktop, or a remote host through an SSH tunnel), over stdio or HTTP; it does not work in a container. Sign-in messages go to stderr: over stdio, stdout is the MCP channel.

### Elasticsearch Passthrough

`ElasticsearchPassthrough` in `es_passthrough.py` forwards a Query DSL body, unchanged, to Nuxeo's `/site/es/{index}/_search`. Nuxeo applies the caller's ACLs and restricts the audit index to administrators; this server adds no filter. `query_dsl.apply_guardrails()` bounds the body before it is sent (script rejection, size/from caps, `top_hits`/`inner_hits` caps), and `PassthroughError` turns Nuxeo and engine failures into messages that tell the model whether to fix the query or stop.

### Configuration via Environment Variables

| Variable | Purpose |
|----------|---------|
| `NUXEO_URL` | Nuxeo server URL (default: `http://localhost:8080/nuxeo`) |
| `NUXEO_USERNAME` | Username for Basic auth (required, no default) |
| `NUXEO_PASSWORD` | Password for Basic auth (required, no default) |
| `NUXEO_AUTH_METHOD` | `basic` or `oauth2`; any other value stops startup |
| `NUXEO_MCP_AUTH_MODE` | `local` (default, only value): one Nuxeo identity for every caller |
| `NUXEO_OAUTH_CLIENT_ID` | OAuth2 client ID |
| `NUXEO_OAUTH_CLIENT_SECRET` | OAuth2 client secret |
| `NUXEO_OAUTH_AUTH_ENDPOINT` | OAuth2 authorization endpoint |
| `NUXEO_OAUTH_TOKEN_ENDPOINT` | OAuth2 token endpoint |
| `NUXEO_OAUTH_OPENID_URL` | OpenID Connect configuration URL |
| `NUXEO_OAUTH_REDIRECT_PORT` | Local port for OAuth2 callback (default: auto) |
| `NUXEO_OAUTH_SCOPE` | OAuth2 scopes (default: `openid profile email`) |

### Server Transport Modes

The server binary (`nuxeo-mcp`) supports three transport modes:

```bash
nuxeo-mcp                          # stdio (default, for MCP clients)
nuxeo-mcp --http --port 8080       # Streamable-HTTP
nuxeo-mcp --sse  --port 8080       # SSE (deprecated, use --http instead)
nuxeo-mcp --oauth2                 # Enable OAuth2 auth (any transport)
nuxeo-mcp --oauth2 --no-browser    # OAuth2, sign-in URL printed on stderr
```

A `/health` endpoint is always available in HTTP and SSE modes.

---

### Strategy

| Layer | Location | Marker | Needs Nuxeo? |
|-------|----------|--------|--------------|
| Unit | `tests/test_*.py` | *(none / default)* | No |
| Integration | `tests/test_integration.py`, `test_oauth2_integration.py`, etc. | `@pytest.mark.integration` | Yes (Docker) |

### Running Tests Locally

```bash
# Unit only
uv run pytest tests/ -v --no-integration

# Integration (spins up Nuxeo via Docker automatically via conftest.py)
uv run pytest tests/ -v --integration

# Rancher Desktop variant
uv run pytest tests/ -v --integration --rancher

# Verbose logging
uv run pytest -s --log-cli-level=INFO
```

### Test Fixtures (`tests/conftest.py`)

- `nuxeo_client` — provides a connected `Nuxeo` client pointed at the Docker container.
- The Docker container is started once per session; credentials come from `tests/test_credentials.py`.
- `@pytest.mark.integration` gates tests that require a live server.

### Seeding Test Data

```bash
uv run python seed_nuxeo.py \
  --url http://localhost:8080/nuxeo \
  --username admin \
  --password secret
```

Creates a sample folder, `File` document (with PDF), and `Note` document.

### Writing New Tests

- **Unit tests** mock the Nuxeo client — never make real HTTP calls.
- **Integration tests** must be decorated with `@pytest.mark.integration` and use the `nuxeo_client` fixture.
- Test files live in `tests/`, named `test_<feature>.py`.
- `standalone_test_*.py` files are debugging utilities — not part of the CI suite.

### CI/CD Pipelines (`.github/workflows/`)

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `build-and-unit-tests.yml` | Push to `main`, PRs | `uv build` + unit tests |
| `integration-tests.yml` | Push to `main`, PRs | Pull Nuxeo image, run integration tests |
| `package-docker-image.yml` | Push to `main`, PRs | Build multi-arch Docker image, push to registry |
| `updatecli.yml` | Scheduled | Automated dependency updates |

All workflows use the composite action `.github/actions/setup-and-install-dep` for consistent, frozen installs via `uv`.

---

## Agent Guidelines

### Before Making Changes

1. Identify which module owns the responsibility (see [Module Responsibilities](#module-responsibilities)).
2. Check whether the feature belongs in `tools.py`, `resources.py`, or `prompts.py` — avoid adding logic to `server.py`.
3. Run unit tests first to establish a passing baseline: `uv run pytest tests/ -v --no-integration`.

### Do

- **Add type hints** to every function signature, including return types.
- **Write a docstring** for every new public function, class, and module.
- **Register through `register_*()`** — never call `@mcp.tool()` / `@mcp.resource()` outside the designated registration function.
- **Use the Nuxeo Python client** for all server interactions; do not construct raw HTTP calls.
- **Add a matching unit test** for every new tool, resource, or parser change.
- **Format before committing**: `uv run black src/ tests/ && uv run isort src/ tests/`.

### Don't

- Don't add business logic to `server.py` — it is wiring only.
- Don't store credentials in source code or tests; use environment variables or `tests/test_credentials.py`.
- Don't merge without passing `uv run mypy src/` in strict mode.
- Don't add `standalone_test_*.py` files to the CI test suite — they are development-only debugging utilities.
- Don't build a Nuxeo client inside a tool; use the one `register_tools()` receives, so every call runs as the configured identity.

### Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| mypy error on untyped third-party library | Add a `py.typed` stub or use `# type: ignore[import]` with a comment |
| Integration test runs in unit CI | Ensure the test is decorated with `@pytest.mark.integration` |
| OAuth2 token not refreshed | Check `TokenManager.get_valid_token()` — it handles refresh automatically |
| Tool not appearing in MCP client | Verify it is registered inside `register_tools()`, not at module level |
| `ImportError: cannot import name 'FastMCP' from 'fastmcp'` | `fastmcp`/`fastmcp-slim` share one namespace; in-place reinstalls can break it. Rebuild clean: `rm -rf .venv && uv sync --frozen --extra dev` |

### Dependency Management

```bash
uv add <package>                  # Add runtime dependency
uv add --optional dev <package>   # Add dev-only dependency
uv lock                           # Regenerate lock file
uv lock --upgrade                 # Upgrade all dependencies
```

Always commit both `pyproject.toml` and `uv.lock` together.
