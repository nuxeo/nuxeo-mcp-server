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
| `nuxeo_create_document` | no | no | no | Create a new document in the Nuxeo repository with optional file attachment |
| `nuxeo_delete_document` | no | yes | no | Delete a document from the Nuxeo repository |
| `nuxeo_execute_operation` | no | yes | yes | Execute a Nuxeo Operation with the specified parameters and input |
| `nuxeo_get_document` | yes | no | no | Get a document from the Nuxeo repository |
| `nuxeo_get_metadata_schema` | yes | no | no | Get detailed information about schemas defined in the Nuxeo server |
| `nuxeo_get_repository_info` | yes | no | no | Get information about the Nuxeo repository |
| `nuxeo_list_children` | yes | no | no | list children of a folder document |
| `nuxeo_list_document_types` | yes | no | no | Get information about document types and schemas defined in the Nuxeo server |
| `nuxeo_list_operations` | yes | no | no | Get information about available Automation Operations in the Nuxeo server |
| `nuxeo_move_document` | no | yes | no | Move a document to a different location in the Nuxeo repository |
| `nuxeo_search_audit_with_query_dsl` | yes | no | yes | Run a raw Elasticsearch/OpenSearch Query DSL request against the Nuxeo audit log index and return the engine response unchanged. Administrators only. Read nuxeo://audit-query-dsl-guide first for the field names. |
| `nuxeo_search_documents` | yes | no | no | Search documents in the Nuxeo repository. Use mode='natural' for a plain-English query, mode='nxql' for an exact NXQL statement, mode='semantic' to match on meaning rather than keywords. Returns a normalized result envelope that is identical for every mode. For counts, groupings or aggregations, use nuxeo_search_documents_with_query_dsl instead. |
| `nuxeo_search_documents_with_query_dsl` | yes | no | yes | Run a raw Elasticsearch/OpenSearch Query DSL request against the Nuxeo repository index and return the engine response unchanged. Use this for aggregations, highlighting, sorting and any query the normalized search cannot express. Read nuxeo://query-dsl-guide first for the field names. |
| `nuxeo_update_metadata` | no | yes | no | Update an existing document in the Nuxeo repository |

<!-- END GENERATED TOOLS -->

## Available Resources

The Nuxeo MCP Server provides the following resources:

- `nuxeo://info`: Basic information about the connected Nuxeo server
- `nuxeo://document/{path}`: Get a document by path
- `nuxeo://document/id/{uid}`: Get a document by ID
- `nuxeo://nxql-guide`: Comprehensive NXQL query language documentation

## Examples

### Get Repository Information

```python
from fastmcp import use_tool

result = use_tool("nuxeo", "nuxeo_get_repository_info", {})
print(result)
```

### Search for Documents

`nuxeo_search_documents` returns the same envelope whatever the mode, so you
never have to branch on the shape of the result.

```python
from fastmcp import use_tool

# mode="nxql" -- an exact NXQL statement
result = use_tool("nuxeo", "nuxeo_search_documents", {
    "query": "SELECT * FROM Document WHERE ecm:primaryType = 'File'",
    "mode": "nxql",
    "page_size": 10,
    "page_index": 0,
})

# mode="natural" (the default) -- plain English, converted to NXQL
result = use_tool("nuxeo", "nuxeo_search_documents", {
    "query": "PDFs created by john in the last month",
    "mode": "natural",
})

# interpretedQuery always reports the NXQL that actually ran, so a generated
# query can be inspected and corrected.
print(result["interpretedQuery"])
print(result["totalCount"], "matches,", "more pages" if result["hasMore"] else "last page")

for doc in result["documents"]:
    print(doc["id"], doc["documentType"], doc["title"], doc["path"])
    # score and snippets are populated by ranking modes and empty otherwise
    print(doc["score"], doc["snippets"])

# If natural-language parsing fails, the call still succeeds with a fulltext
# fallback and says so rather than returning an empty page.
if result["degraded"]:
    print("degraded:", result["degraded"])
```

#### `mode="semantic"`

Matches on meaning rather than keywords, against the Nuxeo vector index.

```python
result = use_tool("nuxeo", "nuxeo_search_documents", {
    "query": "what causes musty cork taint from chlorine and mould",
    "mode": "semantic",
    # semantic-only, both optional
    "nxql_filter": "ecm:primaryType = 'File' AND ecm:isProxy=0 AND ecm:isVersion=0",
    "include_snippets": True,
})

for doc in result["documents"]:
    print(doc["score"], doc["title"])
    for passage in doc["snippets"]:
        print("   ", passage)
```

Notes:

- **Phrase it as a question or a domain-rich sentence.** Hybrid scoring combines
  neural and BM25 signals, so two or three keywords rank markedly worse than
  `"what causes musty cork taint from chlorine and mould"`.
- `interpretedQuery` reports the NXQL that ran, exactly as in the other modes —
  the vector client embeds the `ecm:fulltext` term and still applies the
  remaining scalar predicates.
