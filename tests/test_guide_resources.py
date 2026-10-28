"""Tests for the nuxeo:// guide resources.

The NXQL guide used to be read from `specs/`, a path outside the package that
ships in neither the wheel nor the container image, so the resource only ever
worked from a source checkout. These tests pin it to the package.
"""

from importlib import resources
from typing import Any, Callable, Dict
from unittest.mock import MagicMock, patch

import pytest

from nuxeo_mcp.resources import register_resources


def _register() -> Dict[str, Callable[..., Any]]:
    captured: Dict[str, Callable[..., Any]] = {}

    class FakeMCP:
        def resource(self, *args: Any, **kwargs: Any) -> Callable[[Callable], Callable]:
            def decorator(fn: Callable) -> Callable:
                captured[kwargs.get("uri", "")] = fn
                return fn

            return decorator

    register_resources(FakeMCP(), MagicMock())
    return captured


@pytest.mark.parametrize(
    "uri",
    ["nuxeo://nxql-guide", "nuxeo://query-dsl-guide", "nuxeo://audit-query-dsl-guide"],
)
def test_guide_resources_return_content(uri: str) -> None:
    result = _register()[uri]()

    assert "error" not in result, f"{uri} returned an error payload, not content"
    assert result["format"] == "markdown"
    assert len(result["content"]) > 500


def test_nxql_guide_ships_inside_the_package() -> None:
    """A path outside the package is absent from the wheel and the image."""
    guide = resources.files("nuxeo_mcp.guides").joinpath("nxql.md")

    assert guide.is_file()
    assert "NXQL" in guide.read_text(encoding="utf-8")


def test_query_dsl_guides_document_their_own_limits() -> None:
    """The limits are rendered from the constants the guardrails enforce."""
    from nuxeo_mcp import query_dsl

    guide = _register()["nuxeo://query-dsl-guide"]()["content"]

    assert str(query_dsl.MAX_SIZE) in guide
    assert str(query_dsl.MAX_FROM) in guide
    assert str(query_dsl.MAX_RESPONSE_BYTES) in guide


# ---------------------------------------------------------------------------
# Runtime field discovery
# ---------------------------------------------------------------------------


def _sampler(*field_sets: Dict[str, Any]) -> Any:
    """Return a fake execute_query yielding documents with the given _source."""

    def execute_query(index: str, query: Dict[str, Any]) -> Dict[str, Any]:
        return {"hits": {"hits": [{"_source": fields} for fields in field_sets]}}

    return execute_query


def test_sampling_unions_source_keys_across_documents() -> None:
    from nuxeo_mcp import query_dsl

    query_dsl.reset_sample_cache()
    names = query_dsl.sample_field_names(
        _sampler({"dc:title": "a", "invoice:amount": 1}, {"dc:title": "b", "x:y": 2}),
        "nuxeo",
    )

    assert names == ["dc:title", "invoice:amount", "x:y"]


def test_sampling_is_cached_per_index() -> None:
    from nuxeo_mcp import query_dsl

    query_dsl.reset_sample_cache()
    calls = []

    def counting(index: str, query: Dict[str, Any]) -> Dict[str, Any]:
        calls.append(index)
        return {"hits": {"hits": [{"_source": {"dc:title": "a"}}]}}

    query_dsl.sample_field_names(counting, "nuxeo")
    query_dsl.sample_field_names(counting, "nuxeo")

    assert calls == ["nuxeo"]


def test_discovered_fields_appear_in_the_guide() -> None:
    from nuxeo_mcp import query_dsl

    guide = query_dsl.field_guide(["dc:title", "invoice:amount"])

    assert "invoice:amount" in guide
    # Curated fields are not repeated in the discovered section.
    assert guide.count("`dc:title`") == 1


def test_curated_field_families_are_not_listed_again() -> None:
    """ecm:path@level* stands for level1..level5; listing them is noise."""
    from nuxeo_mcp import query_dsl

    guide = query_dsl.field_guide(["ecm:path@level1", "ecm:path@level4"])

    assert "Schema fields on this instance" not in guide


def test_guide_degrades_to_curated_fields_when_sampling_fails() -> None:
    """A slightly less complete guide beats a guide that errors."""
    nuxeo = MagicMock()
    nuxeo.client.host = "http://unreachable:8080/nuxeo"
    nuxeo.client.auth = ("user", "pass")

    captured: Dict[str, Callable[..., Any]] = {}

    class FakeMCP:
        def resource(self, *args: Any, **kwargs: Any) -> Callable[[Callable], Callable]:
            def decorator(fn: Callable) -> Callable:
                captured[kwargs.get("uri", "")] = fn
                return fn

            return decorator

    register_resources(FakeMCP(), nuxeo)

    with patch(
        "nuxeo_mcp.es_passthrough.ElasticsearchPassthrough.execute_query",
        side_effect=Exception("connection refused"),
    ):
        result = captured["nuxeo://query-dsl-guide"]()

    assert "ecm:primaryType" in result["content"]
    assert "Schema fields on this instance" not in result["content"]


@pytest.mark.parametrize(
    "uri,index",
    [("nuxeo://query-dsl-guide", "nuxeo"), ("nuxeo://audit-query-dsl-guide", "audit")],
)
def test_guide_states_when_its_tool_cannot_work(uri: str, index: str) -> None:
    """A normal-looking guide for a tool that can only fail invites retries."""
    from nuxeo_mcp import query_dsl
    from nuxeo_mcp.es_passthrough import PassthroughError

    query_dsl.reset_sample_cache()
    with patch(
        "nuxeo_mcp.es_passthrough.ElasticsearchPassthrough.execute_query",
        side_effect=PassthroughError("Search is disabled.", 400, unavailable=True),
    ):
        content = _register()[uri]()["content"]

    assert content.startswith("> **Unavailable on this server:** Search is disabled.")


def test_guide_has_no_warning_for_a_query_error() -> None:
    from nuxeo_mcp import query_dsl
    from nuxeo_mcp.es_passthrough import PassthroughError

    query_dsl.reset_sample_cache()
    with patch(
        "nuxeo_mcp.es_passthrough.ElasticsearchPassthrough.execute_query",
        side_effect=PassthroughError("bad query", 400),
    ):
        content = _register()["nuxeo://query-dsl-guide"]()["content"]

    assert "Unavailable" not in content
