"""
Basic tests for the Nuxeo MCP Server project.

These tests verify that the project is set up correctly without
requiring a connection to a Nuxeo server.
"""

import os
import sys
from typing import Any

import pytest


@pytest.mark.unit
def test_project_structure() -> None:
    """Test that the project structure is set up correctly."""
    # Check that the src directory exists
    assert os.path.isdir("src"), "src directory should exist"

    # Check that the nuxeo_mcp package exists
    assert os.path.isdir("src/nuxeo_mcp"), "src/nuxeo_mcp directory should exist"

    # Check that the main module files exist
    assert os.path.isfile("src/nuxeo_mcp/__init__.py"), "__init__.py should exist"
    assert os.path.isfile("src/nuxeo_mcp/server.py"), "server.py should exist"
    assert os.path.isfile("src/nuxeo_mcp/__main__.py"), "__main__.py should exist"

    # Check that the tests directory exists
    assert os.path.isdir("tests"), "tests directory should exist"

    # Check that the test files exist
    assert os.path.isfile("tests/conftest.py"), "conftest.py should exist"
    assert os.path.isfile("tests/test_server.py"), "test_server.py should exist"

    # Check that the project configuration files exist
    assert os.path.isfile("pyproject.toml"), "pyproject.toml should exist"
    assert os.path.isfile("README.md"), "README.md should exist"


@pytest.mark.unit
def test_package_version() -> None:
    """Test that the package version is set correctly."""
    # Import the package
    import nuxeo_mcp

    # Check that the version is set
    assert hasattr(nuxeo_mcp, "__version__"), "__version__ should be defined"
    assert nuxeo_mcp.__version__ == "0.1.0", "__version__ should be 0.1.0"
