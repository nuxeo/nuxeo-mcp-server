# Developer Guide

How to build, test and extend the Nuxeo MCP Server. [AGENTS.md](AGENTS.md)
holds the code layout, module responsibilities and conventions.

## Setup

Install [uv](https://docs.astral.sh/uv/), then the dependencies, dev extras
included, from the lock file:

```bash
git clone https://github.com/nuxeo/nuxeo-mcp-server.git
cd nuxeo-mcp-server
uv sync --frozen --extra dev
```

uv creates `.venv`. Without uv: `python -m venv .venv`, activate it, then
`pip install -e ".[dev]"` (no lock file).

## Build

```bash
uv build          # sdist and wheel in dist/
docker build -t nuxeo-mcp-server .
```

## Tests

```bash
uv run pytest tests/ -v --no-integration   # unit, Nuxeo mocked
uv run pytest tests/ -v --integration      # starts a Nuxeo container
```

Integration tests run against the `nuxeo-mcp-demo:2025` image (Nuxeo with
embedded OpenSearch, built from [ci/docker/nuxeo](ci/docker/nuxeo/README.md)),
or against an existing server with `NUXEO_URL`. See
[tests/README.md](tests/README.md). Add `-s --log-cli-level=INFO` for live output.

`seed_nuxeo.py` creates the sample folder, File, Note and Picture the integration
tests read:

```bash
uv run python seed_nuxeo.py --url http://localhost:8080/nuxeo \
  --username Administrator --password Administrator
```

## Checks

CI fails on any of these:

```bash
uv run black src/ tests/
uv run isort src/ tests/
uv run mypy src/
uv run python scripts/generate_tool_reference.py --check
```

The last one checks the generated tool tables in `AGENTS.md` and `USAGE.md`. After changing a tool name, description or annotation, regenerate
them with `uv run python scripts/generate_tool_reference.py`.

## Adding a Tool

1. Declare its safety hints in `src/nuxeo_mcp/annotations.py`; registration
   fails at startup without them.
2. Register it in `register_tools()` in `src/nuxeo_mcp/tools.py` through the
   `tool()` wrapper, named `nuxeo_{verb}_{object}`. See the example in
   [AGENTS.md](AGENTS.md#mcp-surface).
3. Add unit tests, and a call in `tests/test_all_tools_integration.py`: it
   fails when a registered tool is never called.
4. Regenerate the tool reference.

Resources (`nuxeo://` URIs) are registered in `register_resources()` in
`src/nuxeo_mcp/resources.py`.

## Dependencies

```bash
uv add <package>                  # runtime
uv add --optional dev <package>   # dev only
uv lock --upgrade                 # upgrade within pyproject.toml bounds
```

Commit `pyproject.toml` and `uv.lock` together.

## CI Workflows

All use the `.github/actions/setup-and-install-dep` composite action:

| Workflow | What it does |
|---|---|
| `build-and-unit-tests.yml` | `uv build`, the checks above, unit tests |
| `integration-tests.yml` | Integration tests against the `nuxeo-mcp-demo:2025` image |
| `package-docker-image.yml` | Builds the image, smoke-tests it with `mcp_client.py`, pushes it from `main` |
| `updatecli.yml` | Scheduled dependency updates |
