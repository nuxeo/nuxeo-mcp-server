"""Guardrails and field guidance for the raw Query DSL search tool.

Nuxeo's ``/site/es`` passthrough enforces ACLs server-side, so the risk here is
not access but cost and response size: the engine happily answers an unqualified
``match_all`` with ``size: 10000`` with several megabytes, and it executes
Painless scripts. Neither is bounded by the passthrough, so they are bounded
here.

These bounds are client-side and therefore advisory: they constrain what this
tool sends, not what the passthrough accepts. NXP-34107 tracks the server-side
counterpart -- an explicit DSL policy, recursive script rejection and
server-controlled resource limits in ``nuxeo-rest-opensearch1-passthrough``.
Until it ships this module is the only thing between a model-authored query and
the engine; once it does, these checks remain as a fast local failure carrying a
usable error message.

``_mapping`` is not exposed by the passthrough -- only ``_search`` -- so field
names cannot be discovered at runtime and are documented instead. This matters
more than it looks: an unknown field name returns HTTP 200 with zero hits, which
a model reads as "nothing matches" rather than "my query was wrong".
"""

import copy
from typing import Any, Callable, Dict, List, Optional

# A single response must stay small enough to be worth putting in a context
# window. Measured: size=10000 over 3179 documents returns ~5.5 MB.
MAX_RESPONSE_BYTES = 262_144
MAX_SIZE = 100
MAX_FROM = 1_000

# top_hits and inner_hits fetch whole documents per bucket or per hit, under a
# size of their own that the top-level cap does not reach. Each is capped and
# projected here. Their cumulative cost (buckets x hits) is not accounted for:
# that is a server-side resource limit, tracked by NXP-34107.
MAX_TOP_HITS_SIZE = 10

# Returned when no body is supplied, so the model can correct itself without a
# round trip.
USAGE = """nuxeo_search_documents_with_query_dsl needs an OpenSearch/Elasticsearch request body.

Full-text search with highlighting, live user documents only:
  {"size": 10, "_source": ["dc:title", "ecm:path"],
   "query": {"bool": {
       "must": {"match": {"all_field": "quarterly report"}},
       "filter": [{"term": {"ecm:isProxy": false}},
                  {"term": {"ecm:isVersion": false}},
                  {"term": {"ecm:isTrashed": false}}],
       "must_not": [{"term": {"ecm:mixinType": "HiddenInNavigation"}}]}},
   "highlight": {"require_field_match": false,
                 "fields": {"dc:title.fulltext": {},
                            "dc:description.fulltext": {},
                            "ecm:binarytext": {"fragment_size": 150,
                                               "number_of_fragments": 3}}}}

Count documents per type (no hits, just the aggregation):
  {"size": 0, "query": {"bool": {
       "filter": [{"term": {"ecm:isProxy": false}},
                  {"term": {"ecm:isVersion": false}},
                  {"term": {"ecm:isTrashed": false}}],
       "must_not": [{"term": {"ecm:mixinType": "HiddenInNavigation"}}]}},
   "aggs": {"types": {"terms": {"field": "ecm:primaryType", "size": 20}}}}

Files under a path, newest first:
  {"size": 20, "query": {"bool": {
       "filter": [{"term": {"ecm:primaryType": "File"}},
                  {"term": {"ecm:path.children": "/default-domain/workspaces"}},
                  {"term": {"ecm:isProxy": false}},
                  {"term": {"ecm:isVersion": false}},
                  {"term": {"ecm:isTrashed": false}}],
       "must_not": [{"term": {"ecm:mixinType": "HiddenInNavigation"}}]}},
   "sort": [{"dc:modified": "desc"}]}

Read nuxeo://query-dsl-guide for the available field names."""