- `nxql_filter` replaces the default `ecm:isProxy=0 AND ecm:isVersion=0`.
  **A clause the vector client cannot translate is dropped, not refused** — the
  filter is not applied, you get more documents than you asked for, and nothing
  reports it. Verified: `dc:title LIKE '%nothing-matches-this%'` returned the
  same 46 documents as no filter at all, with `degraded` null.

  Filterable fields come from the index mapping, not from NXQL. Defaults:

  | Kind | Fields |
  |---|---|
  | keyword | `ecm:primaryType`, `ecm:mixinType`, `ecm:ancestorId`, `ecm:tag`, `ecm:uuid`, `ecm:repository` |
  | path | `ecm:path` |
  | boolean | `ecm:isProxy`, `ecm:isVersion` |
  | range | `dc:modified`, `chunk_id` |

  A deployment can extend this with its own mapping file. Anything unmapped —
  `dc:title`, `dc:description`, custom schema fields — is dropped.

  Operators: `=` `<>` `IN` `NOT IN` `IS [NOT] NULL` on any filterable field;
  `<` `<=` `>` `>=` `BETWEEN` `NOT BETWEEN` on range fields only; `STARTSWITH`
  on `ecm:path` only. `OR` and `NOT` discard the whole sub-expression. `LIKE`
  is never supported. `ORDER BY` is ignored; results are ranked by relevance.
- `score` requires **Nuxeo 2025.22+**. On older servers the enricher is unknown,
  the field is simply absent, and `score` stays null.
- **`totalCount` does not mean "total matches" in this mode.** k-NN has no
  exhaustive match count, so it reports how many candidates the retrieval
  considered, and it grows with `page_size` (measured: 7/17/28/46/78 for page
  sizes 2/5/10/20/50). `hasMore` is true for the same reason. Use it for
  "there is more to page through", never as a corpus total.
- If the vector backend is unavailable the tool raises with the engine's own
  error, naming `mode="natural"` and `mode="nxql"` as the alternatives.

Calling the tool with an empty query returns usage help with worked examples
instead of an error.

### Query DSL Search

`nuxeo_search_documents_with_query_dsl` takes a raw Elasticsearch/OpenSearch
request body and returns the engine response unchanged. Use it for
aggregations, highlighting, sorting and anything the normalized search cannot
express. It is **not** a natural-language tool.

Read the `nuxeo://query-dsl-guide` resource first: the search passthrough
exposes `_search` only, so field names cannot be discovered at runtime, and an
unknown field matches nothing rather than raising an error.

```python
from fastmcp import use_tool

# Full-text search with highlighting. Query `all_field`, but highlight
# source-backed fields: `all_field` is a copy_to catch-all, never stored, so
# the highlighter has no text to fragment for it.
result = use_tool("nuxeo", "nuxeo_search_documents_with_query_dsl", {
    "query": {
        "size": 10,
        "_source": ["dc:title", "ecm:path"],
        "query": {"match": {"all_field": "quarterly report"}},
        "highlight": {
            "require_field_match": False,
            "fields": {
                "dc:title": {},
                "dc:description": {},
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
1000, responses are capped at 256 KiB, `_source` defaults to a small
projection, and scripted queries (`script`, `script_fields`, `script_score`)
are rejected. Without them an unqualified `match_all` with `size: 10000`
returns several megabytes.

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

#### Natural Language Patterns

`mode="natural"` understands these patterns:

**Document Types:** "find all invoices", "show me PDFs", "list folders"

**Time:** "documents created today", "files from last week", "files since 2024-01-01"

**Users:** "documents created by john", "alice's files"

**Content:** "documents containing 'budget'", "files with title 'Project Report'"

**Paths:** "documents in folder '/workspaces/project'", "files under /default-domain"

**State:** "draft documents", "published files", "active documents not in trash"

**Combined:** "invoices created by john from last week sorted by title limit 10"

Parsing is best-effort. Always check `interpretedQuery` to see what actually
ran, and use `mode="nxql"` when you need exact control.

### Get a Document

```python
from fastmcp import use_tool

# Get document metadata
result = use_tool("nuxeo", "nuxeo_get_document", {
    "path": "/default-domain/workspaces/My Workspace/My Document"
})
print(result)

# Get document blob
blob = use_tool("nuxeo", "nuxeo_get_document", {
    "path": "/default-domain/workspaces/My Workspace/My Document",
    "blob": True
})

# Get document thumbnail
thumbnail = use_tool("nuxeo", "nuxeo_get_document", {
    "path": "/default-domain/workspaces/My Workspace/My Document",
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

result = use_tool("nuxeo", "nuxeo_delete_document", {
    "path": "/default-domain/workspaces/My Workspace/My Document"
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
        "path": "/default-domain/workspaces/My Workspace/My Document"
    })
    print(result)
except Exception as e:
    print(f"Error: {e}")
```

### Performance Considerations

- Use `page_size` and `page_index` when searching; `page_size` is capped at 100 and `hasMore` tells you whether to page again
- Use the `schemas` parameter when getting documents to limit the properties returned
- Use the `enrichers` parameter when getting documents to include additional information
