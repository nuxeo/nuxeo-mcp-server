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
    register_tools(server, nuxeo)
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
    result = _call(mcp, "nuxeo_list_children", {"ref": "/default-domain/workspaces"})

    text = result.content[0].text
    assert "| uuid | name | title | type |" in text
    assert "Folder A" in text and "Folder B" in text


@pytest.mark.unit
def test_get_children_as_resource_returns_uris(mcp: FastMCP) -> None:
    """as_resource must also satisfy the declared string return type."""
    result = _call(
        mcp,
        "nuxeo_list_children",
        {"ref": "/default-domain/workspaces", "as_resource": True},
    )

    assert result.content[0].text == "nuxeo://uid-1\nnuxeo://uid-2"


@pytest.mark.unit
def test_update_document_returns_markdown(mcp: FastMCP) -> None:
    """update_document returns formatted markdown, not a dict."""
    result = _call(
        mcp,
        "nuxeo_update_metadata",
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

    result = _call(mcp, "nuxeo_get_document", {"ref": "uid-1", "fetch_blob": True})

    content = result.content[0]
    assert isinstance(content, ImageContent)
    assert content.mime_type == "image/png"
    assert base64.b64decode(content.data) == PNG_BYTES


@pytest.mark.unit
def test_failed_conversion_raises_tool_error(mcp: FastMCP, nuxeo: MagicMock) -> None:
    """A failed conversion must surface as an error, not a successful result."""
    nuxeo.client.request.side_effect = RuntimeError("boom")

    with pytest.raises(Exception, match="Conversion failed"):
        _call(mcp, "nuxeo_get_document", {"ref": "uid-1", "conversion_format": "pdf"})


@pytest.mark.unit
@pytest.mark.parametrize(
    "args, message",
    [
        ({"rendition": "nope"}, "Rendition 'nope' failed"),
        ({"fetch_blob": True}, "Could not fetch the main blob"),
    ],
)
def test_failed_blob_or_rendition_raises_tool_error(
    mcp: FastMCP, nuxeo: MagicMock, args: Dict[str, Any], message: str
) -> None:
    """Returned as text, the error would read as the content asked for."""
    nuxeo.client.request.side_effect = RuntimeError("Rendition does not exist")

    with pytest.raises(Exception, match=message):
        _call(mcp, "nuxeo_get_document", {"ref": "uid-1", **args})


@pytest.mark.unit
def test_move_reports_the_document_where_it_landed(
    mcp: FastMCP, nuxeo: MagicMock
) -> None:
    """Document.Move answers with a dict; a name conflict changes the path."""
    renamed = "/default-domain/workspaces/archive/note.1793293947335"
    nuxeo.operations.new.return_value.execute.return_value = {
        "entity-type": "document",
        "uid": "uid-1",
        "path": renamed,
        "title": "A Note",
    }

    result = _call(
        mcp,
        "nuxeo_move_document",
        {"document_uid": "uid-1", "target_path": "/default-domain/workspaces/archive"},
    )

    assert result.data["uid"] == "uid-1"
    assert result.data["path"] == renamed
    assert result.data["title"] == "A Note"


@pytest.mark.unit
def test_move_without_a_document_is_an_error(mcp: FastMCP, nuxeo: MagicMock) -> None:
    nuxeo.operations.new.return_value.execute.return_value = {"entity-type": "x"}

    with pytest.raises(
        Exception, match="Move returned no document.*may have been applied"
    ):
        _call(mcp, "nuxeo_move_document", {"document_uid": "u", "target_path": "/t"})


# ---------------------------------------------------------------------------
# Server-wide conventions
#
# These assert the contract every tool must satisfy, so a new tool cannot
# silently ship without a prefix or without safety hints.
# ---------------------------------------------------------------------------


def _list_tools(mcp: FastMCP) -> Dict[str, Any]:
    async def run() -> Any:
        async with Client(mcp) as client:
            return {t.name: t for t in await client.list_tools()}

    return asyncio.run(run())


@pytest.mark.unit
def test_every_tool_is_namespaced(mcp: FastMCP) -> None:
    """Bare names collide when a client is connected to several MCP servers."""
    unprefixed = [name for name in _list_tools(mcp) if not name.startswith("nuxeo_")]

    assert unprefixed == []


@pytest.mark.unit
def test_every_tool_declares_safety_annotations(mcp: FastMCP) -> None:
    """Without hints a cautious client must prompt for confirmation on reads."""
    missing = []
    for name, tool in _list_tools(mcp).items():
        annotations = tool.annotations
        if annotations is None or annotations.read_only_hint is None:
            missing.append(name)

    assert missing == []


@pytest.mark.unit
def test_destructive_tools_are_marked_destructive(mcp: FastMCP) -> None:
    """A client gating writes relies on these being honest."""
    tools = _list_tools(mcp)

    for name in (
        "nuxeo_delete_document",
        "nuxeo_update_metadata",
        "nuxeo_move_document",
        "nuxeo_execute_operation",
    ):
        annotations = tools[name].annotations
        assert annotations.read_only_hint is False, name
        assert annotations.destructive_hint is True, name


@pytest.mark.unit
def test_search_tools_are_read_only(mcp: FastMCP) -> None:
    tools = _list_tools(mcp)

    for name in (
        "nuxeo_search_documents",
        "nuxeo_search_documents_with_query_dsl",
        "nuxeo_search_audit_with_query_dsl",
    ):
        assert tools[name].annotations.read_only_hint is True, name


@pytest.mark.unit
def test_only_caller_supplied_payload_tools_are_open_world(mcp: FastMCP) -> None:
    """Open-world means the reachable surface is not described by the schema."""
    open_world = {
        name
        for name, tool in _list_tools(mcp).items()
        if tool.annotations.open_world_hint
    }

    assert open_world == {
        "nuxeo_execute_operation",
        "nuxeo_search_documents_with_query_dsl",
        "nuxeo_search_audit_with_query_dsl",
    }


def test_move_is_not_declared_idempotent() -> None:
    """A replayed move, by UID, renames the document with a timestamp suffix."""
    from nuxeo_mcp.annotations import TOOL_ANNOTATIONS

    assert TOOL_ANNOTATIONS["nuxeo_move_document"].idempotent_hint is False
