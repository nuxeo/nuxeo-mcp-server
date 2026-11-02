"""Unit tests for Query DSL and audit search error handling.

Covers the 401/403 permission-denied branches and the connectivity-failure branch
without requiring a live Nuxeo or search engine.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib
from fastmcp.exceptions import ToolError

from tests.helpers import capture_tools, mock_nuxeo

# ---------------------------------------------------------------------------
# nuxeo_search_documents_with_query_dsl failure handling
# ---------------------------------------------------------------------------


@patch("requests.post")
def test_query_dsl_engine_error_raises_tool_error(mock_post: MagicMock) -> None:
    """A non-200 from the passthrough surfaces as an error, not an empty result."""
    response = MagicMock()
    response.status_code = 403
    response.json.side_effect = ValueError("not json")
    response.text = "forbidden"
    mock_post.return_value = response
    fn = capture_tools(mock_nuxeo())["nuxeo_search_documents_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn({"query": {"match_all": {}}})

    assert "Permission denied: forbidden" in str(excinfo.value)


@patch("requests.post")
def test_query_dsl_engine_error_in_http_200_is_not_an_empty_result(
    mock_post: MagicMock,
) -> None:
    """Nuxeo relays engine errors with HTTP 200; no 'No hits' hint must follow."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "error": {"type": "parsing_exception", "reason": "unknown query [bogus]"},
        "status": 400,
    }
    mock_post.return_value = response
    fn = capture_tools(mock_nuxeo())["nuxeo_search_documents_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn({"query": {"bogus": {}}})

    assert "unknown query [bogus]" in str(excinfo.value)


@patch("requests.post")
def test_query_dsl_connection_error_raises_tool_error(mock_post: MagicMock) -> None:
    mock_post.side_effect = requests_lib.exceptions.ConnectionError("refused")
    fn = capture_tools(mock_nuxeo())["nuxeo_search_documents_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn({"query": {"match_all": {}}})

    assert "Could not reach Nuxeo" in str(excinfo.value)


@patch("requests.post")
def test_query_dsl_oversized_response_raises_tool_error(mock_post: MagicMock) -> None:
    """An oversized response is refused rather than pushed into the context."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "hits": {"hits": [{"_source": {"dc:title": "x" * 1000}} for _ in range(500)]}
    }
    mock_post.return_value = response
    fn = capture_tools(mock_nuxeo())["nuxeo_search_documents_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn({"query": {"match_all": {}}})

    assert "over the" in str(excinfo.value)


# ---------------------------------------------------------------------------
# nuxeo_search_audit_with_query_dsl
# ---------------------------------------------------------------------------


@patch("requests.post")
def test_audit_non_admin_403_raises_tool_error(mock_post: MagicMock) -> None:
    """Nuxeo restricts the audit index server-side; the 403 must surface."""
    response = MagicMock()
    response.status_code = 403
    response.json.side_effect = ValueError("not json")
    response.text = "forbidden"
    mock_post.return_value = response
    fn = capture_tools(mock_nuxeo())["nuxeo_search_audit_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn({"query": {"match_all": {}}})

    assert "restricted to administrators" in str(excinfo.value)


def test_audit_missing_body_returns_audit_usage_help() -> None:
    fn = capture_tools(mock_nuxeo())["nuxeo_search_audit_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn(None)

    message = str(excinfo.value)
    assert "eventDate" in message
    assert "nuxeo://audit-query-dsl-guide" in message