AUDIT_USAGE = """nuxeo_search_audit_with_query_dsl needs an OpenSearch/Elasticsearch request body.

What happened to one document, newest first:
  {"size": 20, "query": {"term": {"docUUID": "<uuid>"}},
   "sort": [{"eventDate": "desc"}]}

Documents trashed or deleted over the last day:
  {"size": 50, "query": {"bool": {"filter": [
       {"terms": {"eventId": ["documentTrashed", "documentRemoved"]}},
       {"range": {"eventDate": {"gte": "now-1d"}}}]}},
   "sort": [{"eventDate": "desc"}]}

Who downloaded files under a folder this week:
  {"size": 50, "_source": ["eventDate", "principalName", "docPath",
                           "extended.blobFilename"],
   "query": {"bool": {"filter": [
       {"term": {"eventId": "download"}},
       {"term": {"docPath.children": "/default-domain/workspaces"}},
       {"range": {"eventDate": {"gte": "now-7d"}}}]}},
   "sort": [{"eventDate": "desc"}]}

Failed logins per user (no hits, just the aggregation):
  {"size": 0, "query": {"term": {"eventId": "loginFailed"}},
   "aggs": {"users": {"terms": {"field": "principalName", "size": 20}}}}

Most active users:
  {"size": 0, "aggs": {"users": {"terms": {"field": "principalName", "size": 20}}}}

Read nuxeo://audit-query-dsl-guide for the available field names."""

# Audit index fields. Audit entries are events, not documents, so they share no
# schema with the repository index.
AUDIT_FIELDS: Dict[str, str] = {
    "id": "long - audit entry id",
    "eventId": "keyword - event name: documentCreated, documentModified, "
    "documentTrashed, documentUntrashed, documentRemoved (permanent deletion), "
    "documentMoved, documentCheckedIn, documentLocked, documentSecurityUpdated, "
    "download, search, loginSuccess, loginFailed, logout, user_created, "
    "user_deleted, group_created",
    "category": "keyword - eventDocumentCategory (document events), "
    "NuxeoAuthentication (logins), userGroup (users and groups)",
    "eventDate": "date - when the event happened; the usual sort field",
    "logDate": "date - when the entry was written",
    "principalName": "keyword - user who caused the event",
    "docUUID": "keyword - id of the document concerned",
    "docPath": "keyword - path at the time of the event; term on "
    "docPath.children for everything under a path",
    "docType": "keyword - document type",
    "docLifeCycle": "keyword - lifecycle state at the time of the event",
    "repositoryId": "keyword - repository name",
    "comment": "text - comment, e.g. the version label on documentCheckedIn; "
    "match comment.fulltext",
    "entity-type": "keyword - always logEntry",
    "extended": "object - event-specific details, e.g. extended.blobFilename "
    "and extended.downloadReason on download, extended.effectiveQuery and "
    "extended.resultsCount on search",
}


# Core index fields, stable across Nuxeo instances, with their type in the
# default LTS 2025 mapping. Schema-specific fields exist too but depend on the
# deployed content model.
CORE_FIELDS: Dict[str, str] = {
    "all_field": "text - catch-all full-text field (every string property and "
    "the extracted text); query it with match; never in _source, so it cannot "
    "be highlighted",
    "ecm:uuid": "keyword - document id",
    "ecm:name": "keyword - name in its parent",
    "ecm:title": "keyword - title, exact value; use dc:title.fulltext to find words",
    "ecm:path": "keyword - full path; prefix or term on it, or term on "
    "ecm:path.children for everything under a path",
    "ecm:path@depth": "integer - path depth",
    "ecm:path@level*": "keyword - path segment at each level, level1 to level5",
    "ecm:parentId": "keyword - parent id",
    "ecm:ancestorId": "keyword[] - every ancestor id; term on it for a subtree",
    "ecm:primaryType": "keyword - document type, e.g. File, Note, Folder",
    "ecm:mixinType": "keyword[] - facets, e.g. Folderish, HiddenInNavigation",
    "ecm:currentLifeCycleState": "keyword - lifecycle state, e.g. project",
    "ecm:isVersion": "boolean - see the default filter",
    "ecm:isProxy": "boolean - see the default filter",
    "ecm:isTrashed": "boolean - see the default filter",
    "ecm:isLatestVersion": "boolean",
    "ecm:isLatestMajorVersion": "boolean",
    "ecm:isCheckedIn": "boolean",
    "ecm:isRecord": "boolean",
    "ecm:hasLegalHold": "boolean",
    "ecm:versionLabel": "keyword - e.g. 1.0, versions only",
    "ecm:versionVersionableId": "keyword - live document id, versions only",
    "ecm:binarytext": "text - text extracted from attached files; match and "
    "highlight it directly",
    "ecm:acl": "keyword[] - applied by Nuxeo; do not filter on it",
    "ecm:pos": "integer - position in an ordered folder",
    "ecm:repository": "keyword - repository name",
    "ecm:changeToken": "keyword",
    "dc:title": "text - match it, or dc:title.fulltext for the full-text "
    "analyzer; sortable",
    "dc:description": "keyword - exact value; match or highlight "
    "dc:description.fulltext",
    "dc:creator": "keyword - username",
    "dc:lastContributor": "keyword - username",
    "dc:contributors": "keyword[] - usernames",
    "dc:created": "date",
    "dc:modified": "date",
    "file:content.name": "keyword - main attached file name",
    "file:content.mime-type": "keyword - e.g. application/pdf",
    "file:content.length": "long - size in bytes",
    "file:content.digest": "keyword",
    "uid:major_version": "long",
    "uid:minor_version": "long",
    "common:icon": "keyword",
    "thumb:thumbnail": "object - not indexed; cannot be queried",
}

