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

"""The nuxeo://<ref>@<adapter> resources, read through a real MCP client."""

import asyncio
import base64
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastmcp import Client, FastMCP

from nuxeo_mcp.resources import register_resources

UID = "5d86eea5-293e-4a90-b368-832d3877d01c"


def _read(nuxeo: MagicMock, uri: str) -> Any:
    server = FastMCP("test")
    register_resources(server, nuxeo)

    async def run() -> Any:
        async with Client(server) as client:
            return (await client.read_resource(uri))[0]

    return asyncio.run(run())


def _nuxeo(content_type: str, body: bytes) -> MagicMock:
    nuxeo = MagicMock()
    nuxeo.documents.get.return_value.uid = UID
    response = nuxeo.client.request.return_value
    response.headers = {"content-type": content_type}
    response.content = body
    response.text = body.decode(errors="replace")
    return nuxeo


@pytest.mark.unit
def test_path_adapter_resolves_the_path_to_an_id() -> None:
    nuxeo = _nuxeo("application/json", b'{"entity-type":"documents"}')

    content = _read(nuxeo, "nuxeo://default-domain/workspaces@children")

    nuxeo.documents.get.assert_called_once_with(path="/default-domain/workspaces")
    nuxeo.client.request.assert_called_once_with(
        "GET", f"api/v1/repo/default/id/{UID}/@children"
    )
    # JSON adapters come back as text, not base64 bytes.
    assert content.text == '{"entity-type":"documents"}'


@pytest.mark.unit
def test_uid_adapter_with_a_parameter() -> None:
    """The path template matches first: a uid must not be looked up as a path."""
    nuxeo = _nuxeo("application/json", b"{}")

    _read(nuxeo, f"nuxeo://{UID}@blob/blobholder:0")

    nuxeo.documents.get.assert_not_called()
    nuxeo.client.request.assert_called_once_with(
        "GET", f"api/v1/repo/default/id/{UID}/@blob/blobholder:0"
    )


@pytest.mark.unit
def test_uid_adapter_without_a_parameter() -> None:
    """nuxeo://<uid>@children matches the plain uid template first."""
    nuxeo = _nuxeo("application/json", b'{"entity-type":"documents"}')

    content = _read(nuxeo, f"nuxeo://{UID}@children")

    nuxeo.documents.get.assert_not_called()
    nuxeo.client.request.assert_called_once_with(
        "GET", f"api/v1/repo/default/id/{UID}/@children"
    )
    assert content.text == '{"entity-type":"documents"}'


@pytest.mark.unit
def test_xml_adapter_answer_is_text() -> None:
    """An XML answer comes back as text, not base64 bytes."""
    nuxeo = _nuxeo("application/xml", b"<acl/>")

    content = _read(nuxeo, f"nuxeo://{UID}@acl")

    assert content.text == "<acl/>"


@pytest.mark.unit
def test_image_rendition_is_a_blob() -> None:
    """An image file is returned as a blob with its MIME type, not ImageContent."""
    nuxeo = _nuxeo("image/png", b"\x89PNG")
    nuxeo.client.request.return_value.headers["content-disposition"] = (
        "inline; filename=thumb.png"
    )

    content = _read(nuxeo, f"nuxeo://{UID}@rendition/thumbnail")

    assert content.mimeType == "image/png"
    assert base64.b64decode(content.blob) == b"\x89PNG"
