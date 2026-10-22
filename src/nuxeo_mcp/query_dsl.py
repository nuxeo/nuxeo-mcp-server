"""Guardrails and field guidance for the raw Query DSL search tool.

Nuxeo's ``/site/es`` passthrough enforces ACLs server-side, so the risk here is
not access but cost and response size: the engine happily answers an unqualified
``match_all`` with ``size: 10000`` with several megabytes, and it executes
Painless scripts. Neither is bounded by the passthrough, so they are bounded
here.

``_mapping`` is not exposed by the passthrough -- only ``_search`` -- so field
names cannot be discovered at runtime and are documented instead. This matters
more than it looks: an unknown field name returns HTTP 200 with zero hits, which
a model reads as "nothing matches" rather than "my query was wrong".
"""

from typing import Any, Dict, List

# A single response must stay small enough to be worth putting in a context
# window. Measured: size=10000 over 3179 documents returns ~5.5 MB.
MAX_RESPONSE_BYTES = 262_144
MAX_SIZE = 100
MAX_FROM = 1_000

# Returned when no body is supplied, so the model can correct itself without a
# round trip.
USAGE = """nuxeo_search_documents_with_query_dsl needs an Elasticsearch/OpenSearch request body.

Full-text search with highlighting:
  {"size": 10, "_source": ["dc:title", "ecm:path"],
   "query": {"match": {"all_field": "quarterly report"}},
   "highlight": {"fields": {"all_field": {"fragment_size": 150, "number_of_fragments": 3}}}}

Count documents per type (no hits, just the aggregation):
  {"size": 0, "aggs": {"types": {"terms": {"field": "ecm:primaryType", "size": 20}}}}

Filter on type and path, newest first:
  {"size": 20, "query": {"bool": {"filter": [
       {"term": {"ecm:primaryType": "File"}},
       {"prefix": {"ecm:path": "/default-domain/workspaces"}}]}},
   "sort": [{"dc:modified": "desc"}]}

Read nuxeo://query-dsl-guide for the available field names."""

# Core index fields, stable across Nuxeo instances. Schema-specific fields exist
# too but depend on the deployed content model.
CORE_FIELDS: Dict[str, str] = {
    "all_field": "catch-all full-text field; queryable but never returned in _source",
    "ecm:uuid": "keyword - document UUID",
    "ecm:name": "keyword - document name",
    "ecm:title": "text - document title",
    "ecm:path": "keyword - full repository path",
    "ecm:path@depth": "integer - path depth",
    "ecm:path@level1..level5": "keyword - path segment at each level",
    "ecm:primaryType": "keyword - document type, e.g. File, Note, Folder",
    "ecm:mixinType": "keyword[] - facets",
    "ecm:currentLifeCycleState": "keyword - lifecycle state, e.g. project, deleted",
    "ecm:parentId": "keyword - parent UUID",
    "ecm:ancestorId": "keyword[] - every ancestor UUID; use to search a subtree",
    "ecm:isVersion": "boolean",
    "ecm:isLatestVersion": "boolean",
    "ecm:isProxy": "boolean",
    "ecm:isTrashed": "boolean - filter on false to exclude the trash",
    "ecm:isRecord": "boolean",
    "ecm:hasLegalHold": "boolean",
    "ecm:isCheckedIn": "boolean",
    "ecm:binarytext": "text - extracted text of the attached binary",
    "ecm:acl": "keyword[] - principals allowed to read; applied by Nuxeo, do not filter on it",
    "ecm:changeToken": "keyword",
    "ecm:repository": "keyword - repository name",
    "dc:title": "text - title",
    "dc:description": "text - description",
    "dc:creator": "keyword - username of the creator",
    "dc:created": "date",
    "dc:modified": "date",
    "dc:contributors": "keyword[]",
    "dc:lastContributor": "keyword",
    "file:content": "object - attached blob: name, mime-type, length, digest",
    "uid:major_version": "integer",
    "uid:minor_version": "integer",
    "common:icon": "keyword",
    "thumb:thumbnail": "object",
}

