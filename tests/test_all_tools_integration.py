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

"""Every MCP tool, called through an MCP client against a live Nuxeo server.

Follows nuxeo_mcp_test_scenario.md. Safe on a server holding real content: all
writes happen in a workspace created for the run, deleted on teardown.

Needs Nuxeo with the search passthrough (/site/es), an audit index, and an
administrator account. Run against an existing server with
NUXEO_URL=... NUXEO_USERNAME=... NUXEO_PASSWORD=... pytest --integration.
"""

import asyncio
import base64
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Set, Tuple

import pytest
from fastmcp import Client
from fastmcp.client.client import CallToolResult
from nuxeo.models import Document

from nuxeo_mcp.file_access import FilePathPolicy
from nuxeo_mcp.server import NuxeoMCPServer

pytestmark = pytest.mark.integration

WORKSPACES = "/default-domain/workspaces"
# Search and listings read the index, which lags writes by a few seconds.
INDEX_TIMEOUT_S = 15.0

CALLED: Set[str] = set()


class Mcp:
    """Synchronous wrapper over an in-process MCP client."""

    def __init__(self, server: NuxeoMCPServer) -> None:
        self.server = server

    def _run(self, fn: Callable[[Client], Any]) -> Any:
        async def run() -> Any:
            async with Client(self.server.mcp) as client:
                return await fn(client)

        return asyncio.run(run())

    def call(self, name: str, args: Dict[str, Any]) -> CallToolResult:
        CALLED.add(name)
        return self._run(lambda c: c.call_tool(name, args, raise_on_error=False))

    def ok(self, name: str, args: Dict[str, Any]) -> Any:
        """Call a tool that must succeed; return its structured or text result."""
        result = self.call(name, args)
        assert not result.is_error, f"{name} failed: {text(result)}"
        return data(result)

    def fails(self, name: str, args: Dict[str, Any]) -> str:
        """Call a tool that must fail; return the error text."""
        result = self.call(name, args)
        assert result.is_error, f"{name} should have failed: {text(result)[:300]}"
        return text(result)

    def read(self, uri: str) -> Any:
        return self._run(lambda c: c.read_resource(uri))[0]

    def tool_names(self) -> Set[str]:
        return {t.name for t in self._run(lambda c: c.list_tools())}


def text(result: CallToolResult) -> str:
    return "\n".join(getattr(c, "text", "") or "" for c in result.content)


def data(result: CallToolResult) -> Any:
    sc = result.structured_content
    if isinstance(sc, dict):
        return sc.get("result", sc) if set(sc) == {"result"} else sc
    try:
        return json.loads(text(result))
    except ValueError:
        return text(result)


def eventually(fn: Callable[[], Any], what: str) -> Any:
    """Retry fn until it returns a truthy value or the index timeout expires."""
    deadline = time.monotonic() + INDEX_TIMEOUT_S
    while True:
        value = fn()
        if value:
            return value
        if time.monotonic() > deadline:
            pytest.fail(f"{what}: not visible after {INDEX_TIMEOUT_S}s")
        time.sleep(1)


