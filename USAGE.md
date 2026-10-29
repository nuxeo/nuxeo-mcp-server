# Usage Guide

This guide provides information for users who want to use the Nuxeo MCP Server.

## Installation

<details open>
<summary>Using uv (recommended)</summary>

```bash
uv sync --frozen
```

</details>

<details>
<summary>Using pip</summary>

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

</details>

## Configuration

The Nuxeo MCP Server can be configured using a configuration file or environment variables.

### Configuration File

Create a file named `nuxeo_mcp_config.json` with the following content:

```json
{
  "nuxeo_url": "http://localhost:8080/nuxeo",
  "username": "Administrator",
  "password": "Administrator"
}
```

### Environment Variables

You can also configure the Nuxeo MCP Server using environment variables:

```bash
export NUXEO_URL=http://localhost:8080/nuxeo
export NUXEO_USERNAME=Administrator
export NUXEO_PASSWORD=Administrator
```

## Running the Server

You can run the MCP server using one of the following methods:

<details open>
<summary>Using uv (recommended)</summary>

```bash
uv run nuxeo-mcp

# Or directly with Python module
uv run python -m nuxeo_mcp
```

</details>

<details>
<summary>Using pip</summary>

```bash
# After activating your virtual environment

# Using the entry point script
nuxeo-mcp

# Or directly with Python module
python -m nuxeo_mcp
```

</details>

## Available Tools

<!-- BEGIN GENERATED TOOLS -->

14 tools, generated from the registered MCP schema by `scripts/generate_tool_reference.py` -- do not edit by hand.

| Tool | Read-only | Destructive | Open-world | Description |
|------|-----------|-------------|------------|-------------|
| `nuxeo_create_document` | no | no | no | Create a new document in the Nuxeo repository with optional file attachment. To confirm the result, read it back with nuxeo_get_document; search may not see it yet. |
| `nuxeo_delete_document` | no | yes | no | Delete a document from the Nuxeo repository, by UID. To delete by path, read the UID with nuxeo_get_document first. |
| `nuxeo_execute_operation` | no | yes | yes | Execute a Nuxeo Operation with the specified parameters and input |
| `nuxeo_get_document` | yes | no | no | Get a document from the Nuxeo repository |
| `nuxeo_get_metadata_schema` | yes | no | no | Get detailed information about schemas defined in the Nuxeo server |
| `nuxeo_get_repository_info` | yes | no | no | Get information about the Nuxeo repository |
| `nuxeo_list_children` | yes | no | no | list children of a folder document |
| `nuxeo_list_document_types` | yes | no | no | Get information about document types and schemas defined in the Nuxeo server |
| `nuxeo_list_operations` | yes | no | no | Get information about available Automation Operations in the Nuxeo server |
| `nuxeo_move_document` | no | yes | no | Move a document, identified by UID, under the folder at target_path. Not idempotent: repeating the call renames the document. To move by path, read the UID with nuxeo_get_document first. |
| `nuxeo_search_audit_with_query_dsl` | yes | no | yes | Run a raw OpenSearch/Elasticsearch Query DSL request against the Nuxeo audit log index and return the engine response, plus two server-added keys: _nuxeo_executed_query (the guarded request) and _nuxeo_hint (set on empty results). Administrators only. Read nuxeo://audit-query-dsl-guide first for the field names. |
| `nuxeo_search_documents` | yes | no | no | Search documents in the Nuxeo repository. mode='nxql' (default) runs a NXQL statement: read nuxeo://nxql-guide first, it gives the default filter that keeps versions and system documents out. mode='semantic' matches a question or phrase on meaning, only on servers with vector search; elsewhere it fails with an error saying so. Returns a normalized result envelope. For counts, groupings or aggregations, use nuxeo_search_documents_with_query_dsl instead. Recently created or modified documents may take a few seconds to appear; read them by uid or path with nuxeo_get_document instead. |
| `nuxeo_search_documents_with_query_dsl` | yes | no | yes | Run a raw OpenSearch/Elasticsearch Query DSL request against the Nuxeo repository index and return the engine response, plus two server-added keys: _nuxeo_executed_query (the guarded request) and _nuxeo_hint (set on empty results). Use this for aggregations, highlighting, sorting and any query the normalized search cannot express. Read nuxeo://query-dsl-guide first for the field names. Recently created or modified documents may take a few seconds to appear; read them by uid or path with nuxeo_get_document instead. |
| `nuxeo_update_metadata` | no | yes | no | Update an existing document in the Nuxeo repository |

<!-- END GENERATED TOOLS -->

## Available Resources

The Nuxeo MCP Server provides the following resources:

- `nuxeo://info`: Basic information about the connected Nuxeo server
- `nuxeo://{uid}`: Get a document by UID, e.g. `nuxeo://12345678-1234-1234-1234-123456789012`
- `nuxeo://{path}`: Get a document by path, e.g. `nuxeo://default-domain/workspaces/my-document`
- `nuxeo://nxql-guide`: NXQL for `nuxeo_search_documents`, starting with the default filter
- `nuxeo://query-dsl-guide`: Field reference for `nuxeo_search_documents_with_query_dsl`
- `nuxeo://audit-query-dsl-guide`: Field reference for `nuxeo_search_audit_with_query_dsl`

## Examples

### Get Repository Information

```python
from fastmcp import use_tool

result = use_tool("nuxeo", "nuxeo_get_repository_info", {})
print(result)
```

### Search for Documents

`nuxeo_search_documents` runs a NXQL statement and returns a normalized
envelope. Read the `nuxeo://nxql-guide` resource first: it gives the default
filter that keeps versions, proxies, trashed and system documents out.

```python
from fastmcp import use_tool

result = use_tool("nuxeo", "nuxeo_search_documents", {
    "query": (
        "SELECT * FROM File WHERE ecm:fulltext = 'budget'"
        " AND ecm:mixinType != 'HiddenInNavigation' AND ecm:isProxy = 0"
        " AND ecm:isVersion = 0 AND ecm:isTrashed = 0"
        " ORDER BY dc:modified DESC"
    ),
    "page_size": 10,
    "page_index": 0,
})

print(result["interpretedQuery"])  # the NXQL that ran
print(result["totalCount"], "matches,", "more pages" if result["hasMore"] else "last page")

for doc in result["documents"]:
    print(doc["id"], doc["documentType"], doc["title"], doc["path"])
```

`mode` defaults to `"nxql"`.

#### `mode="semantic"`

Matches a question or phrase on meaning rather than keywords, against the Nuxeo
vector index. **Most Nuxeo servers have no vector index**: there the call fails
with an error saying semantic search is not available and naming the
exact-match alternatives (`mode="nxql"` with `ecm:fulltext`, or the Query DSL
tool). An agent should not retry semantic mode after that error.

**Use it as a fulltext search by meaning, with basic filtering.** It is not a
general NXQL engine: the query text is the point, and `nxql_filter` is a
best-effort narrowing over a small set of indexed scalar fields. If you need
real query expressiveness (conditions on arbitrary properties, `OR`, `LIKE`,
sorting) use `mode="nxql"`; for aggregations use
`nuxeo_search_documents_with_query_dsl`.

```python
result = use_tool("nuxeo", "nuxeo_search_documents", {
    "query": "what causes musty cork taint from chlorine and mould",
    "mode": "semantic",
    # semantic-only, both optional
    "nxql_filter": "ecm:primaryType = 'File' AND ecm:isProxy = 0 AND ecm:isVersion = 0",
    "include_snippets": True,
})

for doc in result["documents"]:
    print(doc["score"], doc["title"])
    for passage in doc["snippets"]:
        print("   ", passage)
```

Notes:

- **Phrase it as a question or a domain-rich sentence.** Hybrid scoring combines
  neural and BM25 signals, so two or three keywords rank markedly worse.
- `interpretedQuery` reports the NXQL that ran: the vector client embeds the
  `ecm:fulltext` term and still applies the remaining scalar predicates.
- `nxql_filter` replaces the default
  `ecm:mixinType <> 'HiddenInNavigation' AND ecm:isProxy = 0 AND ecm:isVersion = 0`.
  `ecm:isTrashed` is not in the default vector mapping, so trashed documents
  cannot be filtered out here.
  **A clause the vector client cannot translate is dropped, not refused**: the
  filter is not applied, you get more documents than you asked for, and nothing
  reports it.

  Filterable fields come from the index mapping, not from NXQL. Defaults:

  | Kind | Fields |
  |---|---|
  | keyword | `ecm:primaryType`, `ecm:mixinType`, `ecm:ancestorId`, `ecm:tag`, `ecm:uuid`, `ecm:repository` |
  | path | `ecm:path` |
  | boolean | `ecm:isProxy`, `ecm:isVersion` |
  | range | `dc:modified`, `chunk_id` |

  A deployment can extend this with its own mapping file. Anything unmapped
  (`dc:title`, `dc:description`, custom schema fields) is dropped.

  Operators: `=` `<>` `IN` `NOT IN` `IS [NOT] NULL` on any filterable field;
  `<` `<=` `>` `>=` `BETWEEN` `NOT BETWEEN` on range fields only; `STARTSWITH`
  on `ecm:path` only. `OR` and `NOT` discard the whole sub-expression. `LIKE`
  is never supported. `ORDER BY` is ignored; results are ranked by relevance.
