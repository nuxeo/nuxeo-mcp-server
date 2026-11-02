# Nuxeo Docker image for MCP demo server

Build the image:

```bash
CLID=something docker buildx build --platform linux/amd64 --secret id=CLID --tag docker-private.packages.nuxeo.com/nuxeo/nuxeo-mcp-demo:2025 --push .
```

The image integrates a nuxeo.conf file that retrieve the environment variable `NUXEO_JWT_SECRET` to configure 
`nuxeo.jwt.secret`.
