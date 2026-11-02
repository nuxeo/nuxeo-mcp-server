# Nuxeo MCP Server tests

## Unit tests

No Nuxeo server needed; the Nuxeo client is mocked.

```bash
uv run pytest tests/ -v --no-integration
```

## Integration tests

Marked `@pytest.mark.integration`, run with `--integration`.

By default they start the `nuxeo-mcp-demo:2025` image (Nuxeo with embedded
OpenSearch, see `ci/docker/nuxeo`) and seed it with `seed_nuxeo.py`. Override the
image with `NUXEO_DOCKER_IMAGE`.

```bash
uv run pytest tests/ -v --integration
```

To run against an existing server instead, set `NUXEO_URL`: no container is
started and nothing is seeded. Use an administrator account.

```bash
NUXEO_URL=http://localhost:8080/nuxeo NUXEO_USERNAME=Administrator \
NUXEO_PASSWORD=Administrator uv run pytest tests/test_all_tools_integration.py --integration
```

`test_all_tools_integration.py` calls every tool, and works in its own workspace,
deleted at the end: it is safe on a server holding real content. The other
integration tests expect the seeded data, so they only pass on the container.

On Rancher Desktop, pass `--rancher` (or set `USE_RANCHER=true`); the socket
defaults to `~/.rd/docker.sock`, override it with `RANCHER_DOCKER_SOCKET`.
