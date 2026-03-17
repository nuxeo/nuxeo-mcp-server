# AGENTS.md — Nuxeo MCP Server

> Guidance for AI coding agents working in this repository.

## Project Overview

Nuxeo MCP Server is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that exposes Nuxeo Content Repository operations to AI assistants. It lets AI tools create, read, update, delete, search, and manage documents on a Nuxeo server through a standardised MCP interface.

**Tech stack:** [FastMCP](https://github.com/jlowin/fastmcp), Nuxeo Python client, FastAPI/Uvicorn, Docker.

## Repository Layout

```
nuxeo-mcp-server/
├── src/nuxeo_mcp/          # Package source
│   ├── server.py           # MCP server entry-point & FastMCP setup
│   ├── tools.py            # All 18 MCP tools
│   ├── resources.py        # MCP resources (nuxeo:// URIs)
│   ├── prompts.py          # MCP prompt templates
│   ├── nl_parser.py        # Natural-language → NXQL parser
│   ├── es_passthrough.py   # Elasticsearch passthrough
│   ├── es_query_builder.py # ES query builder
│   ├── search_filters.py   # Search filter helpers
│   ├── auth.py             # OAuth2 / Basic auth handlers
│   ├── middleware.py       # Authentication middleware
│   ├── config.py           # Configuration dataclasses & enums
│   ├── server_manager.py   # Multi-server management
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

20 tools registered via `register_tools(mcp, nuxeo, skip_server_selection=False)`:

| Tool | Description |
|------|-------------|
| `get_repository_info` | Repository metadata |
| `get_children` | List folder contents |
| `search` | Execute a raw NXQL query |
| `get_document_types` | Available document types |
| `get_schemas` | Available schemas |
| `get_operations` | Available Nuxeo operations |
| `execute_operation` | Execute a Nuxeo operation |
| `create_document` | Create a new document |
| `get_document` | Retrieve a document |
| `update_document` | Update document properties |
| `delete_document` | Delete a document |
| `move_document` | Move or rename a document |
| `natural_search` | Natural-language → NXQL search |
| `search_repository` | Elasticsearch passthrough search *(requires ES)* |
| `search_audit` | Audit log search — admin only *(requires ES)* |
| `list_servers` | List configured Nuxeo instances |
| `switch_server` | Switch the active instance |
| `get_current_server` | Current server info |
| `add_server` | Add a new Nuxeo server configuration |
| `remove_server` | Remove a Nuxeo server configuration |

**Adding a new tool:**

```python
# In tools.py, inside register_tools()
@mcp.tool(
    name="my_tool",
    description="What this tool does",
)
def my_tool(param: str) -> dict:
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
| `server.py` | Instantiates `FastMCP`, wires auth middleware, calls all `register_*()` functions |
| `tools.py` | Implements every MCP tool; delegates to the Nuxeo Python client |
| `resources.py` | Implements every MCP resource; formats documents for consumption |
| `prompts.py` | Defines reusable prompt templates |
| `config.py` | `NuxeoServerConfig`, `OAuth2Config`, `MCPAuthConfig` dataclasses; `AuthMethod` enum |
| `auth.py` | `OAuth2AuthHandler` (PKCE flow), `BasicAuthHandler`; browser-based callback server |
| `middleware.py` | `AuthenticationManager` wraps tool/resource callables to inject auth headers |
| `token_store.py` | `TokenManager` — persists and refreshes OAuth2 tokens |
| `server_manager.py` | `ServerManager` — tracks multiple Nuxeo instances, handles switching |
| `nl_parser.py` | `NaturalLanguageParser` converts English queries to NXQL via `NXQLBuilder` |
| `es_passthrough.py` | `ElasticsearchPassthrough` — forwards ES queries while enforcing Nuxeo ACLs |
| `es_query_builder.py` | `ElasticsearchQueryBuilder` — translates filter conditions to ES DSL |
| `search_filters.py` | Parses and applies search filter objects |
| `utility.py` | `format_document()`, UUID detection, blob helpers |

### Startup Sequence

```
__main__.py  →  main()
  └─ server.py: NuxeoMCPServer.__init__()
       ├─ config.py: read NUXEO_URL / NUXEO_AUTH_METHOD / credentials from env
       ├─ auth.py / middleware.py: build Nuxeo client (basic or OAuth2)
       ├─ server.py: create FastMCP instance + /health endpoint
       ├─ tools.py: register_tools()        ← ServerManager initialised here
       ├─ resources.py: register_resources()
       └─ prompts.py: register_prompts()
```

### Authentication Flow

```
Client request
  → AuthenticationManager.wrap()
      ├─ BasicAuthHandler  (NUXEO_AUTH_METHOD=basic)
      └─ OAuth2AuthHandler (NUXEO_AUTH_METHOD=oauth2)
           ├─ TokenManager: check stored token
           ├─ If expired: refresh_token()
           └─ If none: launch PKCE browser flow → callback server
```

Set `NUXEO_AUTH_METHOD=oauth2` (or `basic`) in the environment to select the authentication method.

### Natural Language Search

`NaturalLanguageParser` in `nl_parser.py` parses a free-text English query into a `ParsedQuery` dataclass (document type, properties, date ranges, full-text terms). `NXQLBuilder` then constructs a valid NXQL `SELECT` statement from the parsed result. The `natural_search` tool orchestrates these two steps.

### Elasticsearch Passthrough

`ElasticsearchPassthrough` in `es_passthrough.py` accepts an ES query dict, injects Nuxeo security filters (principal ACLs), and forwards the request to the Nuxeo ES endpoint. `ElasticsearchQueryBuilder` helps build the ES DSL from higher-level condition objects.

### Configuration via Environment Variables

| Variable | Purpose |
|----------|---------|
| `NUXEO_URL` | Nuxeo server URL (default: `http://localhost:8080/nuxeo`) |
| `NUXEO_USERNAME` | Username for Basic auth |
| `NUXEO_PASSWORD` | Password for Basic auth |
| `NUXEO_AUTH_METHOD` | `basic` or `oauth2` |
| `NUXEO_OAUTH_CLIENT_ID` | OAuth2 client ID |
| `NUXEO_OAUTH_CLIENT_SECRET` | OAuth2 client secret |
| `NUXEO_OAUTH_AUTH_ENDPOINT` | OAuth2 authorization endpoint |
| `NUXEO_OAUTH_TOKEN_ENDPOINT` | OAuth2 token endpoint |
| `NUXEO_OAUTH_OPENID_URL` | OpenID Connect configuration URL |
| `NUXEO_OAUTH_REDIRECT_PORT` | Local port for OAuth2 callback (default: auto) |
| `NUXEO_OAUTH_SCOPE` | OAuth2 scopes (default: `openid profile email`) |
| `SKIP_SERVER_SELECTION` | Set to `true` to skip the interactive server-selection prompt at startup |

### Server Transport Modes

The server binary (`nuxeo-mcp`) supports three transport modes:

```bash
nuxeo-mcp                          # stdio (default, for MCP clients)
nuxeo-mcp --http --port 8080       # Streamable-HTTP
nuxeo-mcp --sse  --port 8080       # SSE
nuxeo-mcp --oauth2                 # Enable OAuth2 auth (any transport)
nuxeo-mcp --oauth2 --no-browser    # OAuth2 without browser popup
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
- Don't bypass authentication middleware when adding new tools; all tools must go through `AuthenticationManager`.

### Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| mypy error on untyped third-party library | Add a `py.typed` stub or use `# type: ignore[import]` with a comment |
| Integration test runs in unit CI | Ensure the test is decorated with `@pytest.mark.integration` |
| OAuth2 token not refreshed | Check `TokenManager.get_valid_token()` — it handles refresh automatically |
| Tool not appearing in MCP client | Verify it is registered inside `register_tools()`, not at module level |
| NXQL syntax error from natural_search | Test the query via `NaturalLanguageParser` directly before wiring to the tool |

### Dependency Management

```bash
uv add <package>                  # Add runtime dependency
uv add --optional dev <package>   # Add dev-only dependency
uv lock                           # Regenerate lock file
uv lock --upgrade                 # Upgrade all dependencies
```

Always commit both `pyproject.toml` and `uv.lock` together.
