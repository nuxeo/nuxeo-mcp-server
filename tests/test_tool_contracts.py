"""
Contract tests for MCP tools, exercised through a real FastMCP server.

The other unit tests call the tool functions captured by MockFastMCP, which
bypasses FastMCP's output-schema generation and result validation. FastMCP
validates a tool's result against its declared return annotation, so a wrong
annotation only fails here -- these tests are the regression guard for that.

Nuxeo itself is mocked, so no server is required.
"""

import asyncio
import base64
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from fastmcp import Client, FastMCP
from mcp.types import ImageContent

from nuxeo_mcp.tools import register_tools

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _doc(uid: str, name: str, title: str, doc_type: str = "Folder") -> MagicMock:
    doc = MagicMock()
    doc.uid = uid
    doc.path = f"/default-domain/workspaces/{name}"
    doc.title = title
    doc.type = doc_type
    doc.properties = {"dc:title": title}
    doc.as_dict.return_value = {
        "uid": uid,
        "path": doc.path,
        "title": title,
        "type": doc_type,
        "properties": doc.properties,
    }
    return doc


@pytest.fixture
def nuxeo() -> MagicMock:
    """A Nuxeo client mock returning two child documents."""
    client = MagicMock()
    client.documents.get_children.return_value = [
        _doc("uid-1", "folder-a", "Folder A"),
        _doc("uid-2", "folder-b", "Folder B"),
    ]
    client.documents.get.return_value = _doc("uid-1", "note", "A Note", "Note")
    return client


@pytest.fixture
def mcp(nuxeo: MagicMock) -> FastMCP:
    """A real FastMCP server with the tools registered against a mocked Nuxeo."""
    server = FastMCP("test")
    register_tools(server, nuxeo, skip_server_selection=True)
    return server


def _call(mcp: FastMCP, name: str, args: Dict[str, Any]) -> Any:
    """Call a tool through an in-process MCP client, so results are validated."""

    async def run() -> Any:
        async with Client(mcp) as client:
            return await client.call_tool(name, args)

    return asyncio.run(run())


@pytest.mark.unit
def test_get_children_returns_markdown_table(mcp: FastMCP) -> None:
    """get_children must return a markdown string, not a dict or a tuple."""
    result = _call(mcp, "get_children", {"ref": "/default-domain/workspaces"})

    text = result.content[0].text
    assert "| uuid | name | title | type |" in text
    assert "Folder A" in text and "Folder B" in text


@pytest.mark.unit
def test_get_children_as_resource_returns_uris(mcp: FastMCP) -> None:
    """as_resource must also satisfy the declared string return type."""
    result = _call(
        mcp, "get_children", {"ref": "/default-domain/workspaces", "as_resource": True}
    )

    assert result.content[0].text == "nuxeo://uid-1\nnuxeo://uid-2"


@pytest.mark.unit
def test_update_document_returns_markdown(mcp: FastMCP) -> None:
    """update_document returns formatted markdown, not a dict."""
    result = _call(
        mcp,
        "update_document",
        {"uid": "uid-1", "properties": {"dc:description": "updated"}},
    )

    assert "# Document:" in result.content[0].text


@pytest.mark.unit
def test_image_blob_returns_base64_image_content(
    mcp: FastMCP, nuxeo: MagicMock
) -> None:
    """An image blob is returned as ImageContent carrying base64 text."""
    response = MagicMock()
    response.content = PNG_BYTES
    response.headers = {
        "content-disposition": "attachment; filename=t.png",
        "content-type": "image/png",
        "content-length": str(len(PNG_BYTES)),
    }
    nuxeo.client.request.return_value = response

    result = _call(mcp, "get_document", {"ref": "uid-1", "fetch_blob": True})

    content = result.content[0]
    assert isinstance(content, ImageContent)
    assert content.mime_type == "image/png"
    assert base64.b64decode(content.data) == PNG_BYTES


@pytest.mark.unit
def test_failed_conversion_raises_tool_error(
    mcp: FastMCP, nuxeo: MagicMock
) -> None:
    """A failed conversion must surface as an error, not a successful result."""
    nuxeo.client.request.side_effect = RuntimeError("boom")

    with pytest.raises(Exception, match="Conversion failed"):
        _call(mcp, "get_document", {"ref": "uid-1", "conversion_format": "pdf"})