# How the default mapping indexes properties. Without this a model writes match
# on keyword fields, or highlights a field with no analysed text, and gets
# silence rather than an error.
MAPPING_NOTES: List[str] = [
    "Schema properties are indexed under their prefixed name (`dc:title`).",
    "Complex sub-properties use a dot: `file:content.mime-type` (NXQL uses `/`).",
    "A string property without an explicit mapping is a `keyword`, copied to",
    "`all_field`, and values over 256 characters are not indexed. Query it",
    "with `term`/`terms`/`prefix` on the exact value; to find words in it,",
    "`match` on `all_field`.",
    "Properties mapped for full-text, like `dc:description` or `note:note`,",
    "have an analysed `<field>.fulltext` subfield: `match` and highlight that",
    "subfield, and use the field itself for `term`, sorting and aggregations.",
    "Only `keyword`, numeric, date and boolean fields can be sorted or",
    "aggregated (`dc:title` too: it has fielddata).",
]

# Excludes system documents, versions, proxies and the trash: each is a separate
# index entry, so without it one document is returned several times. Mirrors the
# NXQL guide's default filter.
DEFAULT_FILTER: Dict[str, Any] = {
    "bool": {
        "filter": [
            {"term": {"ecm:isProxy": False}},
            {"term": {"ecm:isVersion": False}},
            {"term": {"ecm:isTrashed": False}},
        ],
        "must_not": [{"term": {"ecm:mixinType": "HiddenInNavigation"}}],
    }
}
DEFAULT_FILTER_LINES: List[str] = [
    '  {"bool": {',
    '     "filter": [{"term": {"ecm:isProxy": false}},',
    '                {"term": {"ecm:isVersion": false}},',
    '                {"term": {"ecm:isTrashed": false}}],',
    '     "must_not": [{"term": {"ecm:mixinType": "HiddenInNavigation"}}]}}',
]

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
#
# Matched by suffix as well as by name: Painless reaches the engine through a
# long tail of carriers -- scripted_metric alone has four
# (init/map/combine/reduce_script), and bucket_script, bucket_selector and
# script_heuristic add more. Enumerating them invites the next omission, so any
# key named "script" or ending in "_script" is refused.
#
# The match is on key names alone, so it also refuses a field named "script" or
# "*_script". Telling a field from a carrier would mean parsing the clause
# grammar; failing closed is the accepted trade-off, and the guide says so.
_SCRIPT_KEYS = ("script", "script_fields", "script_score", "runtime_mappings")
_SCRIPT_KEY_SUFFIX = "_script"


class QueryDslRejected(ValueError):
    """Raised when a request body is refused before it reaches the engine."""


