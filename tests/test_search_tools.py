# (C) Copyright 2026 Hyland (https://hyland.com/) and others.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the unified search tool and the Query DSL escape hatch.

Nuxeo is mocked; these cover the contract of the tools themselves -- mode
dispatch, the normalized envelope, and the Query DSL guardrails.
"""

import copy
from types import SimpleNamespace
from typing import Any, Callable, Dict
from unittest.mock import MagicMock

import pytest
from fastmcp.exceptions import ToolError

from nuxeo_mcp.query_dsl import (
    MAX_FROM,
    MAX_SIZE,
    MAX_TOP_HITS_SIZE,
    QueryDslRejected,
    apply_guardrails,
    field_guide,
)
from nuxeo_mcp.tools import register_tools
from tests.helpers import Captured, MockFastMCP, capture_tools, mock_nuxeo

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


def _register_and_capture(nuxeo: Any, experimental: bool = True) -> Captured:
    return capture_tools(nuxeo, experimental=experimental)


def _make_nuxeo(query_result: Any = None) -> MagicMock:
    nuxeo = mock_nuxeo()
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


def test_empty_query_returns_usage_help() -> None:
    with pytest.raises(ToolError) as excinfo:
        _search_tool()("")

    message = str(excinfo.value)
    assert "ecm:isVersion = 0" in message
    assert "nuxeo://nxql-guide" in message


def test_nxql_is_the_default_mode() -> None:
    nuxeo = _make_nuxeo()
    result = _search_tool(nuxeo)("SELECT * FROM File")

    assert result.mode == "nxql"
    assert result.interpretedQuery == "SELECT * FROM File"
    assert nuxeo.client.query.call_args[0][0] == "SELECT * FROM File"


def test_natural_mode_is_gone() -> None:
    """Agents write NXQL; a regex parser only lost information on the way."""
    with pytest.raises(ToolError) as excinfo:
        _search_tool()("find all files", mode="natural")

    assert "Unknown mode" in str(excinfo.value)
    assert "nxql" in str(excinfo.value)


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ToolError) as excinfo:
        _search_tool()("anything", mode="sparql")

    assert "Unknown mode" in str(excinfo.value)


# ---------------------------------------------------------------------------
# mode="semantic"
# ---------------------------------------------------------------------------

SEMANTIC_RESPONSE = {
    "resultsCount": 2,
    "currentPageIndex": 0,
    "pageSize": 10,
    "isNextPageAvailable": False,
    "entries": [
        {
            "entity-type": "document",
            "uid": "uuid-1",
            "path": "/default-domain/workspaces/cork.pdf",
            "type": "File",
            "title": "Cork taint",
            "properties": {"dc:title": "Cork taint"},
            "contextParameters": {
                "score": 0.82,
                "highlight": [
                    {
                        "field": "ecm:binarytext",
                        "segments": ["chlorine reacts with\nmould to form TCA"],
                    }
                ],
            },
        },
        {
            "entity-type": "document",
            "uid": "uuid-2",
            "path": "/default-domain/workspaces/note",
            "type": "Note",
            "properties": {},
        },
    ],
}


def _semantic_nuxeo(response_json: Any = None, raise_exc: Any = None) -> MagicMock:
    nuxeo = _make_nuxeo()
    if raise_exc is not None:
        nuxeo.client.request.side_effect = raise_exc
    else:
        response = MagicMock()
        response.json.return_value = (
            SEMANTIC_RESPONSE if response_json is None else response_json
        )
        nuxeo.client.request.return_value = response
    return nuxeo


def test_semantic_mode_returns_the_same_envelope() -> None:
    """A mode changes how the query is expressed, never the shape of the answer."""
    nuxeo = _semantic_nuxeo()
    result = _search_tool(nuxeo)("why does cork smell musty", mode="semantic")

    assert result.mode == "semantic"
    assert result.totalCount == 2
    assert [d.id for d in result.documents] == ["uuid-1", "uuid-2"]
    # Ranked mode: score and snippets are populated where the engine supplied them,
    # and present-but-empty where it did not -- never absent.
    assert result.documents[0].score == 0.82
    assert result.documents[0].snippets == ["chlorine reacts with mould to form TCA"]
    assert result.documents[1].score is None
    assert result.documents[1].snippets == []


def test_semantic_mode_reports_the_executed_nxql() -> None:
    nuxeo = _semantic_nuxeo()
    result = _search_tool(nuxeo)("musty cork", mode="semantic")

    params = nuxeo.client.request.call_args.kwargs["params"]
    assert params["index"] == "vector"
    assert params["queryParams"] == result.interpretedQuery
    assert result.interpretedQuery == (
        "SELECT * FROM Document WHERE ecm:fulltext = 'musty cork' "
        "AND (ecm:mixinType <> 'HiddenInNavigation' AND ecm:isProxy = 0 "
        "AND ecm:isVersion = 0)"
    )


def test_semantic_mode_escapes_the_query_literal() -> None:
    """Backslash escaping, as NXQL requires -- not a doubled quote."""
    nuxeo = _semantic_nuxeo()
    _search_tool(nuxeo)("Alice's report", mode="semantic")

    assert (
        nuxeo.client.request.call_args.kwargs["params"]["queryParams"]
        == "SELECT * FROM Document WHERE ecm:fulltext = 'Alice\\'s report' "
        "AND (ecm:mixinType <> 'HiddenInNavigation' AND ecm:isProxy = 0 "
        "AND ecm:isVersion = 0)"
    )


def test_semantic_mode_accepts_a_custom_filter() -> None:
    nuxeo = _semantic_nuxeo()
    _search_tool(nuxeo)("cork", mode="semantic", nxql_filter="ecm:primaryType = 'File'")

    assert nuxeo.client.request.call_args.kwargs["params"]["queryParams"].endswith(
        "AND (ecm:primaryType = 'File')"
    )


def test_nxql_filter_is_refused_in_nxql_mode() -> None:
    """A filter that would never run must not look applied."""
    nuxeo = _make_nuxeo()
    with pytest.raises(ToolError, match="only used by mode='semantic'"):
        _search_tool(nuxeo)(
            "SELECT * FROM Document", nxql_filter="ecm:primaryType = 'File'"
        )
    nuxeo.client.query.assert_not_called()


@pytest.mark.parametrize(
    "nxql_filter,operators",
    [
        ("ecm:primaryType = 'Note' OR ecm:primaryType = 'File'", "OR"),
        ("NOT ecm:primaryType = 'File'", "NOT"),
        ("dc:title LIKE 'x%'", "LIKE"),
        ("dc:title ilike 'x%' or ecm:isProxy = 0", "ILIKE, OR"),
    ],
)
def test_semantic_mode_refuses_operators_it_would_drop(
    nxql_filter: str, operators: str
) -> None:
    """OR, NOT, LIKE and ILIKE are dropped by the vector client: refuse them."""
    nuxeo = _semantic_nuxeo()
    with pytest.raises(ToolError, match=f"nxql_filter uses {operators},"):
        _search_tool(nuxeo)("cork", mode="semantic", nxql_filter=nxql_filter)
    nuxeo.client.request.assert_not_called()


@pytest.mark.parametrize(
    "nxql_filter",
    [
        "ecm:primaryType NOT IN ('File') AND dc:modified NOT BETWEEN "
        "DATE '2020-01-01' AND DATE '2021-01-01'",
        "ecm:tag IS NOT NULL",
        "ecm:path STARTSWITH '/default-domain/Notes or Reports'",
        "ecm:primaryType = 'it\\'s not LIKE this'",
        "ecm:primaryType = 'Ordered' AND ecm:uuid = 'notary'",
    ],
)
def test_semantic_mode_accepts_supported_operators(nxql_filter: str) -> None:
    """NOT inside NOT IN/BETWEEN/IS NOT, words in literals or names are fine."""
    nuxeo = _semantic_nuxeo()
    _search_tool(nuxeo)("cork", mode="semantic", nxql_filter=nxql_filter)
    nuxeo.client.request.assert_called_once()


def test_semantic_mode_can_omit_snippets() -> None:
    nuxeo = _semantic_nuxeo()
    result = _search_tool(nuxeo)("cork", mode="semantic", include_snippets=False)

    assert result.documents[0].snippets == []
    # The score is evidence of ranking, not a passage, so it survives.
    assert result.documents[0].score == 0.82


def test_semantic_mode_requests_both_enrichers() -> None:
    """score needs 2025.22+; asking for it on an older server is harmless."""
    nuxeo = _semantic_nuxeo()
    _search_tool(nuxeo)("cork", mode="semantic")

    headers = nuxeo.client.request.call_args.kwargs["headers"]
    assert "highlight" in headers["enrichers-document"]
    assert "score" in headers["enrichers-document"]


def test_semantic_mode_says_the_server_has_no_vector_search() -> None:
    """Most servers have no vector index: say so, and name the exact-match tools."""
    nuxeo = _semantic_nuxeo(
        # Verbatim str() of the client's HTTPError, observed on a 2025 server
        # without a vector index: the detection depends on this wording.
        raise_exc=Exception(
            'HTTPError(400), error: "java.lang.IllegalArgumentException: Invalid '
            "page provider configuration 'search_check_nxql': Configured indexes "
            "[vector] not found for repository 'default'\", server trace: None"
        )
    )

    with pytest.raises(ToolError) as excinfo:
        _search_tool(nuxeo)("cork", mode="semantic")

    message = str(excinfo.value)
    assert "not available on this Nuxeo server" in message
    assert "Do not retry mode='semantic'" in message
    assert "ecm:fulltext" in message
    assert "nuxeo_search_documents_with_query_dsl" in message


@pytest.mark.parametrize("mode", ["semantic", "image", "similar"])
def test_lts_2023_rules_out_every_vector_mode(mode: str) -> None:
    """LTS 2023 lacks the page provider itself: no vector mode can work."""
    nuxeo = _similar_nuxeo(
        ["Picture"],
        # Verbatim str() of the client's HTTPError, observed on 2023.55.
        raise_exc=Exception(
            'HTTPError(400), error: "Could not resolve page provider with name '
            "'search_check_nxql'\", server trace: None"
        ),
    )

    with pytest.raises(ToolError) as excinfo:
        _search_tool(nuxeo)("cork", mode=mode)

    message = str(excinfo.value)
    assert "Vector search is not available on this Nuxeo server" in message
    assert "Do not retry mode='semantic', 'image' or 'similar'" in message
    assert "ecm:fulltext" in message


def test_semantic_mode_reports_other_failures_in_the_engine_words() -> None:
    """A model still deploying is not "no vector search": do not claim it is."""
    engine_error = "Model not ready yet. Please deploy the model first."
    nuxeo = _semantic_nuxeo(raise_exc=Exception(engine_error))

    with pytest.raises(ToolError) as excinfo:
        _search_tool(nuxeo)("cork", mode="semantic")

    message = str(excinfo.value)
    assert engine_error in message
    assert "not available on this Nuxeo server" not in message


def _search_description(experimental: bool) -> str:
    mcp = MockFastMCP("test")
    register_tools(mcp, _make_nuxeo(), experimental=experimental)
    return next(
        t["description"] for t in mcp.tools if t["name"] == "nuxeo_search_documents"
    )


def test_semantic_mode_is_hidden_by_default() -> None:
    assert "semantic" not in _search_description(experimental=False)
    assert "Experimental: mode='semantic'" in _search_description(experimental=True)


@pytest.mark.parametrize("experimental", [False, True])
def test_discovery_mentions_semantic_only_when_experimental(
    experimental: bool,
) -> None:
    """The whole tools/list payload, docstring-parsed params and output schema."""
    import asyncio
    import json

    from fastmcp import Client, FastMCP

    async def tools_list() -> str:
        mcp = FastMCP("test")
        register_tools(mcp, _make_nuxeo(), experimental=experimental)
        async with Client(mcp) as client:
            tools = await client.list_tools()
        return json.dumps([t.model_dump() for t in tools], default=str).lower()

    payload = asyncio.run(tools_list())
    for mode in ("semantic", "mode='image'", "similar"):
        assert (mode in payload) is experimental, mode


@pytest.mark.parametrize("mode", ["semantic", "image", "similar"])
def test_vector_modes_are_refused_by_default(mode: str) -> None:
    nuxeo = _similar_nuxeo(["Picture"])
    search = _register_and_capture(nuxeo, experimental=False)["nuxeo_search_documents"]
    with pytest.raises(ToolError, match="NUXEO_MCP_EXPERIMENTAL"):
        search("cork", mode=mode)
    nuxeo.client.request.assert_not_called()
    nuxeo.documents.get.assert_not_called()


def test_unknown_mode_lists_only_enabled_modes() -> None:
    search = _register_and_capture(_make_nuxeo(), experimental=False)[
        "nuxeo_search_documents"
    ]
    with pytest.raises(ToolError, match=r"Supported modes: nxql\.$"):
        search("x", mode="fuzzy")


# ---------------------------------------------------------------------------
# mode="image"
# ---------------------------------------------------------------------------

IMAGE_RESPONSE = {
    "resultsCount": 1,
    "currentPageIndex": 0,
    "pageSize": 10,
    "isNextPageAvailable": False,
    "entries": [
        {
            "entity-type": "document",
            "uid": "pic-1",
            "path": "/default-domain/workspaces/coco/coco-139",
            "type": "Picture",
            "title": "IMG_139",
            "properties": {},
            "contextParameters": {"score": 0.64},
        }
    ],
}


def test_image_mode_queries_the_image_index_for_pictures() -> None:
    nuxeo = _semantic_nuxeo(IMAGE_RESPONSE)
    result = _search_tool(nuxeo)("a dog on a beach", mode="image")

    kwargs = nuxeo.client.request.call_args.kwargs
    assert kwargs["params"]["index"] == "vector-image"
    assert result.interpretedQuery == (
        "SELECT * FROM Picture WHERE ecm:fulltext = 'a dog on a beach' "
        "AND (ecm:mixinType <> 'HiddenInNavigation' AND ecm:isProxy = 0 "
        "AND ecm:isVersion = 0)"
    )
    # Images have no passage to highlight.
    assert kwargs["headers"]["enrichers-document"] == "score"
    assert result.mode == "image"


def test_image_mode_keeps_only_light_metadata() -> None:
    """Picture views would bloat every hit: only dc and common properties stay."""
    response = copy.deepcopy(IMAGE_RESPONSE)
    response["entries"][0]["properties"] = {
        "dc:title": "IMG_139",
        "common:icon": "/icons/image.gif",
        "picture:views": [{"title": "Small"}],
        "file:content": {"name": "139.jpg"},
    }
    result = _search_tool(_semantic_nuxeo(response))("a dog", mode="image")

    assert result.documents[0].metadata == {
        "dc:title": "IMG_139",
        "common:icon": "/icons/image.gif",
    }


def test_semantic_mode_keeps_all_metadata() -> None:
    response = copy.deepcopy(SEMANTIC_RESPONSE)
    response["entries"][0]["properties"]["file:content"] = {"name": "cork.pdf"}
    result = _search_tool(_semantic_nuxeo(response))("cork", mode="semantic")

    assert "file:content" in result.documents[0].metadata


def test_image_mode_returns_the_same_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NUXEO_PUBLIC_URL", raising=False)
    result = _search_tool(_semantic_nuxeo(IMAGE_RESPONSE))("a dog", mode="image")

    hit = result.documents[0]
    assert hit.id == "pic-1"
    assert hit.score == 0.64
    assert hit.snippets == []
    assert hit.url == (
        "http://nuxeo:8080/nuxeo/ui/#!/browse/default-domain/workspaces/coco/coco-139"
    )


@pytest.mark.parametrize("mode", ["nxql", "semantic"])
def test_hit_url_is_built_on_the_public_url(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """The internal host is often a container name a browser cannot resolve."""
    monkeypatch.setenv("NUXEO_PUBLIC_URL", "https://nuxeo.example.com/nuxeo/")
    query = "SELECT * FROM File" if mode == "nxql" else "cork"
    result = _search_tool(_semantic_nuxeo())(query, mode=mode)

    url = result.documents[0].url
    assert url is not None
    assert url.startswith(
        "https://nuxeo.example.com/nuxeo/ui/#!/browse/default-domain/"
    )


def test_hit_url_falls_back_on_the_client_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NUXEO_PUBLIC_URL", raising=False)
    result = _search_tool(_semantic_nuxeo())("cork", mode="semantic")

    assert result.documents[0].url == (
        "http://nuxeo:8080/nuxeo/ui/#!/browse/default-domain/workspaces/cork.pdf"
    )


def test_image_mode_accepts_a_filter_and_refuses_dropped_operators() -> None:
    nuxeo = _semantic_nuxeo(IMAGE_RESPONSE)
    _search_tool(nuxeo)(
        "a cat", mode="image", nxql_filter="ecm:path STARTSWITH '/default-domain'"
    )
    assert nuxeo.client.request.call_args.kwargs["params"]["queryParams"].endswith(
        "AND (ecm:path STARTSWITH '/default-domain')"
    )

    with pytest.raises(ToolError, match="nxql_filter uses OR, which image search"):
        _search_tool(nuxeo)(
            "a cat", mode="image", nxql_filter="ecm:isProxy = 0 OR ecm:isVersion = 0"
        )


def test_image_mode_says_the_server_has_no_image_search() -> None:
    nuxeo = _semantic_nuxeo(
        raise_exc=Exception(
            'HTTPError(400), error: "java.lang.IllegalArgumentException: Invalid '
            "page provider configuration 'search_check_nxql': Configured indexes "
            "[vector-image] not found for repository 'default'\", server trace: None"
        )
    )

    with pytest.raises(ToolError) as excinfo:
        _search_tool(nuxeo)("a dog", mode="image")

    message = str(excinfo.value)
    assert "Image search is not available on this Nuxeo server" in message
    assert "Do not retry mode='image'" in message


def test_semantic_mode_is_not_unavailable_because_images_are() -> None:
    """A missing image index says nothing about the text vector index."""
    nuxeo = _semantic_nuxeo(
        raise_exc=Exception("Configured indexes [vector-image] not found")
    )
    with pytest.raises(ToolError) as excinfo:
        _search_tool(nuxeo)("cork", mode="semantic")
    assert "not available on this Nuxeo server" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# mode="similar"
# ---------------------------------------------------------------------------

REF_UID = "8e08f10c-2221-4fe8-8fb1-5f56880526fc"


def _similar_nuxeo(
    facets: Any, response_json: Any = None, raise_exc: Any = None
) -> MagicMock:
    nuxeo = _semantic_nuxeo(response_json, raise_exc)
    nuxeo.documents.get.return_value = SimpleNamespace(uid=REF_UID, facets=facets)
    return nuxeo


def test_similar_mode_on_a_picture_searches_the_image_index() -> None:
    nuxeo = _similar_nuxeo(["Picture", "Versionable"], IMAGE_RESPONSE)
    result = _search_tool(nuxeo)(REF_UID, mode="similar")

    nuxeo.documents.get.assert_called_once_with(uid=REF_UID)
    kwargs = nuxeo.client.request.call_args.kwargs
    assert kwargs["params"]["index"] == "vector-image"
    assert kwargs["headers"]["enrichers-document"] == "score"
    assert result.interpretedQuery == (
        "SELECT * FROM Picture WHERE /*+ES: OPERATOR(more_like_this) */ "
        f"ecm:uuid = '{REF_UID}' "
        "AND (ecm:mixinType <> 'HiddenInNavigation' AND ecm:isProxy = 0 "
        "AND ecm:isVersion = 0)"
    )
    assert result.mode == "similar"


def test_similar_mode_on_a_text_document_searches_the_text_index() -> None:
    nuxeo = _similar_nuxeo(["Versionable"])
    result = _search_tool(nuxeo)("/default-domain/workspaces/cork.pdf", mode="similar")

    nuxeo.documents.get.assert_called_once_with(
        path="/default-domain/workspaces/cork.pdf"
    )
    kwargs = nuxeo.client.request.call_args.kwargs
    assert kwargs["params"]["index"] == "vector"
    assert kwargs["params"]["queryParams"].startswith(
        "SELECT * FROM Document WHERE /*+ES: OPERATOR(more_like_this) */ "
        f"ecm:uuid = '{REF_UID}'"
    )
    assert result.documents[0].snippets == ["chlorine reacts with mould to form TCA"]


def test_similar_mode_reports_an_unknown_reference() -> None:
    nuxeo = _similar_nuxeo([])
    nuxeo.documents.get.side_effect = Exception("HTTPError(404)")
    with pytest.raises(ToolError, match="not found or not readable"):
        _search_tool(nuxeo)(REF_UID, mode="similar")
    nuxeo.client.request.assert_not_called()


def test_similar_mode_reports_a_reference_missing_from_the_index() -> None:
    nuxeo = _similar_nuxeo(
        ["Picture"],
        raise_exc=Exception(
            "HTTPError(400) Document: x is not in the vector index, or not readable"
        ),
    )
    with pytest.raises(ToolError, match="not in the vector-image index"):
        _search_tool(nuxeo)(REF_UID, mode="similar")


@pytest.mark.parametrize(
    "facets, index, kind, other_mode",
    [
        (["Picture"], "vector-image", "pictures", "image"),
        (["Versionable"], "vector", "non-picture documents", "semantic"),
    ],
)
def test_similar_mode_says_the_server_has_no_index_for_the_reference(
    facets: Any, index: str, kind: str, other_mode: str
) -> None:
    nuxeo = _similar_nuxeo(
        facets, raise_exc=Exception(f"Configured indexes [{index}] not found")
    )
    with pytest.raises(ToolError) as excinfo:
        _search_tool(nuxeo)(REF_UID, mode="similar")

    message = str(excinfo.value)
    assert f"Similar search on {kind} is not available" in message
    assert f"Do not retry mode='similar' on {kind}, nor mode='{other_mode}'" in message


def test_similar_mode_failure_is_labelled_similar() -> None:
    nuxeo = _similar_nuxeo(["Picture"], raise_exc=Exception("model not deployed"))
    with pytest.raises(ToolError, match="^Similar search failed on this server"):
        _search_tool(nuxeo)(REF_UID, mode="similar")


def test_similar_mode_accepts_a_filter() -> None:
    nuxeo = _similar_nuxeo(["Picture"], IMAGE_RESPONSE)
    _search_tool(nuxeo)(
        REF_UID, mode="similar", nxql_filter="ecm:path STARTSWITH '/default-domain'"
    )
    assert nuxeo.client.request.call_args.kwargs["params"]["queryParams"].endswith(
        "AND (ecm:path STARTSWITH '/default-domain')"
    )


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


def test_guardrails_cap_nested_top_hits() -> None:
    guarded = apply_guardrails(
        {
            "size": 0,
            "aggs": {
                "types": {
                    "terms": {"field": "ecm:primaryType", "size": 5},
                    "aggs": {"docs": {"top_hits": {"size": 100}}},
                }
            },
        },
        default_source=["dc:title"],
    )

    top_hits = guarded["aggs"]["types"]["aggs"]["docs"]["top_hits"]
    assert top_hits["size"] == MAX_TOP_HITS_SIZE
    assert top_hits["_source"] == ["dc:title"]


def test_guardrails_cap_inner_hits() -> None:
    guarded = apply_guardrails(
        {
            "size": 5,
            "query": {
                "nested": {"path": "n", "query": {}, "inner_hits": {"size": 100}}
            },
            "collapse": {"field": "a", "inner_hits": [{"name": "x", "size": 100}]},
        },
        default_source=["dc:title"],
    )

    nested = guarded["query"]["nested"]["inner_hits"]
    assert nested["size"] == MAX_TOP_HITS_SIZE
    # Nested inner hits return the nested object; a document projection empties it.
    assert "_source" not in nested
    collapsed = guarded["collapse"]["inner_hits"][0]
    assert collapsed["size"] == MAX_TOP_HITS_SIZE
    assert collapsed["_source"] == ["dc:title"]


def test_guides_carry_efficiency_advice() -> None:
    """Advice the caps cannot enforce reaches the agent through both guides."""
    from nuxeo_mcp.query_dsl import EFFICIENCY_TIPS, audit_field_guide

    for guide in (field_guide(), audit_field_guide()):
        assert "## Writing efficient queries" in guide
        assert all(tip in guide for tip in EFFICIENCY_TIPS)


def test_guardrails_do_not_mutate_the_caller_body() -> None:
    body = {"size": 0, "aggs": {"d": {"top_hits": {"size": 50}}}}

    apply_guardrails(body)

    assert body["aggs"]["d"]["top_hits"]["size"] == 50


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


def _dsl_with_response(
    monkeypatch: pytest.MonkeyPatch, response: Dict[str, Any]
) -> Callable[..., Any]:
    from nuxeo_mcp import es_passthrough

    class FakePassthrough:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def execute_query(self, index: str, query: Dict[str, Any]) -> Dict[str, Any]:
            return dict(response)

    monkeypatch.setattr(es_passthrough, "ElasticsearchPassthrough", FakePassthrough)
    return _register_and_capture(_make_nuxeo())["nuxeo_search_documents_with_query_dsl"]


def test_hint_is_set_when_nothing_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    fn = _dsl_with_response(
        monkeypatch, {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}}
    )

    assert "_nuxeo_hint" in fn({"query": {"term": {"dc:titel": "x"}}})


def test_no_hint_on_a_count_query_that_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """size 0 asks for no hits; an empty hit list there is not a wrong field."""
    fn = _dsl_with_response(
        monkeypatch, {"hits": {"total": {"value": 3180, "relation": "eq"}, "hits": []}}
    )

    assert "_nuxeo_hint" not in fn({"size": 0, "track_total_hits": True})


def test_an_aggregation_named_top_hits_is_not_rewritten() -> None:
    """Under aggs, keys are caller-chosen names, not the top_hits type."""
    guarded = apply_guardrails(
        {"size": 0, "aggs": {"top_hits": {"top_hits": {"size": 50}}}},
        default_source=["dc:title"],
    )

    container = guarded["aggs"]["top_hits"]
    assert set(container) == {"top_hits"}
    assert container["top_hits"]["size"] == MAX_TOP_HITS_SIZE
    assert container["top_hits"]["_source"] == ["dc:title"]


def test_top_hits_is_capped_in_sub_aggregations() -> None:
    guarded = apply_guardrails(
        {
            "size": 0,
            "aggregations": {
                "a": {
                    "terms": {"field": "x"},
                    "aggs": {"b": {"aggs": {"c": {"top_hits": {"size": 99}}}}},
                }
            },
        }
    )

    inner = guarded["aggregations"]["a"]["aggs"]["b"]["aggs"]["c"]["top_hits"]
    assert inner["size"] == MAX_TOP_HITS_SIZE


def test_audit_guide_does_not_promise_a_source_projection() -> None:
    """The audit tool applies no _source default."""
    from nuxeo_mcp.query_dsl import audit_field_guide

    assert "defaults to a small projection" not in audit_field_guide()
    assert "defaults to a small projection" in field_guide()
