"""Resources, templates and prompts, discovered through a real MCP client.

Tools are covered the same way in test_tool_contracts.py. Nuxeo is mocked.
Suggested by #9.
"""

import asyncio
import json
from typing import Any, Awaitable, Callable
from unittest.mock import MagicMock

import pytest
from fastmcp import Client, FastMCP

from nuxeo_mcp.prompts import register_prompts
from nuxeo_mcp.resources import register_resources
from nuxeo_mcp.tools import register_tools


@pytest.fixture
def mcp() -> FastMCP:
    """A real FastMCP server with everything registered against a mocked Nuxeo."""
    nuxeo = MagicMock()
    nuxeo.client.host = "http://nuxeo.test/nuxeo/"
    nuxeo.client.server_info.return_value = {"productVersion": "2025.1"}
    server = FastMCP("test")
    register_tools(server, nuxeo)
    register_resources(server, nuxeo)
    register_prompts(server, nuxeo)
    return server


def _with_client(mcp: FastMCP, action: Callable[[Client], Awaitable[Any]]) -> Any:
    async def run() -> Any:
        async with Client(mcp) as client:
            return await action(client)

    return asyncio.run(run())


@pytest.mark.unit
def test_static_resources_are_listed(mcp: FastMCP) -> None:
    resources = _with_client(mcp, lambda c: c.list_resources())

    assert {str(r.uri) for r in resources} >= {
        "nuxeo://info",
        "nuxeo://nxql-guide",
        "nuxeo://query-dsl-guide",
        "nuxeo://audit-query-dsl-guide",
    }


@pytest.mark.unit
def test_document_resource_templates_are_listed(mcp: FastMCP) -> None:
    templates = _with_client(mcp, lambda c: c.list_resource_templates())

    assert {t.uri_template for t in templates} >= {
        "nuxeo://{uid}",
        "nuxeo://{path*}",
        "nuxeo://{uid}@{adapter}/{adapter_param}",
    }


@pytest.mark.unit
def test_prompts_are_listed(mcp: FastMCP) -> None:
    prompts = _with_client(mcp, lambda c: c.list_prompts())

    assert "list_doc_by_type" in {p.name for p in prompts}


@pytest.mark.unit
def test_info_resource_reads_as_json(mcp: FastMCP) -> None:
    contents = _with_client(mcp, lambda c: c.read_resource("nuxeo://info"))

    info = json.loads(contents[0].text)
    assert info["connected"] is True
    assert info["version"] == "2025.1"
    assert info["url"] == "http://nuxeo.test/nuxeo/"