@pytest.fixture(scope="module")
def upload_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The only folder file_path may read from, as with NUXEO_MCP_UPLOAD_DIR."""
    return tmp_path_factory.mktemp("upload").resolve()


@pytest.fixture(scope="module")
def mcp(
    nuxeo_container: Any,
    nuxeo_url: str,
    nuxeo_credentials: Tuple[str, str],
    upload_dir: Path,
) -> Mcp:
    username, password = nuxeo_credentials
    return Mcp(
        NuxeoMCPServer(
            nuxeo_url=nuxeo_url,
            username=username,
            password=password,
            file_path_policy=FilePathPolicy(upload_dir=str(upload_dir)),
            experimental=True,
        )
    )


@pytest.fixture(scope="module")
def ws(mcp: Mcp, upload_dir: Path) -> Iterator[Dict[str, str]]:
    """The run workspace and its documents; deleted on teardown."""
    run = uuid.uuid4().hex[:8]
    path = f"{WORKSPACES}/mcp-test-{run}"
    mcp.fails("nuxeo_get_document", {"ref": path})

    created = mcp.ok(
        "nuxeo_create_document",
        {
            "parent_path": WORKSPACES,
            "name": f"mcp-test-{run}",
            "type": "Workspace",
            "properties": {"dc:title": f"MCP Test {run}"},
        },
    )
    ids = {"run": run, "path": path, "uid": created["uid"]}
    try:
        assert created["path"] == path
        upload = upload_dir / f"mcp-test-{run}.txt"
        upload.write_text(f"Hello from {run}")
        ids["upload_file"] = str(upload)

        def create(name: str, type_: str, props: Dict[str, Any], **kw: Any) -> str:
            doc = mcp.ok(
                "nuxeo_create_document",
                {
                    "parent_path": path,
                    "name": name,
                    "type": type_,
                    "properties": props,
                    **kw,
                },
            )
            assert doc["status"] == "success" and doc["path"] == f"{path}/{name}"
            return str(doc["uid"])

        ids["target"] = create("target", "Folder", {"dc:title": "Target"})
        ids["note"] = create(
            "note",
            "Note",
            {
                "dc:title": f"Note {run}",
                "note:note": f"<p>The quick brown fox jumps over the lazy dog {run}</p>",
            },
        )
        ids["file"] = create("file", "File", {"dc:title": f"File {run}"})
        ids["upload"] = create(
            "upload", "File", {"dc:title": f"Upload {run}"}, file_path=str(upload)
        )
        yield ids
    finally:
        mcp.ok("nuxeo_delete_document", {"uid": ids["uid"]})
        # Deletion is permanent, not a move to the trash.
        mcp.fails("nuxeo_get_document", {"ref": path})


def test_server_info(mcp: Mcp) -> None:
    info = mcp.ok("nuxeo_get_repository_info", {})
    assert info["productVersion"]
    resource = json.loads(mcp.read("nuxeo://info").text)
    assert resource["connected"] is True
    assert resource["version"] == info["productVersion"]
    for guide in ("nxql-guide", "query-dsl-guide", "audit-query-dsl-guide"):
        assert mcp.read(f"nuxeo://{guide}").text


def test_introspection(mcp: Mcp) -> None:
    types = mcp.ok("nuxeo_list_document_types", {})["doctypes"]
    assert {"File", "Note", "Workspace"} <= set(types)
    schemas = {s["name"] for s in mcp.ok("nuxeo_get_metadata_schema", {})}
    assert {"dublincore", "file"} <= schemas
    operations = mcp.ok("nuxeo_list_operations", {})
    assert {"Document.Move", "Blob.AttachOnDocument"} <= set(operations)


def test_list_children(mcp: Mcp, ws: Dict[str, str]) -> None:
    def listing() -> str:
        r = str(mcp.ok("nuxeo_list_children", {"ref": ws["uid"]}))
        return r if ws["note"] in r else ""

    assert "| note |" in eventually(listing, "children of the run workspace")
    uris = mcp.ok("nuxeo_list_children", {"ref": ws["path"], "as_resource": True})
    assert f"nuxeo://{ws['note']}" in uris


def test_read(mcp: Mcp, ws: Dict[str, str]) -> None:
    run = ws["run"]
    by_path = mcp.ok("nuxeo_get_document", {"ref": f"{ws['path']}/note"})
    assert by_path.startswith(f"# Document: Note {run}")
    assert mcp.ok("nuxeo_get_document", {"ref": ws["note"]}) == by_path
    assert (
        mcp.ok("nuxeo_get_document", {"ref": ws["note"], "as_resource": True})
        == f"nuxeo://{ws['note']}"
    )
    assert mcp.read(f"nuxeo://{ws['note']}").text == by_path
    assert mcp.read(f"nuxeo://{ws['path'].lstrip('/')}/note").text == by_path

    blob = mcp.ok("nuxeo_get_document", {"ref": ws["upload"], "fetch_blob": True})
    assert blob == f"Hello from {run}"

    pdf = mcp.call(
        "nuxeo_get_document", {"ref": ws["upload"], "conversion_format": "pdf"}
    )
    assert not pdf.is_error, text(pdf)
    # Binary blobs come back base64-encoded in a text content.
    assert base64.b64decode(text(pdf)).startswith(b"%PDF")

    xml = mcp.ok("nuxeo_get_document", {"ref": ws["note"], "rendition": "xmlExport"})
    assert xml.startswith("<?xml")
    resource = mcp.read(f"nuxeo://{ws['note']}@rendition/xmlExport")
    assert resource.mimeType.startswith("text/xml")


def test_execute_operation(mcp: Mcp, ws: Dict[str, str]) -> None:
    mcp.ok(
        "nuxeo_execute_operation",
        {
            "operation_id": "Blob.AttachOnDocument",
            "params": {"document": f"{ws['path']}/file", "xpath": "file:content"},
            "input_type": "file",
            "file_path": ws["upload_file"],
        },
    )
    blob = mcp.ok("nuxeo_get_document", {"ref": ws["file"], "fetch_blob": True})
    assert blob == f"Hello from {ws['run']}"


def test_update_and_move(mcp: Mcp, ws: Dict[str, str]) -> None:
    run = ws["run"]
    note_path = f"{ws['path']}/note"
    updated = mcp.ok(
        "nuxeo_update_metadata",
        {"path": note_path, "properties": {"dc:description": f"Updated {run}"}},
    )
    assert f"Updated {run}" in updated
    updated = mcp.ok(
        "nuxeo_update_metadata",
        {"uid": ws["note"], "properties": {"dc:title": f"Note {run} v2"}},
    )
    assert updated.startswith(f"# Document: Note {run} v2")
    mcp.fails(
        "nuxeo_update_metadata",
        {"path": note_path, "uid": ws["note"], "properties": {"dc:title": "x"}},
    )

    moved = mcp.ok(
        "nuxeo_move_document",
        {"document_uid": ws["note"], "target_path": f"{ws['path']}/target"},
    )
    assert moved["path"] == f"{ws['path']}/target/note"
    moved = mcp.ok(
        "nuxeo_move_document", {"document_uid": ws["note"], "target_path": ws["path"]}
    )
    assert moved["path"] == note_path


def test_update_after_a_concurrent_edit_conflicts(
    mcp: Mcp, ws: Dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partial update must not overwrite an edit made since the tool read."""
    nuxeo = mcp.server.nuxeo
    assert nuxeo is not None
    doc = mcp.ok(
        "nuxeo_create_document",
        {
            "parent_path": ws["path"],
            "name": "conflict",
            "type": "Note",
            "properties": {"dc:title": "Before"},
        },
    )
    real_get = nuxeo.documents.get

    def get_then_edit(self: Any, **kwargs: Any) -> Any:
        stale = real_get(**kwargs)
        nuxeo.documents.put(
            Document(
                uid=stale.uid,
                changeToken=stale.changeToken,
                properties={"dc:title": "Concurrent"},
            )
        )
        return stale

    # API objects use __slots__: patch the class, restored below.
    monkeypatch.setattr(type(nuxeo.documents), "get", get_then_edit)
    error = mcp.fails(
        "nuxeo_update_metadata",
        {"uid": doc["uid"], "properties": {"dc:title": "Lost"}},
    )
    monkeypatch.undo()

    try:
        assert "409" in error or "change token" in error.lower()
        assert real_get(uid=doc["uid"]).title == "Concurrent"
    finally:
        # Keep the run workspace's per-type counts for test_search_query_dsl.
        mcp.ok("nuxeo_delete_document", {"uid": doc["uid"]})


