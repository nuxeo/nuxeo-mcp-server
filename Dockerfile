ARG PYTHON_VERSION=3.10.20
FROM python:${PYTHON_VERSION}-slim

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Configure user
ENV NUXEO_USER=nuxeo
RUN useradd --create-home --home /app --uid 1200 --gid root --no-user-group --shell /bin/bash $NUXEO_USER
USER $NUXEO_USER

WORKDIR /app

# UV_LINK_MODE=copy required since hardlinks don't work across Docker layers
ENV UV_LINK_MODE=copy

# Copy dependency manifests and install dependencies without the project.
# Keeping this layer separate from the source allows Docker to cache it and skip
# dependency installation when only application source changes.
COPY --chown=$NUXEO_USER:0 pyproject.toml uv.lock ./
RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/app/.cache/uv,uid=1200 \
    uv sync --frozen --no-dev --no-install-project

# Copy application source and install the project.
# jwt 1.4.0 (python-jwt) and pyjwt both install to the jwt/ namespace;
# nuxeo[oauth2] needs jwt 1.4.0's JWT/jwk_from_dict; force it to win.
COPY --chown=$NUXEO_USER:0 src ./src/
RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/app/.cache/uv,uid=1200 \
    uv sync --locked --no-dev && \
    uv pip install "jwt==1.4.0" --force-reinstall

# Add the virtual environment to PATH (uv is not present in the final image)
ENV PATH="/app/.venv/bin:$PATH"

# Expose the HTTP port
EXPOSE 8181

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV MCP_MODE=http
ENV MCP_PORT=8181
ENV MCP_HOST=0.0.0.0

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:${MCP_PORT}/health || exit 1

# Copy the entrypoint, and use it
COPY --chown=$NUXEO_USER:0 --chmod=+x Dockerfile-entrypoint.sh entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
