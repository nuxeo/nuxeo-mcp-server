#!/usr/bin/env python
"""Unit tests for the ``semantic_search`` MCP tool.

These tests mock the Nuxeo client's ``request`` method so they run without a live
server (collected under ``--no-integration``). They cover the success path (entries
mapped to results with extracted chunks), the ``include_chunks`` toggle, page-size
clamping, and the graceful fallback when the vector index is not configured (e.g. on
Nuxeo 2023), where the page provider rejects the ``index=vector`` override with a 4xx.
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
                        "highlight": [
                            {
                                "segments": [
                                    "the termination clause states",
                                    "second seg",
                                ]
                            }
                        ]
                    },
                },
                {
                    "title": "Notes.pdf",
                    "path": "/default-domain/Notes.pdf",
                    "uid": "uid-2",
                    "contextParameters": {"highlight": []},
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
    assert result["results"][0]["chunks"] == [
        "the termination clause states",
        "second seg",
    ]
    assert result["results"][1]["chunks"] == []

    # The page provider is routed to the vector index via the 'index' override and the
    # highlight enricher is requested.
    _, kwargs = nuxeo.client.request.call_args
    assert kwargs["params"]["index"] == "vector"
    assert kwargs["params"]["ecm_fulltext"] == "termination clause"
    assert kwargs["headers"]["enrichers-document"] == "highlight"


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


def test_semantic_search_unexpected_error_returns_generic_failure() -> None:
    nuxeo = _make_nuxeo(raise_exc=ValueError("boom"))
    fn = _register_and_capture(nuxeo)["semantic_search"]

    result = _call(fn, "q")

    assert result["success"] is False
    assert result["error"] == "Semantic search failed"
    assert "boom" in result["message"]
