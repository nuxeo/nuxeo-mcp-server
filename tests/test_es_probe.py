"""Unit tests for Query DSL and audit search error handling.

Covers the 401/403 permission-denied branches and the connectivity-failure branch
without requiring a live Nuxeo or Elasticsearch server.
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

    register_tools(FakeMCP(), nuxeo, skip_server_selection=True)
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
    response.text = "forbidden"
    mock_post.return_value = response
    fn = _register_and_capture(_make_nuxeo())["nuxeo_search_documents_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn({"query": {"match_all": {}}})

    assert "Query DSL search failed" in str(excinfo.value)


@patch("requests.post")
def test_query_dsl_connection_error_raises_tool_error(mock_post: MagicMock) -> None:
    mock_post.side_effect = requests_lib.exceptions.ConnectionError("refused")
    fn = _register_and_capture(_make_nuxeo())["nuxeo_search_documents_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn({"query": {"match_all": {}}})

    assert "Query DSL search failed" in str(excinfo.value)


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
# search_audit probe tests
# ---------------------------------------------------------------------------


@patch("requests.post")
def test_search_audit_probe_403_returns_permission_denied(mock_post: MagicMock) -> None:
    mock_post.return_value = _mock_probe(403)
    fn = _register_and_capture(_make_nuxeo())["search_audit"]

    result = _call(fn, "deletions yesterday")

    assert result["success"] is False
    assert result["error"] == "Permission denied"
    assert "administrator" in result["message"].lower()


@patch("requests.post")
def test_search_audit_probe_401_returns_authentication_failed(
    mock_post: MagicMock,
) -> None:
    mock_post.return_value = _mock_probe(401)
    fn = _register_and_capture(_make_nuxeo())["search_audit"]

    result = _call(fn, "deletions yesterday")

    assert result["success"] is False
    assert result["error"] == "Authentication failed"


@patch("requests.post")
def test_search_audit_probe_connection_error_returns_not_available(
    mock_post: MagicMock,
) -> None:
    mock_post.side_effect = requests_lib.exceptions.ConnectionError("refused")
    fn = _register_and_capture(_make_nuxeo())["search_audit"]

    result = _call(fn, "deletions yesterday")

    assert result["success"] is False
    assert result["error"] == "Elasticsearch audit not available"
