FROM python:3.10-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy only the pyproject.toml file first to leverage Docker cache
COPY pyproject.toml .

# Copy the application
COPY . .

# Install the packaging module (required by nuxeo), uvicorn (for HTTP mode), and the package with its dependencies
RUN pip install --no-cache-dir packaging uvicorn && pip install --no-cache-dir -e .

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