- `score` is filled only when the search client exposes it; otherwise it stays
  null.
- **`totalCount` does not mean "total matches" in this mode.** k-NN has no
  exhaustive match count, so it reports how many candidates the retrieval
  considered, and it grows with `page_size`. `hasMore` is true for the same
  reason. Use it for "there is more to page through", never as a corpus total.

Calling the tool with an empty query returns usage help with a worked example
instead of an error.

### Query DSL Search

`nuxeo_search_documents_with_query_dsl` takes a raw Elasticsearch/OpenSearch
request body and returns the engine response, plus two server-added keys:
`_nuxeo_executed_query` (the request after guardrails) and `_nuxeo_hint` (set
when nothing matches). Use it for
aggregations, highlighting, sorting and anything the normalized search cannot
express.

Read the `nuxeo://query-dsl-guide` resource first: the search passthrough
exposes `_search` only, so field names cannot be discovered at runtime, and an
unknown field matches nothing rather than raising an error.

```python
from fastmcp import use_tool

# Full-text search with highlighting. Query `all_field`, but highlight
# analysed fields: `all_field` is a copy_to catch-all, never stored, so the
# highlighter has no text to fragment for it. String properties are keyword
# fields with an analysed `.fulltext` subfield; highlight the subfield.
result = use_tool("nuxeo", "nuxeo_search_documents_with_query_dsl", {
    "query": {
        "size": 10,
        "_source": ["dc:title", "ecm:path"],
        "query": {"match": {"all_field": "quarterly report"}},
        "highlight": {
            "require_field_match": False,
            "fields": {
                "dc:title.fulltext": {},
                "dc:description.fulltext": {},
                "ecm:binarytext": {"fragment_size": 150, "number_of_fragments": 3},
            },
        },
    }
})

for hit in result["hits"]["hits"]:
    print(hit["_score"], hit["_source"]["dc:title"], hit.get("highlight"))

# Count documents per type -- aggregation only, no hits
result = use_tool("nuxeo", "nuxeo_search_documents_with_query_dsl", {
    "query": {
        "size": 0,
        "aggs": {"types": {"terms": {"field": "ecm:primaryType", "size": 20}}},
    }
})
for bucket in result["aggregations"]["types"]["buckets"]:
    print(bucket["key"], bucket["doc_count"])

# Pull the extracted binary text of a few documents
result = use_tool("nuxeo", "nuxeo_search_documents_with_query_dsl", {
    "query": {
        "size": 3,
        "_source": ["dc:title", "ecm:binarytext"],
        "query": {"match": {"all_field": "water chemistry pH"}},
    }
})
```

Results are already filtered to what the authenticated user may read; Nuxeo
applies the ACLs server-side. Do not filter on `ecm:acl` yourself.

**Limits.** `size` defaults to 10 and is capped at 100, `from` is capped at
1000, `top_hits` and `inner_hits` are capped at 10 each, responses are capped
at 256 KiB, `_source` defaults to a small projection, and scripted queries are
rejected: any key named `script` or ending in `_script`, which also makes a
field with such a name unqueryable. Without them an unqualified `match_all`
with `size: 10000` returns several megabytes.

**Efficiency.** The limits bound the worst case only; the search cluster is
shared with the application. Both field guides carry a "Writing efficient
queries" section: `size: 0` for counts, exact conditions in `bool.filter`, a
short `_source` list, shallow aggregations with small bucket sizes, no leading
wildcards or `regexp` on text fields, and no deep paging.

### Audit Search (Admin Only)

`nuxeo_search_audit_with_query_dsl` is the same mechanism against the audit
index. Audit entries are events, not documents, so they are returned in the
engine shape rather than the document envelope. See
`nuxeo://audit-query-dsl-guide` for the field names.

```python
from fastmcp import use_tool

# Deletions over the last day
result = use_tool("nuxeo", "nuxeo_search_audit_with_query_dsl", {
    "query": {
        "size": 50,
        "query": {"bool": {"filter": [
            {"term": {"eventId": "documentRemoved"}},
            {"range": {"eventDate": {"gte": "now-1d"}}},
        ]}},
        "sort": [{"eventDate": "desc"}],
    }
})

for hit in result["hits"]["hits"]:
    event = hit["_source"]
    print(event["eventDate"], event["eventId"], event["principalName"], event["docPath"])

# Who is most active
result = use_tool("nuxeo", "nuxeo_search_audit_with_query_dsl", {
    "query": {
        "size": 0,
        "aggs": {"users": {"terms": {"field": "principalName", "size": 20}}},
    }
})
```

Non-administrators receive an error: Nuxeo restricts the audit index
server-side.