def _subtree_nxql(ws: Dict[str, str]) -> str:
    return (
        f"SELECT * FROM Document WHERE ecm:ancestorId = '{ws['uid']}' "
        "AND ecm:isVersion = 0 AND ecm:isTrashed = 0"
    )


def test_search_nxql(mcp: Mcp, ws: Dict[str, str]) -> None:
    query = _subtree_nxql(ws)
    eventually(
        lambda: mcp.ok("nuxeo_search_documents", {"query": query})["totalCount"] == 4,
        "the 4 run documents in NXQL search",
    )
    fulltext = f"SELECT * FROM Note WHERE ecm:fulltext = 'fox' AND ecm:ancestorId = '{ws['uid']}'"
    eventually(
        lambda: any(
            h["id"] == ws["note"]
            for h in mcp.ok("nuxeo_search_documents", {"query": fulltext})["documents"]
        ),
        "the note in full-text search",
    )
    page = mcp.ok(
        "nuxeo_search_documents", {"query": query, "page_size": 1, "page_index": 1}
    )
    assert len(page["documents"]) == 1 and page["hasMore"] is True

    error = mcp.fails(
        "nuxeo_search_documents", {"query": query, "nxql_filter": "ecm:isProxy = 0"}
    )
    assert "only used by mode='semantic'" in error


