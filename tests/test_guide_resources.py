"""Tests for the nuxeo:// guide resources.

The NXQL guide used to be read from `specs/`, a path outside the package that
ships in neither the wheel nor the container image, so the resource only ever
worked from a source checkout. These tests pin it to the package.
"""

from importlib import resources
from typing import Any, Callable, Dict
from unittest.mock import MagicMock

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
