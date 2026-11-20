#!/usr/bin/env bash
set -euxo pipefail

# The uv image the Dockerfile pins by digest: CI runs the same verified binary.
uv_image=$(sed -nE 's|^FROM (ghcr.io/astral-sh/uv:[^ ]+@sha256:[0-9a-f]{64}) AS uv$|\1|p' Dockerfile)
python_version=$(sed -n 's|^FROM .*/python:\([0-9]*\.[0-9]*\.[0-9]*\)[-@].*|\1|p' Dockerfile | sort -u)
# One version for both stages: none, or a mismatch, must fail here.
if [[ ! "$python_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Dockerfile: expected one Python X.Y.Z across the FROM lines, got: '${python_version//$'\n'/, }'" >&2
  exit 1
fi
if [[ -z "$uv_image" || "$uv_image" == *$'\n'* ]]; then
  echo "Dockerfile: expected one uv image pinned by digest, got: '${uv_image//$'\n'/, }'" >&2
  exit 1
fi

# Later steps find uv through the pipeline PATH and the interpreter through .venv.
mkdir -p .ci-bin
container=$(docker create "$uv_image" /uv)
trap 'docker rm "$container" >/dev/null' EXIT
docker cp "$container:/uv" .ci-bin/uv
export PATH="$PWD/.ci-bin:$PATH"
uv sync --frozen --extra dev --python "$python_version"
# Both distributions share jwt/; Nuxeo needs the JWT/jwk_from_dict API.
uv pip install 'jwt==1.4.0' --force-reinstall
