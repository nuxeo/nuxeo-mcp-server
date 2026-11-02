# Nuxeo MCP Server Test Scenario

End-to-end check of every MCP tool and resource against a live Nuxeo server. Give
this file as a prompt to an agent connected to the Nuxeo MCP server.

The server may hold real content. The run must leave it exactly as it found it.

## Safety rules

- Only create documents inside the run workspace `WS` (defined below). The only
  document created outside it is `WS` itself.
- Never update, move or delete a document you did not create in this run. Every
  write tool call (`nuxeo_update_metadata`, `nuxeo_move_document`,
  `nuxeo_delete_document`, `nuxeo_execute_operation`) must target a uid noted
  in this run or a path starting with `WS/`. Before each call, check it; if it
  does not, record FAIL and skip the call.
- Do not call `nuxeo_execute_operation` with any operation other than the one in
  step 4.6.
- If `WS` already exists at step 4.1, stop the run: pick another `RUN` and start
  over. Never reuse or delete an existing workspace.
- Leave nothing behind: cleanup deletes `WS` permanently (not to the trash), and
  step 10.5 checks it is gone. Audit entries for the run remain; that is
  expected.

## Instructions for the agent

- Run every step in order, without asking for confirmation.
- Call the MCP tools and read the MCP resources directly. Do not write code.
- Check each step against its **Pass if** condition. Record PASS, FAIL (with the
  error) or SKIP (with the reason), then continue: a failure does not stop the run.
- Steps marked *retry* depend on the search index, `nuxeo_list_children`
  included: new, changed or moved documents can take a few seconds to show up. Retry up to 5 times, 2 seconds apart, before
  recording FAIL.
