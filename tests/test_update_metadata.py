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

"""nuxeo_update_metadata: properties parsing and the returned document."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from nuxeo.models import Document

from tests.helpers import capture_tools


def _update(**kwargs: Any) -> tuple:
    nuxeo = MagicMock()
    nuxeo.documents.put.return_value = {"title": "Saved"}
    doc = nuxeo.documents.get.return_value
    doc.uid = "u"
    doc.changeToken = "42"
    doc.properties = {"dc:title": "Old", "dc:creator": "Administrator"}
    tool = capture_tools(nuxeo)["nuxeo_update_metadata"]
    return tool(**kwargs), nuxeo, doc


def _sent(nuxeo: MagicMock) -> Document:
    nuxeo.documents.put.assert_called_once()
    sent: Document = nuxeo.documents.put.call_args.args[0]
    return sent


@pytest.mark.unit
def test_json_object_string_is_parsed() -> None:
    _, nuxeo, _ = _update(uid="u", properties='{"dc:title": "New"}')

    assert _sent(nuxeo).properties == {"dc:title": "New"}


@pytest.mark.unit
def test_sends_only_the_changed_properties() -> None:
    """Not dc:creator: Nuxeo refuses read-only properties from non-administrators."""
    _, nuxeo, _ = _update(path="/a", properties={"dc:title": "New"})

    sent = _sent(nuxeo)
    assert sent.uid == "u"
    assert sent.changeToken == "42"
    assert sent.properties == {"dc:title": "New"}


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
        assert _sent(nuxeo).properties == {}
        return
    nuxeo = MagicMock()
    tool = capture_tools(nuxeo)["nuxeo_update_metadata"]

    with pytest.raises(ValueError, match=error):
        tool(uid="u", properties=properties)

    nuxeo.documents.get.assert_not_called()
    nuxeo.documents.put.assert_not_called()
