# Nuxeo MCP Server tests

## Unit tests

No Nuxeo server is needed; the Nuxeo client is mocked.

```bash
uv run pytest tests/ -v --no-integration
```

## Integration tests

Tests marked `@pytest.mark.integration` run with `--integration` against an
existing Nuxeo server. They neither provision services nor seed the repository.
Use a test server with an administrator account, OpenSearch search and audit
backends, the search passthrough and Web UI. Picture conversions
also need the server's conversion tools, including FFmpeg.

```bash
export NUXEO_URL=http://localhost:8080/nuxeo
export NUXEO_USERNAME=Administrator
export NUXEO_PASSWORD=Administrator
uv run python seed_nuxeo.py --url "$NUXEO_URL" \
  --username "$NUXEO_USERNAME" --password "$NUXEO_PASSWORD"
uv run pytest tests/ -v --integration
```

The URL defaults to `http://localhost:8080/nuxeo`; credentials default to
`Administrator` / `Administrator` for local test servers.

`test_all_tools_integration.py` creates its own workspace and deletes it on
teardown. It can run independently without seeding:

```bash
uv run pytest tests/test_all_tools_integration.py -v --integration
```

The other document integration tests expect the data created by `seed_nuxeo.py`.
CI provisions and seeds separate Nuxeo 2023, 2025 and 2027 environments.
