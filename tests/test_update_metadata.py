"""nuxeo_update_metadata: properties parsing and the returned document."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.helpers import capture_tools


def _update(**kwargs: Any) -> tuple:
    nuxeo = MagicMock()
    nuxeo.documents.put.return_value = {"title": "Saved"}
    doc = nuxeo.documents.get.return_value
    doc.properties = {}
    tool = capture_tools(nuxeo)["nuxeo_update_metadata"]
    return tool(**kwargs), nuxeo, doc


@pytest.mark.unit
def test_json_object_string_is_parsed() -> None:
    _, nuxeo, doc = _update(uid="u", properties='{"dc:title": "New"}')

    assert doc.properties == {"dc:title": "New"}
    nuxeo.documents.put.assert_called_once_with(doc)


@pytest.mark.unit
def test_returns_the_saved_document() -> None:
    """The server's answer, not the local copy with its stale fields."""
    result, _, _ = _update(uid="u", properties={"dc:title": "New"})

    assert result.startswith("# Document: Saved")


@pytest.mark.unit
@pytest.mark.parametrize(
    "properties,error",
    [
        ("{not json", "Invalid JSON"),
        ("", "Invalid JSON"),
        ("[1, 2]", "must be an object"),
        ("42", "must be an object"),
        ("true", "must be an object"),
        ("null", None),
    ],
)
def test_rejected_properties_touch_nothing(properties: str, error: Any) -> None:
    if error is None:
        # JSON null means no properties: the document is saved unchanged.
        _, nuxeo, _ = _update(uid="u", properties=properties)
        nuxeo.documents.put.assert_called_once()
        return
    nuxeo = MagicMock()
    tool = capture_tools(nuxeo)["nuxeo_update_metadata"]

    with pytest.raises(ValueError, match=error):
        tool(uid="u", properties=properties)

    nuxeo.documents.get.assert_not_called()
    nuxeo.documents.put.assert_not_called()