### Get a Document

```python
from fastmcp import use_tool

# Get document metadata; `ref` is a path or a UID
result = use_tool("nuxeo", "nuxeo_get_document", {
    "ref": "/default-domain/workspaces/My Workspace/My Document"
})
print(result)

# Get document blob
blob = use_tool("nuxeo", "nuxeo_get_document", {
    "ref": "/default-domain/workspaces/My Workspace/My Document",
    "fetch_blob": True
})

# Get document thumbnail
thumbnail = use_tool("nuxeo", "nuxeo_get_document", {
    "ref": "/default-domain/workspaces/My Workspace/My Document",
    "rendition": "thumbnail"
})
```

### Create a Document

```python
from fastmcp import use_tool

result = use_tool("nuxeo", "nuxeo_create_document", {
    "parent_path": "/default-domain/workspaces/My Workspace",
    "name": "My New Document",
    "type": "File",
    "properties": {
        "dc:title": "My New Document",
        "dc:description": "This is a new document"
    }
})
print(result)
```

### Update a Document

```python
from fastmcp import use_tool

result = use_tool("nuxeo", "nuxeo_update_metadata", {
    "path": "/default-domain/workspaces/My Workspace/My Document",
    "properties": {
        "dc:title": "Updated Title",
        "dc:description": "This document has been updated"
    }
})
print(result)
```

### Delete a Document

```python
from fastmcp import use_tool

# Deletion takes a UID only, not a path
result = use_tool("nuxeo", "nuxeo_delete_document", {
    "uid": "12345678-1234-1234-1234-123456789012"
})
print(result)
```

## Configuring with Cline

To use the Nuxeo MCP server with Cline, you need to add a configuration to your Cline MCP settings file. Here's an example configuration:

```json
{
  "mcpServers": {
    "nuxeo": {
      "command": "python",
      "args": ["-m", "nuxeo_mcp"]
    }
  }
}
```

For more detailed examples, see the [Nuxeo MCP Server Configuration Examples](./nuxeo_mcp_config.md).

## Troubleshooting

### Connection Issues

If you're having trouble connecting to the Nuxeo server, check the following:

- Make sure the Nuxeo server is running
- Check that the URL, username, and password are correct
- Check that the Nuxeo server is accessible from your machine

### Authentication Issues

If you're having authentication issues, check the following:

- Make sure the username and password are correct
- Check that the user has the necessary permissions
- Try using the Nuxeo web interface to verify your credentials

### Using the MCP Inspector

The MCP Inspector is a tool that helps you debug MCP servers. You can use it to inspect the tools and resources provided by the Nuxeo MCP Server.

To use the MCP Inspector:

1. Install the MCP Inspector:

```bash
npm install -g @modelcontextprotocol/inspector
```

2. Run the MCP Inspector with the Nuxeo MCP Server using the provided configuration file:

```bash
DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector \
  --config mcp.json \
  --server default
```

Note: The `DANGEROUSLY_OMIT_AUTH=true` flag is used to bypass authentication for local testing. Do not use this in production environments.

3. The MCP Inspector will start a web server that you can access at http://localhost:6277

4. Use the MCP Inspector to explore the tools and resources provided by the Nuxeo MCP Server:
   - View available tools and their input schemas
   - Test tools with different inputs
   - View available resources and their content
   - Monitor requests and responses

The MCP Inspector is particularly useful for:
- Understanding the capabilities of the Nuxeo MCP Server
- Testing tools with different inputs
- Debugging issues with tools and resources
- Learning how to use the Nuxeo MCP Server effectively

### Common Errors

#### "Cannot connect to Nuxeo server"

This error occurs when the MCP server cannot connect to the Nuxeo server. Check that the Nuxeo server is running and that the URL is correct.

#### "Authentication failed"

This error occurs when the MCP server cannot authenticate with the Nuxeo server. Check that the username and password are correct.

#### "Document not found"

This error occurs when the MCP server cannot find a document at the specified path or with the specified ID. Check that the path or ID is correct.

## Best Practices

### Error Handling

Always handle errors when using the Nuxeo MCP Server. Tools and resources may return errors if there are issues with the Nuxeo server or with the input parameters.

```python
from fastmcp import use_tool

try:
    result = use_tool("nuxeo", "nuxeo_get_document", {
        "ref": "/default-domain/workspaces/My Workspace/My Document"
    })
    print(result)
except Exception as e:
    print(f"Error: {e}")
```

### Performance Considerations

- Use `page_size` and `page_index` when searching; `page_size` is capped at 100 and `hasMore` tells you whether to page again
- Use the `schemas` parameter when getting documents to limit the properties returned
- Use the `enrichers` parameter when getting documents to include additional information
