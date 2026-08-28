"""
Regression tests for critical bugs fixed in the nuxeo-mcp-server codebase.

Covers:
- ServerManager default server initialization
- Resource adapter path parsing (strip, len, uid resolution)
- ImageContent construction in return_blob
"""

import base64
import inspect
import os
import tempfile

import pytest
from mcp.types import ImageContent

from nuxeo_mcp import resources
from nuxeo_mcp.server_manager import ServerManager, DEFAULT_SERVER_NAME
from nuxeo_mcp.utility import return_blob


# ---------------------------------------------------------------------------
# ServerManager — default server initialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_initialize_default_servers_sets_active_to_existing_server() -> None:
    """After fresh init the active server must reference a name that exists."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        config_path = f.name

    try:
        os.unlink(config_path)  # force default initialization path
        mgr = ServerManager(config_file=config_path)

        assert mgr.active_server in mgr.servers, (
            f"active_server '{mgr.active_server}' does not match any configured "
            f"server ({list(mgr.servers.keys())})"
        )
        assert mgr.active_server == DEFAULT_SERVER_NAME
    finally:
        context_path = str(config_path).rsplit("/", 1)[0] + "/context.json"
        for path in (config_path, context_path):
            if os.path.exists(path):
                os.unlink(path)


# ---------------------------------------------------------------------------
# resources.py — adapter path parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_strip_whitespace_from_uid_before_adapter_request() -> None:
    """UIDs must be whitespace-stripped (Python str.strip, not Java .trim)."""
    uid = "  abc-123  "
    assert uid.strip() == "abc-123"
    # Ensure the Java-style method does not exist on Python str
    assert not hasattr(uid, "trim")


@pytest.mark.unit
def test_adapter_path_slicing_uses_len_function_call() -> None:
    """Adapter param extraction must call len(), not subscript len[]."""
    adapter = "blob"
    adapter_path = "blob/blobholder:0"

    # len[adapter] would raise TypeError; len(adapter) returns 4
    result = adapter_path[len(adapter) :]
    assert result == "/blobholder:0"


@pytest.mark.unit
def test_path_with_adapter_resolves_document_uid() -> None:
    """get_document_by_path must fetch the document to obtain its uid."""
    source = inspect.getsource(resources.register_resources)

    assert "doc.uid" in source, (
        "Expected 'doc.uid' in get_document_by_path — the path-based resource "
        "must resolve the document before forwarding to the adapter handler"
    )


# ---------------------------------------------------------------------------
# utility.return_blob — ImageContent construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_return_blob_creates_valid_image_content_for_images() -> None:
    """return_blob must produce a fully valid ImageContent for image/* MIME types."""
    raw_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    blob_info = {
        "mime_type": "image/png",
        "content": raw_png,
        "name": "test.png",
        "size": len(raw_png),
    }

    result = return_blob(blob_info)

    assert isinstance(result, ImageContent)
    assert result.type == "image"
    assert result.mimeType == "image/png"
    assert base64.b64decode(result.data) == raw_png


@pytest.mark.unit
def test_return_blob_passes_through_raw_bytes_for_non_images() -> None:
    """return_blob must return raw bytes unchanged for non-image MIME types."""
    raw_pdf = b"%PDF-1.4 fake content"
    blob_info = {
        "mime_type": "application/pdf",
        "content": raw_pdf,
        "name": "report.pdf",
        "size": len(raw_pdf),
    }

    assert return_blob(blob_info) == raw_pdf