def test_search_semantic_unavailable(mcp: Mcp) -> None:
    result = mcp.call("nuxeo_search_documents", {"query": "fox", "mode": "semantic"})
    if not result.is_error:
        pytest.skip("this server has vector search; semantic search is not covered")
    assert "search is not available on this Nuxeo server" in text(result)


def test_search_query_dsl(mcp: Mcp, ws: Dict[str, str]) -> None:
    subtree = [
        # Not ecm:ancestorId: LTS 2023 does not index it.
        {"term": {"ecm:path.children": ws["path"]}},
        {"term": {"ecm:isVersion": False}},
    ]
    match = {
        "size": 10,
        "_source": ["dc:title"],
        "query": {"bool": {"must": {"match": {"all_field": "fox"}}, "filter": subtree}},
    }

    def note_hit() -> Any:
        r = mcp.ok("nuxeo_search_documents_with_query_dsl", {"query": match})
        return r if any(h["_id"] == ws["note"] for h in r["hits"]["hits"]) else None

    assert "_nuxeo_executed_query" in eventually(note_hit, "the note in Query DSL")

    # ecm:path.children matches the workspace itself too.
    expected = {"File": 2, "Folder": 1, "Note": 1, "Workspace": 1}

    def buckets() -> Dict[str, int]:
        aggs = mcp.ok(
            "nuxeo_search_documents_with_query_dsl",
            {
                "query": {
                    "size": 0,
                    "query": {"bool": {"filter": subtree}},
                    "aggs": {"types": {"terms": {"field": "ecm:primaryType"}}},
                }
            },
        )
        found = {
            b["key"]: b["doc_count"] for b in aggs["aggregations"]["types"]["buckets"]
        }
        return found if found == expected else {}

    assert eventually(buckets, "the run documents in the aggregation") == expected

    empty = mcp.ok(
        "nuxeo_search_documents_with_query_dsl",
        {"query": {"query": {"term": {"no_such_field": "x"}}}},
    )
    assert "_nuxeo_hint" in empty

    error = mcp.fails(
        "nuxeo_search_documents_with_query_dsl",
        {"query": {"query": {"script": {"script": "true"}}}},
    )
    assert "Scripted queries are not allowed" in error


def test_search_audit(mcp: Mcp, ws: Dict[str, str]) -> None:
    query = {"size": 20, "query": {"term": {"docUUID": ws["file"]}}}
    assert mcp.server.nuxeo is not None
    if not mcp.server.nuxeo.users.current_user().isAdministrator:
        error = mcp.fails("nuxeo_search_audit_with_query_dsl", {"query": query})
        assert "restricted to administrators" in error
        return

    def events() -> Set[str]:
        r = mcp.ok("nuxeo_search_audit_with_query_dsl", {"query": query})
        found = {h["_source"].get("eventId") for h in r["hits"]["hits"]}
        return found if "documentCreated" in found else set()

    assert "documentCreated" in eventually(events, "the file creation in the audit")


def test_delete(mcp: Mcp, ws: Dict[str, str]) -> None:
    doc = mcp.ok(
        "nuxeo_create_document",
        {
            "parent_path": ws["path"],
            "name": "to-delete",
            "type": "Note",
            "properties": {"dc:title": "To delete"},
        },
    )
    assert mcp.ok("nuxeo_delete_document", {"uid": doc["uid"]})["status"] == "success"
    mcp.fails("nuxeo_get_document", {"ref": doc["uid"]})


def test_file_path_outside_the_upload_dir_is_refused(
    mcp: Mcp, ws: Dict[str, str]
) -> None:
    error = mcp.fails(
        "nuxeo_create_document",
        {
            "parent_path": ws["path"],
            "name": "outside",
            "type": "File",
            "properties": {"dc:title": "Outside"},
            "file_path": "/etc/hostname",
        },
    )
    assert "NUXEO_MCP_UPLOAD_DIR" in error


def test_every_tool_was_called(mcp: Mcp) -> None:
    """Runs last: a new tool must be added to this module."""
    assert mcp.tool_names() <= CALLED, f"Not covered: {mcp.tool_names() - CALLED}"