- Always run the Cleanup step, even after failures.
- End with the report table described in [Report](#report).

## Prerequisites

- The MCP server is connected to a Nuxeo server, as a user who can create
  documents under `/default-domain/workspaces`.
- Query DSL steps need the Nuxeo search passthrough (`/site/es`) with OpenSearch
  or Elasticsearch, for example `nuxeo-opensearch2-embed-package`.
- The audit step needs an administrator. Otherwise record SKIP.
- The upload step needs the agent and the MCP server to share a filesystem:
  `file_path` is read by the MCP server. Otherwise record SKIP.

Pick a random 8-character suffix `RUN`, for example `a1b2c3d4`. Below, `WS` is
`/default-domain/workspaces/mcp-test-RUN`.

## 1. Server

**1.1** `nuxeo_get_repository_info` with no arguments.
Pass if: the result has a `productVersion`.

**1.2** Read resource `nuxeo://info`.
Pass if: `connected` is `true` and `version` matches 1.1.

**1.3** Read resources `nuxeo://nxql-guide`, `nuxeo://query-dsl-guide`,
`nuxeo://audit-query-dsl-guide`.
Pass if: each returns non-empty text.

## 2. Introspection

**2.1** `nuxeo_list_document_types`.
Pass if: the types include `File`, `Note` and `Workspace`.

**2.2** `nuxeo_get_metadata_schema`.
Pass if: the schemas include `dublincore` and `file`.

**2.3** `nuxeo_list_operations`.
Pass if: the operations include `Document.Move` and `Blob.AttachOnDocument`.

## 3. Browse

**3.1** `nuxeo_list_children` with `ref` = `/default-domain`.
Pass if: the table lists `workspaces`. Note its uuid as `WORKSPACES_UID`.

**3.2** `nuxeo_list_children` with `ref` = `WORKSPACES_UID`.
Pass if: it returns a table (possibly empty).

**3.3** `nuxeo_list_children` with `ref` = `/default-domain`, `as_resource` = `true`.
Pass if: it returns `nuxeo://<uuid>` lines.

## 4. Create

**4.1** `nuxeo_create_document`: `parent_path` = `/default-domain/workspaces`,
`name` = `mcp-test-RUN`, `type` = `Workspace`,
`properties` = `{"dc:title": "MCP Test RUN"}`.
First check with `nuxeo_get_document` that `WS` does not exist (see Safety rules).
Pass if: `status` is `success` and `path` is `WS`. Note `uid` as `WS_UID`.

**4.2** `nuxeo_create_document`: `parent_path` = `WS`, `name` = `target`,
`type` = `Folder`, `properties` = `{"dc:title": "Target"}`.
Pass if: `status` is `success`.

**4.3** `nuxeo_create_document`: `parent_path` = `WS`, `name` = `note`,
`type` = `Note`, `properties` =
`{"dc:title": "Note RUN", "note:note": "<p>The quick brown fox jumps over the lazy dog RUN</p>"}`.
Pass if: `status` is `success`. Note `uid` as `NOTE_UID`.

**4.4** `nuxeo_create_document`: `parent_path` = `WS`, `name` = `file`,
`type` = `File`, `properties` = `{"dc:title": "File RUN"}`.
Pass if: `status` is `success`. Note `uid` as `FILE_UID`.

**4.5** Upload (needs a shared filesystem). Write `/tmp/mcp-test-RUN.txt`
containing `Hello from RUN`. Then `nuxeo_create_document`: `parent_path` = `WS`,
`name` = `upload`, `type` = `File`, `properties` = `{"dc:title": "Upload RUN"}`,
`file_path` = `/tmp/mcp-test-RUN.txt`.
Pass if: `status` is `success`. Note `uid` as `UPLOAD_UID`.

**4.6** Upload through an operation (needs a shared filesystem).
`nuxeo_execute_operation`: `operation_id` = `Blob.AttachOnDocument`,
`params` = `{"document": "WS/file", "xpath": "file:content"}`,
`input_type` = `file`, `file_path` = `/tmp/mcp-test-RUN.txt`.
Pass if: no error.

## 5. Read

**5.1** `nuxeo_get_document` with `ref` = `WS/note`.
Pass if: the markdown starts with `# Document: Note RUN` and shows `**Type**: Note`.

**5.2** `nuxeo_get_document` with `ref` = `NOTE_UID`.
Pass if: same document as 5.1.

**5.3** `nuxeo_get_document` with `ref` = `UPLOAD_UID`, `fetch_blob` = `true`
(SKIP if 4.5 was skipped).
Pass if: the content is `Hello from RUN`.

**5.4** `nuxeo_get_document` with `ref` = `UPLOAD_UID`, `conversion_format` = `pdf`
(SKIP if 4.5 was skipped).
Pass if: a PDF blob is returned. If the error names a missing converter, record
SKIP.

**5.5** `nuxeo_get_document` with `ref` = `NOTE_UID`, `rendition` = `xmlExport`.
Pass if: an XML export of the note is returned.

**5.6** `nuxeo_get_document` with `ref` = `NOTE_UID`, `as_resource` = `true`.
Pass if: the result is `nuxeo://NOTE_UID`.

**5.7** Read resources `nuxeo://NOTE_UID` and `nuxeo://WS/note` (path without
the leading slash).
Pass if: both return the markdown of 5.1.

**5.8** Read resource `nuxeo://NOTE_UID@rendition/xmlExport`.
Pass if: an XML export of the note is returned.

## 6. Update and move

**6.1** `nuxeo_update_metadata`: `path` = `WS/file`,
`properties` = `{"dc:description": "Updated RUN"}`.
Pass if: the markdown shows `Updated RUN`.

**6.2** `nuxeo_update_metadata`: `uid` = `FILE_UID`,
`properties` = `{"dc:title": "File RUN v2"}`.
Pass if: the markdown starts with `# Document: File RUN v2`.

**6.3** `nuxeo_update_metadata` with both `path` and `uid`.
Pass if: it fails with an error asking for only one of them.

**6.4** `nuxeo_move_document`: `document_uid` = `FILE_UID`, `target_path` = `WS/target`.
Pass if: `status` is `success` and `path` is `WS/target/file`.

**6.5** *retry* `nuxeo_list_children` with `ref` = `WS/target`.
Pass if: the table lists `file` with title `File RUN v2`.

## 7. NXQL search

**7.1** *retry* `nuxeo_search_documents`: `query` =
`SELECT * FROM Document WHERE ecm:ancestorId = 'WS_UID' AND ecm:isVersion = 0 AND ecm:isTrashed = 0`.
Pass if: `totalCount` is 4 (target, note, file, upload) or 3 if 4.5 was skipped.

**7.2** *retry* `nuxeo_search_documents`: `query` =
`SELECT * FROM Note WHERE ecm:fulltext = 'fox' AND ecm:ancestorId = 'WS_UID'`.
Pass if: `documents` contains `NOTE_UID`.

**7.3** `nuxeo_search_documents`: `query` = the query of 7.1, `page_size` = 1,
`page_index` = 1.
Pass if: one document is returned and `hasMore` is `true`.

**7.4** `nuxeo_search_documents`: `query` = `fox`, `mode` = `semantic`.
Pass if: it fails with `Semantic search is not available on this Nuxeo server`.
Semantic search is not covered yet: on a server with vector search, record SKIP.

**7.5** `nuxeo_search_documents`: `query` = the query of 7.1, `nxql_filter` = `ecm:isProxy = 0`.
Pass if: it fails with an error saying `nxql_filter` is only for semantic mode.

## 8. Query DSL search

**8.1** *retry* `nuxeo_search_documents_with_query_dsl`: `query` =
`{"size": 10, "_source": ["dc:title", "ecm:path"], "query": {"bool": {"must": {"match": {"all_field": "fox"}}, "filter": [{"term": {"ecm:ancestorId": "WS_UID"}}, {"term": {"ecm:isVersion": false}}]}}}`.
Pass if: the hits contain `NOTE_UID` and the result has `_nuxeo_executed_query`.

**8.2** `nuxeo_search_documents_with_query_dsl`: `query` =
`{"size": 0, "query": {"bool": {"filter": [{"term": {"ecm:ancestorId": "WS_UID"}}, {"term": {"ecm:isVersion": false}}]}}, "aggs": {"types": {"terms": {"field": "ecm:primaryType"}}}}`.
Pass if: the `types` buckets are `File` (2, or 1 if 4.5 was skipped), `Folder` (1)
and `Note` (1).

**8.3** `nuxeo_search_documents_with_query_dsl`: `query` =
`{"query": {"term": {"no_such_field": "x"}}}`.
Pass if: no hits, and `_nuxeo_hint` is set.

**8.4** `nuxeo_search_documents_with_query_dsl`: `query` =
`{"query": {"script": {"script": "true"}}}`.
Pass if: it fails with an error refusing scripts.

## 9. Audit search (administrator only)

**9.1** *retry* `nuxeo_search_audit_with_query_dsl`: `query` =
`{"size": 20, "query": {"term": {"docUUID": "FILE_UID"}}}`.
Pass if: the hits include the `eventId` values `documentCreated` and
`documentModified`. If the error says administrators only, record SKIP.

## 10. Cleanup (always run)

**10.1** `nuxeo_delete_document` with `uid` = `NOTE_UID`.
Pass if: `status` is `success`.

**10.2** `nuxeo_get_document` with `ref` = `NOTE_UID`.
Pass if: it fails with not found. A trashed document counts as FAIL.

**10.3** `nuxeo_delete_document` with `uid` = `WS_UID`. This deletes everything
created in the run. If `WS_UID` is unknown because 4.1 failed after creating
it, read `WS` with `nuxeo_get_document` first, and delete it only if its title
is `MCP Test RUN`.
Pass if: `status` is `success`.

**10.4** Delete `/tmp/mcp-test-RUN.txt` if it was created.

**10.5** `nuxeo_get_document` with `ref` = `WS`, then with `ref` = `FILE_UID`
and `UPLOAD_UID`.
Pass if: every call fails with not found. Otherwise report the leftover
documents by path and uid.

## Report

Print one table, one row per step: step number, tool or resource, PASS / FAIL /
SKIP, and the error or reason. Then a coverage line listing any of the 14 tools
below that has no PASS:

`nuxeo_get_repository_info`, `nuxeo_list_document_types`,
`nuxeo_get_metadata_schema`, `nuxeo_list_operations`, `nuxeo_list_children`,
`nuxeo_create_document`, `nuxeo_execute_operation`, `nuxeo_get_document`,
`nuxeo_update_metadata`, `nuxeo_move_document`, `nuxeo_search_documents`,
`nuxeo_search_documents_with_query_dsl`, `nuxeo_search_audit_with_query_dsl`,
`nuxeo_delete_document`.
