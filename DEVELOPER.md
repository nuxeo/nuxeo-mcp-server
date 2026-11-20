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
uv pip install 'jwt==1.4.0' --force-reinstall
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
uv run pytest tests/ -v --integration      # existing, seeded Nuxeo server
```

Integration tests use an existing server selected with `NUXEO_URL`. Provision and
seed it before running the suite; the tests do not start containers. See
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

## Continuous integration

Pull requests and `main` run packaging, static checks and unit tests, then build
the multi-platform image with SBOM and provenance. Smoke and integration tests
run against Nuxeo 2023, 2025 and 2027 in independent Kubernetes environments.
Successful `main` builds promote the tested image to the snapshot registry.

The package version stays at `0.1.0`; snapshot image tags identify builds.
`updatecli.yml` remains in GitHub Actions for scheduled Python and uv updates.
The [CI notes](ci/README.md) describe infrastructure configuration.
