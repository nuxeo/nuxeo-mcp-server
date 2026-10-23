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
        # scripted_metric carries Painless under four keys, none of them named
        # "script", and runs even with size: 0.
        {
            "size": 0,
            "aggs": {
                "m": {
                    "scripted_metric": {
                        "init_script": "state.s = 0",
                        "map_script": "state.s += 1",
                        "combine_script": "return state.s",
                        "reduce_script": "return states.size()",
                    }
                }
            },
        },
        {"aggs": {"b": {"bucket_script": {"script": "params.a", "buckets_path": {}}}}},
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


def test_natural_mode_degrades_with_an_escaped_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parse failure must still produce executable NXQL, apostrophes included."""
    from nuxeo_mcp import nl_parser

    def boom(self: Any, query: str) -> Any:
        raise ValueError("nope")

    monkeypatch.setattr(nl_parser.NaturalLanguageParser, "parse", boom)

    nuxeo = _make_nuxeo()
    result = _search_tool(nuxeo)("find Alice's report", mode="natural")

    executed = nuxeo.client.query.call_args[0][0]
    # Backslash escaping, not a doubled quote -- the latter is invalid NXQL.
    assert executed == "SELECT * FROM Document WHERE ecm:fulltext = 'Alice\\'s report'"
    assert result.interpretedQuery == executed
    assert result.degraded is not None


def test_query_dsl_size_check_covers_the_echoed_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tiny engine response plus a huge request still exceeds the cap."""
    from nuxeo_mcp import es_passthrough, query_dsl

    class FakePassthrough:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def execute_query(self, index: str, query: Dict[str, Any]) -> Dict[str, Any]:
            return {"hits": {"hits": []}}

    monkeypatch.setattr(es_passthrough, "ElasticsearchPassthrough", FakePassthrough)

    ids = ["x" * 64 for _ in range(query_dsl.MAX_RESPONSE_BYTES // 64 + 100)]
    fn = _register_and_capture(_make_nuxeo())["nuxeo_search_documents_with_query_dsl"]

    with pytest.raises(ToolError) as excinfo:
        fn({"size": 1, "query": {"ids": {"values": ids}}})

    assert "over the" in str(excinfo.value)


def test_field_sampling_excludes_extracted_binary_text() -> None:
    """Discovery needs key names, not the full text of every binary."""
    from nuxeo_mcp.query_dsl import (
        SAMPLE_SOURCE_EXCLUDES,
        reset_sample_cache,
        sample_field_names,
    )

    reset_sample_cache()
    seen: Dict[str, Any] = {}

    def execute_query(index: str, query: Dict[str, Any]) -> Dict[str, Any]:
        seen.update(query)
        return {"hits": {"hits": [{"_source": {"invoice:amount": 1}}]}}

    assert sample_field_names(execute_query, "nuxeo") == ["invoice:amount"]
    assert seen["_source"] == {"excludes": SAMPLE_SOURCE_EXCLUDES}
    assert "ecm:binarytext" in SAMPLE_SOURCE_EXCLUDES
    reset_sample_cache()


def test_usage_highlights_source_backed_fields() -> None:
    """all_field is never stored, so highlighting it yields no fragments."""
    from nuxeo_mcp.query_dsl import USAGE

    highlight = USAGE[USAGE.index('"highlight"') :]
    assert '"all_field"' not in highlight
    assert "require_field_match" in highlight
    assert "dc:title" in highlight
