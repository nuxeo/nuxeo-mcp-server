"""
Pytest configuration for Nuxeo MCP Server tests.

This module provides fixtures for setting up and tearing down a Nuxeo server
using Docker for testing purposes.
"""

import os
import subprocess
import sys
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union, cast

import docker
import pytest
import requests
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.nodes import Item


# Add command line options for integration tests and Docker configuration
def pytest_addoption(parser: Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that require external services like Nuxeo",
    )
    parser.addoption(
        "--no-integration",
        action="store_true",
        default=False,
        help="Skip integration tests",
    )
    parser.addoption(
        "--rancher",
        action="store_true",
        default=False,
        help="Use Rancher Desktop Docker socket",
    )


# Skip integration tests unless --integration is specified
def pytest_configure(config: Config) -> None:
    config.addinivalue_line("markers", "integration: mark test as integration test")


def pytest_collection_modifyitems(config: Config, items: List[Item]) -> None:
    # Skip integration tests if --integration is not specified or --no-integration is specified
    if not config.getoption("--integration") or config.getoption("--no-integration"):
        skip_integration = pytest.mark.skip(reason="Need --integration option to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


@pytest.fixture(scope="session")
def docker_client(request: pytest.FixtureRequest) -> docker.DockerClient:
    """
    Create a Docker client.

    This fixture creates a Docker client based on the environment:
    - If --rancher is specified or USE_RANCHER environment variable is set,
      it uses the Rancher Desktop Docker socket.
    - Otherwise, it uses the default Docker socket.
    """
    # Check if we should use Rancher Desktop Docker socket
    use_rancher = request.config.getoption("--rancher") or os.environ.get(
        "USE_RANCHER", ""
    ).lower() in ("true", "1", "yes")

    if use_rancher:
        # Use the Docker socket location for Rancher Desktop
        print("Using Rancher Desktop Docker socket", flush=True)
        socket = os.environ.get(
            "RANCHER_DOCKER_SOCKET", os.path.expanduser("~/.rd/docker.sock")
        )
        return docker.DockerClient(base_url=f"unix://{socket}")
    else:
        # Use the default Docker socket location
        print("Using default Docker socket", flush=True)
        return docker.DockerClient()


# Get the Nuxeo Docker image from environment variable or use default
NUXEO_DOCKER = os.environ.get(
    "NUXEO_DOCKER_IMAGE",
    # Embedded OpenSearch, search client and audit: the search tools need them.
    "docker-private.packages.nuxeo.com/nuxeo/nuxeo-mcp-demo:2025",
)


@pytest.fixture(scope="session")
def nuxeo_container(
    request: pytest.FixtureRequest,
) -> Generator[Optional[docker.models.containers.Container], None, None]:
    """
    Start a Nuxeo container for testing.

    This fixture starts a Nuxeo container using Docker, waits for it to be ready,
    and then yields the container. After the tests are done, it stops and removes
    the container.
    """
    # Skip if not running integration tests
    if not request.config.getoption("--integration"):
        yield None
        return

    # NUXEO_URL targets an existing server: no container, no seeding.
    if os.environ.get("NUXEO_URL"):
        yield None
        return

    # Requested only now: an existing server must not need a Docker daemon.
    docker_client: docker.DockerClient = request.getfixturevalue("docker_client")

    # Pull the Nuxeo image if needed
    try:
        docker_client.images.get(NUXEO_DOCKER)
    except docker.errors.ImageNotFound:
        print("Pulling Nuxeo Docker image (this may take a while)...")
        docker_client.images.pull(NUXEO_DOCKER)

    # Start the container
    container = docker_client.containers.run(
        NUXEO_DOCKER,
        detach=True,
        ports={"8080/tcp": 8080},
        environment={
            "NUXEO_DEV_MODE": "false",
            # The nuxeo-mcp-demo image reads it in nuxeo.conf; unused by the tests.
            "NUXEO_JWT_SECRET": "integration-tests",
        },
        name="nuxeo-mcp-test",
        remove=True,
    )

    # Wait for 60 seconds to give Nuxeo time to initialize before checking endpoints
    print("Waiting 2 seconds for initial Nuxeo startup...", flush=True)
    time.sleep(2)

    # Wait for Nuxeo to be ready
    # Embedded OpenSearch makes the startup much slower than plain Nuxeo.
    max_retries = 36
    retry_interval = 5
    nuxeo_ready = False

    print("Waiting for Nuxeo to start...", flush=True)
    for i in range(max_retries):
        try:
            # Try different endpoints to check if Nuxeo is responding
            endpoints = ["http://localhost:8080/nuxeo/runningstatus"]

            for endpoint in endpoints:
                try:
                    print(f"Trying endpoint: {endpoint}", flush=True)
                    response = requests.get(endpoint, timeout=5)
                    print(f"Response status: {response.status_code}", flush=True)

                    if response.status_code == 200:
                        nuxeo_ready = True
                        print(
                            f"Nuxeo is ready after {i * retry_interval} seconds (endpoint: {endpoint})",
                            flush=True,
                        )
                        break
                except requests.exceptions.RequestException as e:
                    print(f"Error connecting to {endpoint}: {e}", flush=True)

            if nuxeo_ready:
                break
        except requests.exceptions.RequestException:
            pass

        print(f"Waiting for Nuxeo to start ({i + 1}/{max_retries})...", flush=True)
        # Print container logs to help diagnose issues
        time.sleep(retry_interval)

    if not nuxeo_ready:
        container.stop()
        pytest.fail("Nuxeo failed to start within the expected time")

    # Run the seed_nuxeo.py script to initialize the repository
    print("Initializing Nuxeo repository with sample documents...", flush=True)
    try:
        # Get the Nuxeo URL and credentials
        nuxeo_url_value = os.environ.get("NUXEO_URL", "http://localhost:8080/nuxeo")
        # For Docker-based integration tests, use default Administrator credentials
        # since this is a local test container
        username = os.environ.get("NUXEO_USERNAME", "Administrator")
        password = os.environ.get("NUXEO_PASSWORD", "Administrator")

        # Run the seed_nuxeo.py script
        result = subprocess.run(
            [
                sys.executable,
                "seed_nuxeo.py",
                "--url",
                nuxeo_url_value,
                "--username",
                username,
                "--password",
                password,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        print("Seed script output:", flush=True)
        print(result.stdout, flush=True)

        # Check if the seed script was successful
        if (
            "Successfully seeded Nuxeo repository with sample documents"
            not in result.stdout
        ):
            print(
                "Warning: Seed script may not have completed successfully", flush=True
            )
            print("Error output:", flush=True)
            print(result.stderr, flush=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running seed script: {e}", flush=True)
        print("Error output:", flush=True)
        print(e.stderr, flush=True)
        pytest.fail("Failed to initialize Nuxeo repository with sample documents")
    except Exception as e:
        print(f"Unexpected error running seed script: {e}", flush=True)
        pytest.fail(f"Unexpected error initializing Nuxeo repository: {e}")

    # Yield the container for tests to use
    yield container

    # Stop and remove the container after tests
    print("Stopping Nuxeo container...", flush=True)
    try:
        container.stop()
    except docker.errors.NotFound:
        print("Container no longer exists.")


@pytest.fixture(scope="session")
def nuxeo_url() -> str:
    """Get the URL of the Nuxeo server."""
    return os.environ.get("NUXEO_URL", "http://localhost:8080/nuxeo")


@pytest.fixture(scope="session")
def nuxeo_credentials() -> Tuple[str, str]:
    """Get the credentials for the Nuxeo server."""
    # For Docker-based integration tests, use default Administrator credentials
    # since this is a local test container
    username = os.environ.get("NUXEO_USERNAME", "Administrator")
    password = os.environ.get("NUXEO_PASSWORD", "Administrator")
    return username, password
