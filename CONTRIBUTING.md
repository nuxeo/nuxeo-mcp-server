# Contributing to the Nuxeo MCP Server

Thank you for your interest in contributing to the Nuxeo MCP Server!

## Contributor License Agreement (CLA)

Before Hyland can accept any contribution (code, tests, or documentation),
you must sign Hyland's Contributor License Agreement (CLA), modeled on the
Apache Software Foundation's CLA. This grants Hyland the rights needed to
distribute your contribution while you retain ownership of your work.

Hyland offers an Individual CLA, and a Corporate CLA for work done for an
employer. You do not need to sign anything before opening a pull request:
if the maintainers want to merge it, they will contact you with the CLA that
applies. A pull request is merged only after the signed CLA is on file, and
signing does not oblige Hyland to accept the contribution.

## Getting Started

1. Fork the repository and create a feature branch from `main`.
2. Install Python 3.11+ and [uv](https://docs.astral.sh/uv/), then the
   development dependencies:

   ```bash
   uv sync --frozen --extra dev
   ```

3. Run the unit tests (no Nuxeo server needed):

   ```bash
   uv run pytest tests/ --no-integration
   ```

4. Run the checks CI runs before committing:

   ```bash
   uv run black src/ tests/
   uv run isort src/ tests/
   uv run mypy src/
   uv run python scripts/generate_tool_reference.py --check
   ```

Integration tests need Docker or an existing Nuxeo server; see
[tests/README.md](tests/README.md). [DEVELOPER.md](DEVELOPER.md) and
[AGENTS.md](AGENTS.md) describe the code layout and conventions.

## Submitting Changes

- Keep pull requests focused on a single change/topic.
- Include unit tests for new behavior and update documentation (README,
  USAGE) where relevant. A new tool also needs its safety annotations and a
  call in `tests/test_all_tools_integration.py`.
- Ensure the unit tests and the checks above pass locally before opening a PR.
- Describe the motivation and context for the change in the PR description.

## Reporting Issues

Please use GitHub Issues to report bugs or request features. Include steps
to reproduce, expected vs. actual behavior, and the MCP server and Nuxeo
versions.

## Code of Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By
participating, you are expected to uphold it.

## Security Issues

Do not report security vulnerabilities via public GitHub issues. See
[SECURITY.md](SECURITY.md) for our responsible disclosure process.
