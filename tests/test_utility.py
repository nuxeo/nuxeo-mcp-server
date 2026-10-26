"""
Unit tests for the utility module.

These tests verify the functionality of the utility functions.
"""

import pytest

from nuxeo_mcp.utility import format_doc, format_property_value


@pytest.mark.unit
def test_format_doc() -> None:
    """Test that the format_doc function formats a document correctly."""
    # Create a test document
    doc = {
        "uid": "dbaccb2c-7bbc-4326-9330-b1bc08dc9e09",
        "type": "Root",
        "title": "Test Document",
        "path": "/",
        "facets": ["Folderish", "NXTag", "NotCollectionMember"],
        "isProxy": False,
        "isCheckedOut": True,
        "isTrashed": False,
        "isVersion": False,
        "properties": {
            "dc:title": "Test Document",
            "dc:description": "This is a test document",
            "dc:creator": "Administrator",
            "dc:created": "2023-01-01T00:00:00.000Z",
            "dc:modified": "2023-01-02T00:00:00.000Z",
            "dc:contributors": ["Administrator", "Guest"],
            "common:icon": None,
            "nxtag:tags": [],
        },
    }

    # Format the document
    formatted = format_doc(doc)

    # Check that the formatted document is a string (markdown)
    assert isinstance(formatted, str)

    content = formatted

    # Check that the formatted document contains the expected information
    assert "Document: Test Document" in content
    assert "**UID**: dbaccb2c-7bbc-4326-9330-b1bc08dc9e09" in content
    assert "**Type**: Root" in content
    assert "**Path**: /" in content
    assert "**Facets**: Folderish, NXTag, NotCollectionMember" in content
    assert "**Is Proxy**: False" in content
    assert "**Is Checked Out**: True" in content
    assert "**Is Trashed**: False" in content
    assert "**Is Version**: False" in content
    assert "DC Namespace" in content
    assert "COMMON Namespace" in content
    assert "NXTAG Namespace" in content
    assert "| dc:title | Test Document |" in content
    assert "| dc:description | This is a test document |" in content
    assert "| dc:creator | Administrator |" in content
    assert "| dc:contributors | Administrator, Guest |" in content
    assert "| common:icon | *None* |" in content
    assert "| nxtag:tags | *Empty list* |" in content


@pytest.mark.unit
def test_format_doc_empty() -> None:
    """Test that the format_doc function handles empty documents."""
    result_empty = format_doc({})
    result_none = format_doc(None)

    # When document is None, it returns a dict
    assert isinstance(result_none, dict)
    assert "content" in result_none
    assert "content_type" in result_none
    assert result_none["content"] == "No document provided"
    assert result_none["content_type"] == "text/plain"

    # When document is empty dict, it returns a string (markdown)
    assert isinstance(result_empty, str)
    assert "Document: Untitled" in result_empty
    assert "**UID**: Unknown" in result_empty
    assert "**Type**: Unknown" in result_empty


@pytest.mark.unit
def test_format_property_value() -> None:
    """Test that the format_property_value function formats property values correctly."""
    assert format_property_value(None) == "*None*"
    assert format_property_value([]) == "*Empty list*"
    assert format_property_value([1, 2, 3]) == "1, 2, 3"
    assert format_property_value({}) == "*Empty object*"
    assert format_property_value({"key": "value"}) == "*Complex object*"
    assert format_property_value(True) == "True"
    assert format_property_value(False) == "False"
    assert format_property_value(42) == "42"
    assert format_property_value(3.14) == "3.14"
    assert format_property_value("") == "*Empty string*"
    assert format_property_value("Hello") == "Hello"
    assert format_property_value("Hello|World") == "Hello\\|World"
