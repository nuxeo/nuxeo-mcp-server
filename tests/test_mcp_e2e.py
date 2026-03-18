"""
End-to-end MCP protocol tests.

These tests exercise the full MCP transport layer using FastMCP's in-process
Client.  Unlike other tests that call tool functions directly, these go through
the real MCP serialisation → dispatch → response cycle:

    FastMCP Client  ──(MCP protocol)──►  FastMCP Server  ──►  tool/resource fn

A mocked Nuxeo client is injected so no Docker or live server is required.
"""

import pytest
from unittest.mock import MagicMock, patch

from fastmcp import Client, FastMCP

from nuxeo_mcp.tools import register_tools
from nuxeo_mcp.resources import register_resources
from nuxeo_mcp.prompts import register_prompts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_mock_nuxeo() -> MagicMock:
    """Create a realistic Nuxeo client mock."""
    nuxeo = MagicMock()
    nuxeo.client.host = "http://localhost:8080/nuxeo"

    # server_info — used by get_repository_info and nuxeo://info
    nuxeo.client.server_info.return_value = {
        "productName": "Nuxeo Platform",
        "productVersion": "2025.1",
        "distributionName": "server",
        "distributionVersion": "25.0.0",
        "vendorName": "Nuxeo",
    }

    # documents.query — used by search and get_children
    nuxeo.documents.query.return_value = {
        "resultsCount": 0,
        "pageIndex": 0,
        "pageCount": 0,
        "entries": [],
    }

    # document_types — used by get_document_types
    nuxeo.client.request.return_value = MagicMock(
        status_code=200,
        json=lambda: {"doctypes": {"File": {}, "Folder": {}}},
    )

    return nuxeo


def _create_mcp_server() -> FastMCP:
    """Create a fully wired FastMCP server with a mocked Nuxeo backend.

    Patches ``nuxeo.client.Nuxeo`` to avoid a pre-existing JWT import error
    in the nuxeo library on Python 3.14.
    """
    mcp = FastMCP("nuxeo-mcp-test")
    nuxeo = _build_mock_nuxeo()

    # register_tools does `from nuxeo.client import Nuxeo` internally for
    # the switch_server flow.  The nuxeo library has a broken JWT import on
    # Python 3.14, so we patch it with a factory that returns our mock.
    mock_nuxeo_cls = MagicMock(return_value=nuxeo)
    with patch.dict("sys.modules", {"nuxeo.client": MagicMock(Nuxeo=mock_nuxeo_cls)}):
        register_tools(mcp, nuxeo, skip_server_selection=True)

    register_resources(mcp, nuxeo)
    register_prompts(mcp, nuxeo)

    return mcp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.anyio
async def test_tool_discovery_via_mcp_protocol() -> None:
    """MCP Client can discover registered tools through the protocol."""
    mcp = _create_mcp_server()

    async with Client(mcp) as client:
        tools = await client.list_tools()
        tool_names = [t.name for t in tools]

        # Verify core tools are discoverable
        assert "get_repository_info" in tool_names
        assert "search" in tool_names
        assert "get_children" in tool_names
        assert "create_document" in tool_names
        assert "get_document" in tool_names
        assert "update_document" in tool_names
        assert "delete_document" in tool_names


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_tool_via_mcp_protocol() -> None:
    """MCP Client can invoke a tool and receive a response through the protocol."""
    mcp = _create_mcp_server()

    async with Client(mcp) as client:
        result = await client.call_tool("get_repository_info", {})

        # CallToolResult wraps a list of content blocks
        assert result is not None
        assert hasattr(result, "content")
        assert len(result.content) > 0


@pytest.mark.unit
@pytest.mark.anyio
async def test_resource_discovery_via_mcp_protocol() -> None:
    """MCP Client can discover registered resources through the protocol."""
    mcp = _create_mcp_server()

    async with Client(mcp) as client:
        resources = await client.list_resources()
        resource_uris = [str(r.uri) for r in resources]

        assert "nuxeo://info" in resource_uris


@pytest.mark.unit
@pytest.mark.anyio
async def test_read_resource_nuxeo_info_via_mcp_protocol() -> None:
    """MCP Client can read the nuxeo://info resource through the protocol."""
    mcp = _create_mcp_server()

    async with Client(mcp) as client:
        result = await client.read_resource("nuxeo://info")

        assert result is not None
        # read_resource returns a list of ResourceContents
        import json

        content = result[0] if isinstance(result, list) else result
        text = content.text if hasattr(content, "text") else str(content)
        data = json.loads(text)
        assert data["connected"] is True
        assert "version" in data
        assert "url" in data


@pytest.mark.unit
@pytest.mark.anyio
async def test_prompt_discovery_via_mcp_protocol() -> None:
    """MCP Client can discover registered prompts through the protocol."""
    mcp = _create_mcp_server()

    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        prompt_names = [p.name for p in prompts]

        assert len(prompt_names) > 0
        assert "list_doc_by_type" in prompt_names


@pytest.mark.unit
@pytest.mark.anyio
async def test_resource_template_discovery_via_mcp_protocol() -> None:
    """MCP Client can discover resource templates (parameterised URIs)."""
    mcp = _create_mcp_server()

    async with Client(mcp) as client:
        templates = await client.list_resource_templates()
        template_uris = [str(t.uriTemplate) for t in templates]

        # Parameterised resources should appear as templates
        assert any("{uid}" in uri for uri in template_uris)
