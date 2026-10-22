#!/usr/bin/env python
"""Unit tests for the ``semantic_search`` MCP tool.

These tests mock the Nuxeo client's ``request`` method so they run without a live
server (collected under ``--no-integration``). They cover the success path (entries
mapped to results with extracted chunks and relevance score), the ``include_chunks``
toggle, page-size clamping, the ``nxql_filter`` override (default and custom), single-
quote escaping in the query text, the graceful fallback when the vector index is not
configured (e.g. on Nuxeo 2023 or 2025 < 2025.22), where the page provider rejects
the ``index=vector`` override with a 4xx, and that a genuine 5xx server error is
surfaced as a generic failure rather than the "not configured" fallback.
"""

import asyncio
import json
from typing import Any, Callable, Dict
from unittest.mock import MagicMock

import pytest
from nuxeo.exceptions import HTTPError

from nuxeo_mcp.tools import register_tools


def _register_and_capture(nuxeo: Any) -> Dict[str, Callable[..., Any]]:
    """Run register_tools with a fake FastMCP that records @mcp.tool() functions."""
    captured: Dict[str, Callable[..., Any]] = {}

    class FakeMCP:
        def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable], Callable]:
            def decorator(fn: Callable) -> Callable:
                captured[fn.__name__] = fn
                return fn

            return decorator

    register_tools(FakeMCP(), nuxeo, skip_server_selection=True)
    return captured


def _make_nuxeo(response_json: Any = None, raise_exc: Exception = None) -> MagicMock:
    """Build a mock Nuxeo client whose client.request returns/raises as configured."""
    nuxeo = MagicMock()
    if raise_exc is not None:
        nuxeo.client.request.side_effect = raise_exc
    else:
        response = MagicMock()
        response.json.return_value = response_json
        nuxeo.client.request.return_value = response
    return nuxeo


def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return json.loads(asyncio.run(fn(*args, **kwargs)))


def test_semantic_search_success_maps_entries_and_chunks() -> None:
    nuxeo = _make_nuxeo(
        {
            "resultsCount": 2,
            "entries": [
                {
                    "title": "Contract.pdf",
                    "path": "/default-domain/Contract.pdf",
                    "uid": "uid-1",
                    "contextParameters": {
                        "score": 0.87,
                        "highlight": [
                            {
                                "segments": [
                                    "the termination clause states",
                                    "second seg",
                                ]
                            }
                        ],
                    },
                },
                {
                    "title": "Notes.pdf",
                    "path": "/default-domain/Notes.pdf",
                    "uid": "uid-2",
                    "contextParameters": {"score": 0.42, "highlight": []},
                },
            ],
        }
    )
    fn = _register_and_capture(nuxeo)["semantic_search"]

    result = _call(fn, "termination clause", pageSize=5)

    assert result["success"] is True
    assert result["total"] == 2
    assert result["query"] == "termination clause"
    assert len(result["results"]) == 2
    assert result["results"][0]["title"] == "Contract.pdf"
    assert result["results"][0]["uid"] == "uid-1"
    assert result["results"][0]["score"] == 0.87
    assert result["results"][0]["chunks"] == [
        "the termination clause states",
        "second seg",
    ]
    assert result["results"][1]["score"] == 0.42
    assert result["results"][1]["chunks"] == []

    # The search_check_nxql PP is used with the full NXQL as queryParams, routed to the
    # vector index. Both the 'highlight' and 'score' enrichers are requested.
    _, kwargs = nuxeo.client.request.call_args
    assert "search_check_nxql" in kwargs.get("url", "") or "search_check_nxql" in str(
        nuxeo.client.request.call_args
    )
    assert kwargs["params"]["index"] == "vector"
    assert "termination clause" in kwargs["params"]["queryParams"]
    assert "ecm:isProxy=0" in kwargs["params"]["queryParams"]
    assert "ecm:isVersion=0" in kwargs["params"]["queryParams"]
    assert kwargs["headers"]["enrichers-document"] == "highlight, score"
    # The nxql sent is echoed back in the response.
    assert "nxql" in result
    assert "termination clause" in result["nxql"]


def test_semantic_search_default_nxql_filter() -> None:
    """Default nxql_filter excludes proxies and versions."""
    nuxeo = _make_nuxeo({"resultsCount": 0, "entries": []})
    fn = _register_and_capture(nuxeo)["semantic_search"]

    _call(fn, "anything")

    _, kwargs = nuxeo.client.request.call_args
    nxql = kwargs["params"]["queryParams"]
    assert "ecm:isProxy=0" in nxql
    assert "ecm:isVersion=0" in nxql


