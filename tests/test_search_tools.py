"""Unit tests for the unified search tool and the Query DSL escape hatch.

Nuxeo is mocked; these cover the contract of the tools themselves -- mode
dispatch, the normalized envelope, and the Query DSL guardrails.
"""

from typing import Any, Callable, Dict
from unittest.mock import MagicMock

import pytest
from fastmcp.exceptions import ToolError

from nuxeo_mcp.query_dsl import (
    MAX_FROM,
    MAX_SIZE,
    QueryDslRejected,
    apply_guardrails,
    field_guide,
)
from nuxeo_mcp.tools import register_tools

QUERY_RESULT = {
    "resultsCount": 2,
    "currentPageIndex": 0,
    "pageSize": 20,
    "isNextPageAvailable": False,
    "entries": [
        {
            "entity-type": "document",
            "repository": "default",
            "uid": "uuid-1",
            "path": "/default-domain/workspaces/report.pdf",
            "type": "File",
            "state": "project",
            "title": "Report",
            "lastModified": "2026-01-02T00:00:00.00Z",
            "isTrashed": False,
            "properties": {
                "dc:title": "Report",
                "dc:creator": "alice",
                "dc:created": "2026-01-01T00:00:00.00Z",
                "dc:lastContributor": "bob",
            },
        },
        {
            "entity-type": "document",
            "repository": "default",
            "uid": "uuid-2",
            "path": "/default-domain/workspaces/note",
            "type": "Note",
            "properties": {},
        },
    ],
}


def _register_and_capture(nuxeo: Any) -> Dict[str, Callable[..., Any]]:
    captured: Dict[str, Callable[..., Any]] = {}

    class FakeMCP:
        def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable], Callable]:
            def decorator(fn: Callable) -> Callable:
                captured[kwargs.get("name", fn.__name__)] = fn
                return fn

            return decorator

    register_tools(FakeMCP(), nuxeo, skip_server_selection=True)
    return captured


def _make_nuxeo(query_result: Any = None) -> MagicMock:
    nuxeo = MagicMock()
    nuxeo.client.host = "http://nuxeo:8080/nuxeo"
    nuxeo.client.auth = ("user", "pass")
    nuxeo.client.query.return_value = (
        QUERY_RESULT if query_result is None else query_result
    )
    return nuxeo


def _search_tool(nuxeo: Any = None) -> Callable[..., Any]:
    return _register_and_capture(nuxeo or _make_nuxeo())["nuxeo_search_documents"]


# ---------------------------------------------------------------------------
# nuxeo_search_documents
# ---------------------------------------------------------------------------


def test_nxql_mode_executes_query_verbatim() -> None:
    nuxeo = _make_nuxeo()
    result = _search_tool(nuxeo)("SELECT * FROM File", mode="nxql")

    assert nuxeo.client.query.call_args[0][0] == "SELECT * FROM File"
    assert result.mode == "nxql"
    assert result.interpretedQuery == "SELECT * FROM File"


def test_envelope_is_normalized() -> None:
    result = _search_tool()("SELECT * FROM File", mode="nxql")

    assert result.totalCount == 2
    assert result.hasMore is False
    first = result.documents[0]
    assert first.id == "uuid-1"
    assert first.documentType == "File"
    assert first.title == "Report"
    assert first.createdBy == "alice"
    assert first.modifiedBy == "bob"
    assert first.createdAt == "2026-01-01T00:00:00.00Z"
    assert first.extensions["nuxeo"]["isTrashed"] is False


def test_envelope_shape_is_constant_when_mode_cannot_rank() -> None:
    """score and snippets are present-but-empty rather than absent."""
    payload = (
        _search_tool()("SELECT * FROM File", mode="nxql").documents[0].model_dump()
    )

    assert payload["score"] is None
    assert payload["snippets"] == []


def test_natural_mode_reports_the_generated_nxql() -> None:
    nuxeo = _make_nuxeo()
    result = _search_tool(nuxeo)("find all files", mode="natural")

    assert result.mode == "natural"
    assert result.interpretedQuery.upper().startswith("SELECT")
    assert result.degraded is None


def test_empty_query_returns_usage_help() -> None:
    with pytest.raises(ToolError) as excinfo:
        _search_tool()("")

    message = str(excinfo.value)
    assert 'mode="nxql"' in message
    assert "nuxeo://nxql-guide" in message


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ToolError) as excinfo:
        _search_tool()("anything", mode="sparql")

    assert "Unknown mode" in str(excinfo.value)


def test_semantic_mode_is_announced_as_unavailable() -> None:
    with pytest.raises(ToolError) as excinfo:
        _search_tool()("anything", mode="semantic")

    assert "not yet available" in str(excinfo.value)


def test_page_size_is_clamped() -> None:
    nuxeo = _make_nuxeo()
    _search_tool(nuxeo)("SELECT * FROM File", mode="nxql", page_size=10_000)

    assert nuxeo.client.query.call_args[1]["params"]["pageSize"] == 100


def test_repository_error_surfaces_as_tool_error() -> None:
    nuxeo = _make_nuxeo()
    nuxeo.client.query.side_effect = RuntimeError("bad NXQL")

    with pytest.raises(ToolError) as excinfo:
        _search_tool(nuxeo)("SELECT * FROM Nope", mode="nxql")

    assert "Search failed" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Query DSL guardrails
# ---------------------------------------------------------------------------


def test_guardrails_apply_defaults() -> None:
    guarded = apply_guardrails(
        {"query": {"match_all": {}}}, default_source=["dc:title"]
    )

    assert guarded["size"] == 10
    assert guarded["_source"] == ["dc:title"]


def test_guardrails_leave_source_alone_without_a_default() -> None:
    """The audit index shares no field names with the repository index."""
    guarded = apply_guardrails({"query": {"match_all": {}}})

    assert "_source" not in guarded


def test_guardrails_cap_size() -> None:
    assert apply_guardrails({"size": 10_000})["size"] == MAX_SIZE


def test_guardrails_keep_size_zero_for_aggregation_only_requests() -> None:
    guarded = apply_guardrails({"size": 0, "aggs": {"t": {"terms": {"field": "x"}}}})

    assert guarded["size"] == 0
    assert "_source" not in guarded


def test_guardrails_respect_an_explicit_source() -> None:
    guarded = apply_guardrails(
        {"_source": ["dc:title"], "query": {"match_all": {}}},
        default_source=["ecm:uuid"],
    )

    assert guarded["_source"] == ["dc:title"]


def test_guardrails_reject_deep_pagination() -> None:
    with pytest.raises(QueryDslRejected):
        apply_guardrails({"from": MAX_FROM + 1})


@pytest.mark.parametrize(
    "body",
    [
        {"query": {"script": {"script": {"source": "return true"}}}},
        {"script_fields": {"x": {"script": {"source": "1+1"}}}},
        {"query": {"bool": {"must": [{"script_score": {"script": {"source": "1"}}}]}}},
    ],
)
def test_guardrails_reject_scripted_queries_at_any_depth(body: Dict[str, Any]) -> None:
    with pytest.raises(QueryDslRejected) as excinfo:
        apply_guardrails(body)

    assert "Scripted queries are not allowed" in str(excinfo.value)


def test_missing_body_returns_usage_help() -> None:
    fn = _register_and_capture(_make_nuxeo())["nuxeo_search_documents_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn(None)

    assert "aggs" in str(excinfo.value)


def test_field_guide_documents_the_catch_all_field() -> None:
    guide = field_guide()

    assert "all_field" in guide
    assert "ecm:primaryType" in guide
    # The silent-empty-result failure mode must be called out explicitly.
    assert "matches nothing" in guide
