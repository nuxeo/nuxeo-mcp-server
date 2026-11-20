# Base images are pinned by tag and digest. Docker Hardened Images need a
# Docker account: `docker login dhi.io`, or point BASE_REGISTRY at a proxy of it.
ARG BASE_REGISTRY=dhi.io

FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv

# Runtime base: no shell, no package manager.
FROM ${BASE_REGISTRY}/python:3.13.18-alpine@sha256:c4717b7ca3151a64ff896e5c0240fa79739297b8666b576ef461fa3b1d373ab6 AS runtime-base

# Build stage: the -dev variant of the runtime image, with a shell and the same
# interpreter at the same path, which the virtual environment links to.
FROM ${BASE_REGISTRY}/python:3.13.18-alpine-dev@sha256:17c498055ee6e005d5b8e7331d40ef0fcf4a16ec5251dd98dc97daf176c89158 AS build

WORKDIR /app

# UV_LINK_MODE=copy required since hardlinks don't work across Docker layers.
# The image's interpreter only: a downloaded one would be missing at runtime.
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Copy dependency manifests and install dependencies without the project.
# Keeping this layer separate from the source allows Docker to cache it and skip
# dependency installation when only application source changes.
COPY pyproject.toml uv.lock ./
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy application source and install the project.
# jwt 1.4.0 (python-jwt) and pyjwt both install to the jwt/ namespace;
# nuxeo[oauth2] needs jwt 1.4.0's JWT/jwk_from_dict; force it to win.
COPY src ./src/
# Declared in pyproject.toml license-files: the build fails without them.
COPY LICENSE NOTICE ./
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev && \
    uv pip install "jwt==1.4.0" --force-reinstall

# The runtime image has no useradd: add the nuxeo user to its own passwd here.
COPY --from=runtime-base /etc/passwd /tmp/passwd
RUN echo 'nuxeo:x:1200:0:nuxeo:/app:/usr/sbin/nologin' >> /tmp/passwd

FROM runtime-base

ARG SCM_REF=unknown
ARG VERSION=0.1.0
LABEL org.opencontainers.image.title="Nuxeo MCP Server" \
      org.opencontainers.image.description="MCP server for Nuxeo Content Repository" \
      org.opencontainers.image.url="https://github.com/nuxeo/nuxeo-mcp-server" \
      org.opencontainers.image.source="https://github.com/nuxeo/nuxeo-mcp-server" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.revision=$SCM_REF \
      org.opencontainers.image.version=$VERSION

# Group 0 owns the files so the image also runs under a random uid (OpenShift).
COPY --from=build /tmp/passwd /etc/passwd
COPY --from=build --chown=nuxeo:0 /app /app
USER nuxeo
WORKDIR /app

# Add the virtual environment to PATH (uv is not present in the final image)
ENV PATH="/app/.venv/bin:$PATH"

# Expose the HTTP port
EXPOSE 8181

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV MCP_PORT=8181
ENV MCP_HOST=0.0.0.0

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; opener = urllib.request.build_opener(urllib.request.ProxyHandler({})); opener.open('http://localhost:' + os.environ['MCP_PORT'] + '/health', timeout=5).close()"]

# nuxeo-mcp reads MCP_PORT and MCP_HOST, and rejects a removed MCP_MODE.
ENTRYPOINT ["nuxeo-mcp", "--http"]