def test_semantic_search_custom_nxql_filter() -> None:
    """Custom nxql_filter replaces the default — allows scoping by folder or type."""
    nuxeo = _make_nuxeo({"resultsCount": 0, "entries": []})
    fn = _register_and_capture(nuxeo)["semantic_search"]

    _call(
        fn,
        "budget",
        nxql_filter="ecm:ancestorId = 'uid-folder' AND ecm:primaryType = 'File' AND ecm:isProxy=0",
    )

    _, kwargs = nuxeo.client.request.call_args
    nxql = kwargs["params"]["queryParams"]
    assert "ecm:ancestorId = 'uid-folder'" in nxql
    assert "ecm:primaryType = 'File'" in nxql
    # The default filter is NOT present when overridden.
    assert "ecm:isVersion=0" not in nxql


def test_semantic_search_single_quote_escaping() -> None:
    """Single quotes in the query text are doubled to keep the NXQL literal valid."""
    nuxeo = _make_nuxeo({"resultsCount": 0, "entries": []})
    fn = _register_and_capture(nuxeo)["semantic_search"]

    _call(fn, "l'accord de confidentialité")

    _, kwargs = nuxeo.client.request.call_args
    nxql = kwargs["params"]["queryParams"]
    assert "l''accord de confidentialité" in nxql


def test_semantic_search_include_chunks_false_omits_chunks() -> None:
    nuxeo = _make_nuxeo(
        {
            "resultsCount": 1,
            "entries": [
                {
                    "title": "Doc.pdf",
                    "path": "/p",
                    "uid": "u",
                    "contextParameters": {"highlight": [{"segments": ["x"]}]},
                }
            ],
        }
    )
    fn = _register_and_capture(nuxeo)["semantic_search"]

    result = _call(fn, "anything", include_chunks=False)

    assert result["success"] is True
    assert "chunks" not in result["results"][0]


def test_semantic_search_clamps_page_size() -> None:
    nuxeo = _make_nuxeo({"resultsCount": 0, "entries": []})
    fn = _register_and_capture(nuxeo)["semantic_search"]

    _call(fn, "q", pageSize=9999)

    _, kwargs = nuxeo.client.request.call_args
    assert kwargs["params"]["pageSize"] == 100


def test_semantic_search_unavailable_returns_friendly_fallback() -> None:
    # Simulate the 2023 / not-configured case: the page provider rejects the unknown
    # 'vector' index with HTTP 400 (Nuxeo client raises nuxeo.exceptions.HTTPError).
    exc = HTTPError.parse(
        {
            "status": 400,
            "message": (
                "Invalid page provider configuration 'default_search': "
                "Configured indexes [vector] not found for repository 'default'"
            ),
        }
    )
    nuxeo = _make_nuxeo(raise_exc=exc)
    fn = _register_and_capture(nuxeo)["semantic_search"]

    result = _call(fn, "q")

    assert result["success"] is False
    assert result["error"] == "Vector search not available"
    assert "nuxeo-search-client-opensearch2-vector" in result["message"]
    assert result["alternative_tools"] == [
        "search_repository",
        "natural_search",
        "search",
    ]


def test_semantic_search_server_error_returns_generic_failure() -> None:
    # A 5xx is a genuine server-side failure, not a "vector not configured" signal, so it
    # must not be misdiagnosed as the friendly fallback.
    exc = HTTPError.parse(
        {
            "status": 500,
            "message": "Internal Server Error",
        }
    )
    nuxeo = _make_nuxeo(raise_exc=exc)
    fn = _register_and_capture(nuxeo)["semantic_search"]

    result = _call(fn, "q")

    assert result["success"] is False
    assert result["error"] == "Semantic search failed"
    assert "Internal Server Error" in result["message"]


def test_semantic_search_unexpected_error_returns_generic_failure() -> None:
    nuxeo = _make_nuxeo(raise_exc=ValueError("boom"))
    fn = _register_and_capture(nuxeo)["semantic_search"]

    result = _call(fn, "q")

    assert result["success"] is False
    assert result["error"] == "Semantic search failed"
    assert "boom" in result["message"]