def _reject_scripts(node: Any, path: str = "") -> None:
    """Walk the body and refuse any scripted construct, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _SCRIPT_KEYS or key.endswith(_SCRIPT_KEY_SUFFIX):
                where = f"{path}.{key}" if path else key
                raise QueryDslRejected(
                    f"Scripted queries are not allowed ({where}). Express the query "
                    "with standard Query DSL clauses instead."
                )
            _reject_scripts(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_scripts(value, f"{path}[{index}]")


def _cap_hit_size(spec: Dict[str, Any], where: str) -> int:
    """Clamp ``spec['size']`` to MAX_TOP_HITS_SIZE in place and return it."""
    size = spec.get("size", 3)
    try:
        size = int(size)
    except (TypeError, ValueError):
        raise QueryDslRejected(f"'size' in {where} must be an integer, got {size!r}.")
    size = max(0, min(size, MAX_TOP_HITS_SIZE))
    spec["size"] = size
    return size


def _cap_spec(
    spec: Any, where: str, default_source: Optional[List[str]], project: bool
) -> None:
    """Clamp one ``top_hits`` or ``inner_hits`` body and add the default projection."""
    if not isinstance(spec, dict):
        return
    size = _cap_hit_size(spec, where)
    if project and default_source and size > 0 and "_source" not in spec:
        spec["_source"] = list(default_source)


def _cap_aggregations(
    aggs: Any, default_source: Optional[List[str]], path: str
) -> None:
    """Cap ``top_hits`` in an aggregation map, recursing into sub-aggregations.

    Walked by structure, not by key name: under ``aggs`` the keys are names the
    caller chose, so an aggregation called ``top_hits`` is a container, and only
    the ``top_hits`` type inside it is a collector.
    """
    if not isinstance(aggs, dict):
        return
    for name, body in aggs.items():
        if not isinstance(body, dict):
            continue
        where = f"{path}.{name}"
        if "top_hits" in body:
            _cap_spec(body["top_hits"], f"{where}.top_hits", default_source, True)
        for sub in ("aggs", "aggregations"):
            if sub in body:
                _cap_aggregations(body[sub], default_source, f"{where}.{sub}")


def _cap_inner_hits(
    node: Any, default_source: Optional[List[str]], path: str, parent: str = ""
) -> None:
    """Cap every ``inner_hits`` in the query and ``collapse`` clauses, at any depth.

    inner_hits appears under nested, has_child and has_parent queries, and under
    collapse, where it may be a list. Nested inner hits return the nested object,
    not the document, so a document projection would empty them.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            where = f"{path}.{key}" if path else key
            if key == "inner_hits":
                for spec in value if isinstance(value, list) else [value]:
                    _cap_spec(spec, where, default_source, parent != "nested")
            _cap_inner_hits(value, default_source, where, key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _cap_inner_hits(value, default_source, f"{path}[{index}]", parent)


def apply_guardrails(
    query: Dict[str, Any], default_source: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Return a bounded copy of ``query``.

    The caller keeps control of size, ``_source`` and highlighting; these are
    bounds, not a fixed policy. Only the defaults change, and only when the
    caller expressed no preference.

    Args:
        query: The request body.
        default_source: ``_source`` projection to apply when the caller supplied
            none. Index-specific -- the repository and audit indices share no
            field names, so a projection for one returns nothing but nulls on
            the other. ``None`` leaves ``_source`` untouched.
    """
    _reject_scripts(query)

    guarded = copy.deepcopy(query)

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

    if default_source and "_source" not in guarded and guarded.get("size", 0) > 0:
        guarded["_source"] = list(default_source)

    for key in ("aggs", "aggregations"):
        if key in guarded:
            _cap_aggregations(guarded[key], default_source, key)
    for key in ("query", "post_filter", "collapse"):
        if key in guarded:
            _cap_inner_hits(guarded[key], default_source, key)

    return guarded


# Documents sampled to discover instance-specific field names: a few per document
# type, because the first N hits of a match_all are whatever was indexed first --
# on a fresh instance, workflow and admin documents rather than content.
SAMPLE_TYPES = 20
SAMPLE_PER_TYPE = 3
SAMPLE_SIZE = SAMPLE_TYPES * SAMPLE_PER_TYPE

# Excluded from the sample: discovery needs key names, and this one carries the
# entire extracted text of every binary. Already documented in the curated table.
SAMPLE_SOURCE_EXCLUDES: List[str] = ["ecm:binarytext"]

_SAMPLE_CACHE: Dict[str, List[str]] = {}


def sample_field_names(
    execute_query: Callable[..., Dict[str, Any]], index: str
) -> List[str]:
    """Return the field names actually present in ``index``, sorted.

    The curated tables above are a floor, not the truth: every deployment adds
    its own schemas, and ``_mapping`` is not reachable through the passthrough.
    Sampling ``_source`` keys from real documents is the only discovery channel
    left, and it is the difference between a guide that mentions
    ``invoice:amount`` and one that tells the model to go look it up.

    Cached per index for the life of the process -- content models do not change
    between two reads of a guide.

    This bypasses ``apply_guardrails`` deliberately: the body is ours, not the
    caller's, and the guardrails would project ``_source`` down to the very
    fields we are trying to discover beyond. ``ecm:binarytext`` is excluded all
    the same -- it holds the full extracted text of every binary, so sampling it
    costs tens of megabytes for a name already in the curated table.
    """
    if index in _SAMPLE_CACHE:
        return _SAMPLE_CACHE[index]

    # Plain hits as well as per-type buckets: the audit index has no
    # ecm:primaryType, so the aggregation comes back empty there.
    source = {"excludes": SAMPLE_SOURCE_EXCLUDES}
    response = execute_query(
        index=index,
        query={
            "size": SAMPLE_PER_TYPE * 3,
            "_source": source,
            # Sample what a user searches, not workflow and admin documents.
            "query": DEFAULT_FILTER if index == "nuxeo" else {"match_all": {}},
            "aggs": {
                "types": {
                    "terms": {"field": "ecm:primaryType", "size": SAMPLE_TYPES},
                    "aggs": {
                        "docs": {
                            "top_hits": {"size": SAMPLE_PER_TYPE, "_source": source}
                        }
                    },
                }
            },
        },
    )

    hits = list(response.get("hits", {}).get("hits", []))
    buckets = response.get("aggregations", {}).get("types", {}).get("buckets", [])
    for bucket in buckets:
        hits += bucket.get("docs", {}).get("hits", {}).get("hits", [])

    names: set = set()
    for hit in hits:
        names.update((hit.get("_source") or {}).keys())

    discovered = sorted(names)
    _SAMPLE_CACHE[index] = discovered
    return discovered


def reset_sample_cache() -> None:
    """Drop the cached samples. For tests, and for a server that switched target."""
    _SAMPLE_CACHE.clear()


def _discovered_section(
    discovered: Optional[List[str]], known: Dict[str, str], what: str = "documents"
) -> List[str]:
    """Render the fields found on this instance that the curated table misses."""
    if discovered is None:
        return [
            "## Schema fields",
            "",
            "Document-schema properties are indexed under their prefixed name, for",
            "example `invoice:amount`. Which ones exist depends on the content model",
            "deployed on this instance; use nuxeo_list_document_types and",
            "nuxeo_get_metadata_schema to discover them.",
            "",
        ]

    # A curated key ending in * stands for a family of fields, like
    # ecm:path@level* for level1..level5. Listing the members again is noise.
    families = tuple(name[:-1] for name in known if name.endswith("*"))
    # file:content is curated through its sub-fields, file:content.name etc.
    parents = {name.split(".")[0] for name in known if "." in name}
    extra = [
        name
        for name in discovered
        if name not in known and name not in parents and not name.startswith(families)
    ]
    if not extra:
        return []

    return [
        "## Schema fields on this instance",
        "",
        f"Observed by sampling {what} on this instance, so this lists what is",
        "in use rather than everything that could exist. Types are not shown; a",
        "string property is a keyword unless the guide above says otherwise.",
        "",
        *(f"- `{name}`" for name in extra),
        "",
    ]


def field_guide(discovered: Optional[List[str]] = None) -> str:
    """Render the field reference served by the nuxeo://query-dsl-guide resource."""
    return _render_guide(
        title="Nuxeo search index - Query DSL field reference",
        tool="nuxeo_search_documents_with_query_dsl",
        fields=CORE_FIELDS,
        schema_note=_discovered_section(discovered, CORE_FIELDS),
        examples=USAGE,
        preamble=[
            "## Start every query from the default filter",
            "",
            "System documents, versions, proxies and trashed documents are indexed",
            "too, so without this filter they come back, and the same document",
            "appears several times. Add your clauses to it; drop one only on purpose:",
            "",
            *DEFAULT_FILTER_LINES,
            "",
            "## How fields are indexed",
            "",
            *MAPPING_NOTES,
            "",
        ],
        acl_note=(
            "Results are already filtered to what the authenticated user may read.\n"
            "Do not filter on `ecm:acl` yourself."
        ),
    )


def audit_field_guide(discovered: Optional[List[str]] = None) -> str:
    """Render the field reference served by nuxeo://audit-query-dsl-guide."""
    return _render_guide(
        title="Nuxeo audit index - Query DSL field reference",
        tool="nuxeo_search_audit_with_query_dsl",
        fields=AUDIT_FIELDS,
        schema_note=(
            _discovered_section(discovered, AUDIT_FIELDS, what="entries")
            if discovered
            else []
        ),
        examples=AUDIT_USAGE,
        # The audit tool applies no _source default: entries are small.
        projects_source=False,
        acl_note=(
            "The audit index is restricted to administrators; Nuxeo answers HTTP 403\n"
            "for everyone else."
        ),
    )


# Advice, not enforcement: the search cluster is shared with the application,
# and the caps above only bound the worst case. Server-side limits are NXP-34107.
EFFICIENCY_TIPS: List[str] = [
    "Counting or grouping? Use `size: 0` with an aggregation; no hits are fetched.",
    "Put exact conditions (term, range, prefix) in `bool.filter`, not "
    "`bool.must`: filters skip scoring and are cached.",
    "Pass a short `_source` list; never fetch whole documents to read one field.",
    "Keep aggregations shallow and bucket `size` small; nesting multiplies cost.",
    "Keep `top_hits` to a few documents per bucket, with a `_source` list.",
    "Avoid leading wildcards (`*report`) and `regexp`; they scan every term. "
    "Prefer `match` on text fields and `prefix` on keyword fields.",
    "Narrow with filters on keyword and date fields (type, path, user, date "
    "range) before full-text matching.",
    "Do not page deeply with `from`; refine the query instead.",
]


def _render_guide(
    *,
    title: str,
    tool: str,
    fields: Dict[str, str],
    schema_note: List[str],
    examples: str,
    acl_note: str,
    preamble: Optional[List[str]] = None,
    projects_source: bool = True,
) -> str:
    preamble = preamble or []
    lines = [
        f"# {title}",
        "",
        f"Fields available to {tool}.",
        "",
        "An unknown field name does not raise an error: it matches nothing and the",
        "search returns zero hits. Check names here before concluding that no",
        "entry matches.",
        "",
        *preamble,
        "## Fields",
        "",
    ]
    lines += [f"- `{name}` - {desc}" for name, desc in fields.items()]
    lines += ["", *schema_note]
    lines += [
        "## Limits",
        "",
        f"- `size` defaults to 10 and is capped at {MAX_SIZE}",
        f"- `from` is capped at {MAX_FROM}",
        f"- `top_hits` and `inner_hits` are capped at {MAX_TOP_HITS_SIZE} each",
        f"- responses are capped at {MAX_RESPONSE_BYTES} bytes",
        *(
            [
                "- `_source` defaults to a small projection; pass your own list "
                "to override"
            ]
            if projects_source
            else []
        ),
        "- scripted queries are rejected: any key named `script` or ending in "
        "`_script`, at any depth -- including a field name such as "
        "`foo_script`, which therefore cannot be queried",
        "",
        "## Writing efficient queries",
        "",
        *[f"- {tip}" for tip in EFFICIENCY_TIPS],
        "",
        acl_note,
        "",
        "## Examples",
        "",
        examples.split("needs an OpenSearch/Elasticsearch request body.\n\n")[1]
        .split("\nRead nuxeo://")[0]
        .strip(),
    ]
    return "\n".join(lines)
