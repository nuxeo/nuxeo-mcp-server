"""Unit tests for Query DSL and audit search error handling.

Covers the 401/403 permission-denied branches and the connectivity-failure branch
without requiring a live Nuxeo or search engine.
"""

import asyncio
import json
from typing import Any, Callable, Dict
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib
from fastmcp.exceptions import ToolError

from nuxeo_mcp.tools import register_tools


def _register_and_capture(nuxeo: Any) -> Dict[str, Callable[..., Any]]:
    """Run register_tools with a fake FastMCP that records tool functions."""
    captured: Dict[str, Callable[..., Any]] = {}

    class FakeMCP:
        def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable], Callable]:
            def decorator(fn: Callable) -> Callable:
                captured[fn.__name__] = fn
                return fn

            return decorator

    register_tools(FakeMCP(), nuxeo)
    return captured


def _make_nuxeo() -> MagicMock:
    """Build a minimal mock Nuxeo client."""
    nuxeo = MagicMock()
    nuxeo.client.host = "http://nuxeo:8080/nuxeo"
    nuxeo.client.auth = ("user", "pass")
    return nuxeo


def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return json.loads(asyncio.run(fn(*args, **kwargs)))


def _mock_probe(status_code: int) -> MagicMock:
    """Return a mock requests.Response with the given status code."""
    probe = MagicMock()
    probe.status_code = status_code
    probe.raise_for_status.side_effect = (
        requests_lib.exceptions.HTTPError(response=probe)
        if status_code >= 400
        else None
    )
    return probe


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
    fn = _register_and_capture(_make_nuxeo())["nuxeo_search_documents_with_query_dsl"]

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
    fn = _register_and_capture(_make_nuxeo())["nuxeo_search_documents_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn({"query": {"bogus": {}}})

    assert "unknown query [bogus]" in str(excinfo.value)


@patch("requests.post")
def test_query_dsl_connection_error_raises_tool_error(mock_post: MagicMock) -> None:
    mock_post.side_effect = requests_lib.exceptions.ConnectionError("refused")
    fn = _register_and_capture(_make_nuxeo())["nuxeo_search_documents_with_query_dsl"]

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
    fn = _register_and_capture(_make_nuxeo())["nuxeo_search_documents_with_query_dsl"]

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
    fn = _register_and_capture(_make_nuxeo())["nuxeo_search_audit_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn({"query": {"match_all": {}}})

    assert "restricted to administrators" in str(excinfo.value)


def test_audit_missing_body_returns_audit_usage_help() -> None:
    fn = _register_and_capture(_make_nuxeo())["nuxeo_search_audit_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn(None)

    message = str(excinfo.value)
    assert "eventDate" in message
    assert "nuxeo://audit-query-dsl-guide" in message
