# (C) Copyright 2026 Hyland (https://hyland.com/) and others.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pytest options and connection fixtures for an externally provisioned Nuxeo."""

import os
from typing import List, Tuple

import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.nodes import Item


def pytest_addoption(parser: Parser) -> None:
    """Keep live-server tests opt-in."""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests against an existing, seeded Nuxeo server",
    )
    parser.addoption(
        "--no-integration",
        action="store_true",
        default=False,
        help="Skip integration tests",
    )


def pytest_collection_modifyitems(config: Config, items: List[Item]) -> None:
    """Exclude live-server tests unless explicitly enabled."""
    if not config.getoption("--integration") or config.getoption("--no-integration"):
        skip = pytest.mark.skip(reason="Need --integration option to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def nuxeo_url() -> str:
    """Return the URL of the externally provisioned Nuxeo server."""
    return os.environ.get("NUXEO_URL", "http://localhost:8080/nuxeo")


@pytest.fixture(scope="session")
def nuxeo_credentials() -> Tuple[str, str]:
    """Return the administrator credentials for the integration-test server."""
    return (
        os.environ.get("NUXEO_USERNAME", "Administrator"),
        os.environ.get("NUXEO_PASSWORD", "Administrator"),
    )