# Default _source projection: enough to identify and cite a document without
# dragging every schema of every hit into the context window.
DEFAULT_SOURCE_FIELDS: List[str] = [
    "ecm:uuid",
    "ecm:path",
    "ecm:primaryType",
    "ecm:currentLifeCycleState",
    "dc:title",
    "dc:description",
    "dc:creator",
    "dc:created",
    "dc:modified",
]

# Painless executes through the passthrough. It is sandboxed but remains a CPU
# vector reachable from a model-authored query, and nothing in the supported use
# cases needs it.
_SCRIPT_KEYS = ("script", "script_fields", "script_score", "runtime_mappings")


class QueryDslRejected(ValueError):
    """Raised when a request body is refused before it reaches the engine."""


def _reject_scripts(node: Any, path: str = "") -> None:
    """Walk the body and refuse any scripted construct, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _SCRIPT_KEYS:
                where = f"{path}.{key}" if path else key
                raise QueryDslRejected(
                    f"Scripted queries are not allowed ({where}). Express the query "
                    "with standard Query DSL clauses instead."
                )
            _reject_scripts(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_scripts(value, f"{path}[{index}]")


def apply_guardrails(query: Dict[str, Any]) -> Dict[str, Any]:
    """Return a bounded copy of ``query``.

    The caller keeps control of size, ``_source`` and highlighting; these are
    bounds, not a fixed policy. Only the defaults change, and only when the
    caller expressed no preference.
    """
    _reject_scripts(query)

    guarded = dict(query)

    # size: 0 is meaningful -- it means "aggregations only" -- so it is preserved.
    size = guarded.get("size")
    if size is None:
        guarded["size"] = 10
    else:
        try:
            guarded["size"] = max(0, min(int(size), MAX_SIZE))
        except (TypeError, ValueError):
            raise QueryDslRejected(f"'size' must be an integer, got {size!r}.")

    offset = guarded.get("from")
    if offset is not None:
        try:
            offset = int(offset)
        except (TypeError, ValueError):
            raise QueryDslRejected(f"'from' must be an integer, got {offset!r}.")
        if offset > MAX_FROM:
            raise QueryDslRejected(
                f"'from' is {offset}, over the {MAX_FROM} limit. Narrow the query "
                "rather than paging deeply."
            )
        guarded["from"] = max(0, offset)

    if "_source" not in guarded and guarded.get("size", 0) > 0:
        guarded["_source"] = list(DEFAULT_SOURCE_FIELDS)

    return guarded


def field_guide() -> str:
    """Render the field reference served by the nuxeo://query-dsl-guide resource."""
    lines = [
        "# Nuxeo search index - Query DSL field reference",
        "",
        "Fields available to nuxeo_search_documents_with_query_dsl.",
        "",
        "An unknown field name does not raise an error: it matches nothing and the",
        "search returns zero hits. Check names here before concluding that no",
        "document matches.",
        "",
        "## Core fields",
        "",
    ]
    lines += [f"- `{name}` - {desc}" for name, desc in CORE_FIELDS.items()]
    lines += [
        "",
        "## Schema fields",
        "",
        "Document-schema properties are indexed under their prefixed name, for",
        "example `invoice:amount` or `rnode:taskDueDateExpr`. Which ones exist",
        "depends on the content model deployed on this instance; use",
        "nuxeo_list_document_types and nuxeo_get_metadata_schema to discover them.",
        "",
        "## Limits",
        "",
        f"- `size` defaults to 10 and is capped at {MAX_SIZE}",
        f"- `from` is capped at {MAX_FROM}",
        f"- responses are capped at {MAX_RESPONSE_BYTES} bytes",
        "- `_source` defaults to a small projection; pass your own list to override",
        "- scripted queries (`script`, `script_fields`, `script_score`) are rejected",
        "",
        "Results are already filtered to what the authenticated user may read.",
        "Do not filter on `ecm:acl` yourself.",
        "",
        "## Examples",
        "",
        "```json",
        USAGE.split("Full-text search with highlighting:\n")[1].split(
            "\nRead nuxeo://"
        )[0],
        "```",
    ]
    return "\n".join(lines)
