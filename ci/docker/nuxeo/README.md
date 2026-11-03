# Nuxeo Docker image for MCP demo server

Build the image:

```bash
CLID=something docker buildx build --platform linux/amd64 --secret id=CLID --tag docker-private.packages.nuxeo.com/nuxeo/nuxeo-mcp-demo:2025 --push .
```

The image integrates a nuxeo.conf file that retrieves the environment variable `NUXEO_JWT_SECRET` to configure 
`nuxeo.jwt.secret`.

The image adds to the base Nuxeo image: embedded OpenSearch 1 with its search
client and audit backend (needed by the Query DSL and audit tools), showcase
content, Web UI and ffmpeg. It is the default image of the integration tests
and of `docker-compose-demo.yml`.

It is x86 only, so every converter is present; on ARM it runs emulated and
starts much slower (about 80 s, against 4 s for the base image).
