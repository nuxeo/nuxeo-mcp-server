# Build and integration-test infrastructure

`setup.sh` installs the uv version pinned in the root Dockerfile and uses its
pinned Python version, then applies the JWT namespace repair required by the
Nuxeo client.

The root `skaffold.yaml` builds and pushes an attested `linux/amd64` +
`linux/arm64` image through the Kubernetes Buildx builder. Tests pin the
multi-platform index digest pushed by the build. `main` promotes that digest with
`skopeo copy --all --preserve-digests`, including the attestation manifests in
the index.

## LTS test environments

Each of Nuxeo 2023, 2025 and 2027 gets its own namespace, test image tag and
Helmfile cache. `docker/` builds `nuxeo-mcp-tests` on the corresponding Nuxeo
image, with FFmpeg and Web UI. Nuxeo 2023 needs no extra search or audit package;
2025 adds the OpenSearch 1 search client and audit packages, and 2027 the
OpenSearch 3 ones to match its base Helm stack. OpenSearch is external, so the
embedded package is omitted.

LTS bases are selected through the `2023`, `2025` and `2027` tags. The pipeline
resolves their `org.nuxeo.version` label and builds on that fixed version to keep
the image and package platform aligned.

`helm/helmfile.yaml.gotmpl` loads the base Helm stack from the `nuxeo-lts` tag
matching the Nuxeo image version, and enables MongoDB, Kafka, OpenSearch and
Nuxeo. The `helm/charts/mcp` chart deploys the image under test. Helmfile waits
for both; the pipeline then seeds Nuxeo, runs HTTP smoke tests against MCP and
runs the Python integration suite against Nuxeo. The shared deployment wrapper
collects logs and tears down the namespace, including when a test fails.

For local development, `docker-compose.yml` remains available. Its plain Nuxeo
image does not include all packages and services required by the integration
suite; use a fully provisioned server as described in `tests/README.md`.
