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

# top_hits retrieves whole documents from inside every bucket, so its cost is
# the product of the enclosing bucket counts, not its own size: 100 terms
# buckets each holding a top_hits of size 100 is 10,000 documents from a
# request that declares size: 0. The response-size check cannot help -- it runs
# after the engine has already done the work -- so the product is bounded here,
# before the request is forwarded.
MAX_TOP_HITS_SIZE = 10
MAX_COLLECTED_HITS = 500

# Assumed bucket count for a bucket aggregation that declares no size. Matches
# the engine's own default for terms.
DEFAULT_BUCKET_COUNT = 10

# Aggregations that always produce exactly one bucket. Counting them as
# DEFAULT_BUCKET_COUNT would compound per level and reject cheap requests.
_SINGLE_BUCKET_AGGS = frozenset(
    {
        "filter",
        "global",
        "missing",
        "nested",
        "reverse_nested",
        "sampler",
        "diversified_sampler",
        "children",
        "parent",
    }
)

# Aggregations whose bucket count follows from an explicit list of ranges.
_RANGE_AGGS = frozenset({"range", "date_range", "ip_range", "geo_distance"})

# Aggregations whose bucket count depends on the data span, not on the request.
# No bound can be read from the body, so a top_hits beneath them is counted as
# exhausting the whole budget.
_UNBOUNDED_AGGS = frozenset({"histogram", "date_histogram", "rare_terms"})

# Grid aggregations default to 10,000 buckets, not 10.
_GRID_AGGS = frozenset({"geohash_grid", "geotile_grid", "geohex_grid"})
_GRID_DEFAULT_SIZE = 10_000

# Hits whose documents are fetched in full, per outer hit, like top_hits.
_INNER_HITS_DEFAULT_SIZE = 3

# Returned when no body is supplied, so the model can correct itself without a
# round trip.
USAGE = """nuxeo_search_documents_with_query_dsl needs an OpenSearch/Elasticsearch request body.

Full-text search with highlighting:
  {"size": 10, "_source": ["dc:title", "ecm:path"],
   "query": {"match": {"all_field": "quarterly report"}},
   "highlight": {"require_field_match": false,
                 "fields": {"dc:title": {}, "dc:description": {},
                            "ecm:binarytext": {"fragment_size": 150,
                                               "number_of_fragments": 3}}}}

Count documents per type (no hits, just the aggregation):
  {"size": 0, "aggs": {"types": {"terms": {"field": "ecm:primaryType", "size": 20}}}}

Filter on type and path, newest first:
  {"size": 20, "query": {"bool": {"filter": [
       {"term": {"ecm:primaryType": "File"}},
       {"prefix": {"ecm:path": "/default-domain/workspaces"}}]}},
   "sort": [{"dc:modified": "desc"}]}

Read nuxeo://query-dsl-guide for the available field names."""

AUDIT_USAGE = """nuxeo_search_audit_with_query_dsl needs an OpenSearch/Elasticsearch request body.

What happened to one document, newest first:
  {"size": 20, "query": {"term": {"docUUID": "<uuid>"}},
   "sort": [{"eventDate": "desc"}]}

Deletions over the last day:
  {"size": 50, "query": {"bool": {"filter": [
       {"term": {"eventId": "documentRemoved"}},
       {"range": {"eventDate": {"gte": "now-1d"}}}]}},
   "sort": [{"eventDate": "desc"}]}

Who is most active (no hits, just the aggregation):
  {"size": 0, "aggs": {"users": {"terms": {"field": "principalName", "size": 20}}}}

Read nuxeo://audit-query-dsl-guide for the available field names."""

# Audit index fields. Audit entries are events, not documents, so they share no
# schema with the repository index.
AUDIT_FIELDS: Dict[str, str] = {
    "id": "keyword - audit entry id",
    "eventId": "keyword - event name, e.g. documentCreated, documentModified, documentRemoved, loginSuccess",
    "eventDate": "date - when the event happened; the usual sort field",
    "logDate": "date - when the entry was written",
    "category": "keyword - event category, e.g. eventDocumentCategory, eventLifeCycleCategory",
    "principalName": "keyword - user who caused the event",
    "docUUID": "keyword - UUID of the document concerned",
    "docPath": "keyword - path of the document at the time of the event",
    "docType": "keyword - document type",
    "docLifeCycle": "keyword - lifecycle state at the time of the event",
    "repositoryId": "keyword - repository name",
    "comment": "text - free-text comment attached to the event",
    "extended": "object - event-specific extra properties",
}


# Core index fields, stable across Nuxeo instances. Schema-specific fields exist
# too but depend on the deployed content model.
CORE_FIELDS: Dict[str, str] = {
    "all_field": "catch-all full-text field; queryable but never returned in "
    "_source, so highlight source-backed fields (dc:title, dc:description, "
    "ecm:binarytext) with require_field_match: false instead",
    "ecm:uuid": "keyword - document UUID",
    "ecm:name": "keyword - document name",
    "ecm:title": "text - document title",
    "ecm:path": "keyword - full repository path",
    "ecm:path@depth": "integer - path depth",
    "ecm:path@level*": "keyword - path segment at each level, level1 to level5",
    "ecm:primaryType": "keyword - document type, e.g. File, Note, Folder",
    "ecm:mixinType": "keyword[] - facets",
    "ecm:currentLifeCycleState": "keyword - lifecycle state, e.g. project, deleted",
    "ecm:parentId": "keyword - parent UUID",
    "ecm:ancestorId": "keyword[] - every ancestor UUID; use to search a subtree",
    "ecm:isVersion": "boolean",
    "ecm:isLatestVersion": "boolean",
    "ecm:isLatestMajorVersion": "boolean",
    "ecm:isProxy": "boolean",
    "ecm:isTrashed": "boolean - filter on false to exclude the trash",
    "ecm:isRecord": "boolean",
    "ecm:hasLegalHold": "boolean",
    "ecm:isCheckedIn": "boolean",
    "ecm:binarytext": "text - extracted text of the attached binary",
    "ecm:acl": "keyword[] - principals allowed to read; applied by Nuxeo, do not filter on it",
    "ecm:changeToken": "keyword",
    "ecm:pos": "integer - position among its siblings, for ordered folders",
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


def _aggs_of(node: Dict[str, Any]) -> Dict[str, Any]:
    """Return the sub-aggregation map of an aggregation or request body."""
    sub = node.get("aggs") or node.get("aggregations") or {}
    return sub if isinstance(sub, dict) else {}


def _bucket_count(body: Dict[str, Any]) -> int:
    """Bound how many buckets an aggregation produces.

    Deliberately a bound, not accounting: exact where the request declares the
    count, an upper bound where it does not.
    """
    for agg_type, agg_body in body.items():
        if agg_type in ("aggs", "aggregations", "meta") or not isinstance(
            agg_body, dict
        ):
            continue
        if agg_type in _SINGLE_BUCKET_AGGS:
            return 1
        if agg_type in _UNBOUNDED_AGGS:
            return MAX_COLLECTED_HITS + 1
        if agg_type in _RANGE_AGGS:
            ranges = agg_body.get("ranges")
            return max(len(ranges), 1) if isinstance(ranges, list) else 1
        if agg_type in ("filters", "adjacency_matrix"):
            filters = agg_body.get("filters")
            n = len(filters) if isinstance(filters, (dict, list)) else 1
            # adjacency_matrix adds one bucket per intersecting pair.
            n = n + n * (n - 1) // 2 if agg_type == "adjacency_matrix" else n
            return max(n, 1) + (1 if agg_body.get("other_bucket") else 0)
        if agg_type in ("auto_date_histogram", "variable_width_histogram"):
            buckets = agg_body.get("buckets", DEFAULT_BUCKET_COUNT)
            return max(int(buckets), 1) if isinstance(buckets, int) else 1
        default = _GRID_DEFAULT_SIZE if agg_type in _GRID_AGGS else DEFAULT_BUCKET_COUNT
        size = agg_body.get("size", default)
        return max(int(size), 1) if isinstance(size, int) else default
    return DEFAULT_BUCKET_COUNT


def _bound_hit_collectors(
    aggs: Dict[str, Any],
    multiplier: int,
    default_source: Optional[List[str]],
    path: str,
) -> int:
    """Cap every ``top_hits`` in place and return the documents they retrieve."""
    collected = 0
    for name, body in aggs.items():
        if not isinstance(body, dict):
            continue
        where = f"{path}.{name}" if path else name

        top_hits = body.get("top_hits")
        if isinstance(top_hits, dict):
            size = _cap_hit_size(top_hits, f"{where}.top_hits", 3)
            if default_source and "_source" not in top_hits and size > 0:
                top_hits["_source"] = list(default_source)
            collected += multiplier * size

        sub = _aggs_of(body)
        if sub:
            collected += _bound_hit_collectors(
                sub, multiplier * _bucket_count(body), default_source, where
            )
    return collected


def _cap_hit_size(spec: Dict[str, Any], where: str, default: int) -> int:
    """Clamp ``spec['size']`` to MAX_TOP_HITS_SIZE in place and return it."""
    size = spec.get("size", default)
    try:
        size = int(size)
    except (TypeError, ValueError):
        raise QueryDslRejected(f"'size' in {where} must be an integer, got {size!r}.")
    size = max(0, min(size, MAX_TOP_HITS_SIZE))
    spec["size"] = size
    return size


def _bound_inner_hits(
    node: Any, default_source: Optional[List[str]], path: str, parent: str = ""
) -> int:
    """Cap every ``inner_hits`` in place and return the documents fetched per hit.

    inner_hits appears under nested, has_child and has_parent queries, and under
    collapse, where it may be a list. Each outer hit carries its own inner hits,
    so the caller multiplies the result by the top-level size.
    """
    per_hit = 0
    if isinstance(node, dict):
        for key, value in node.items():
            where = f"{path}.{key}" if path else key
            if key == "inner_hits":
                specs = value if isinstance(value, list) else [value]
                for i, spec in enumerate(specs):
                    if not isinstance(spec, dict):
                        continue
                    spec_where = f"{where}[{i}]" if isinstance(value, list) else where
                    size = _cap_hit_size(spec, spec_where, _INNER_HITS_DEFAULT_SIZE)
                    # Nested inner hits return the nested object, not the
                    # document, so a document projection would empty them.
                    if (
                        default_source
                        and parent != "nested"
                        and "_source" not in spec
                        and size > 0
                    ):
                        spec["_source"] = list(default_source)
                    per_hit += size
                    per_hit += _bound_inner_hits(spec, default_source, spec_where)
            else:
                per_hit += _bound_inner_hits(value, default_source, where, key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            per_hit += _bound_inner_hits(
                value, default_source, f"{path}[{index}]", parent
            )
    return per_hit


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

    hits = int(guarded["size"])
    searched = {k: v for k, v in guarded.items() if k not in ("aggs", "aggregations")}
    inner = hits * _bound_inner_hits(searched, default_source, "")
    if hits + inner > MAX_COLLECTED_HITS:
        raise QueryDslRejected(
            f"inner_hits retrieve up to {inner} documents on top of the {hits} "
            f"hits, over the {MAX_COLLECTED_HITS} document budget. Reduce 'size' "
            "or the inner_hits size."
        )

    aggs = _aggs_of(guarded)
    if aggs:
        nested = _bound_hit_collectors(aggs, 1, default_source, "aggs")
        budget = MAX_COLLECTED_HITS - hits - inner
        if nested > budget:
            raise QueryDslRejected(
                f"The aggregations retrieve up to {nested} documents through "
                f"top_hits, over the {budget} remaining in the "
                f"{MAX_COLLECTED_HITS} document budget. Reduce the bucket count "
                "or the top_hits size; histogram and date_histogram have no "
                "declared bucket count, so top_hits beneath them is refused."
            )

    return guarded


# Number of documents sampled to discover instance-specific field names. Large
# enough to cover the common document types, small enough to stay cheap.
SAMPLE_SIZE = 50

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

    response = execute_query(
        index=index,
        query={
            "size": SAMPLE_SIZE,
            "_source": {"excludes": SAMPLE_SOURCE_EXCLUDES},
            "query": {"match_all": {}},
        },
    )

    names: set = set()
    for hit in response.get("hits", {}).get("hits", []):
        names.update((hit.get("_source") or {}).keys())

    discovered = sorted(names)
    _SAMPLE_CACHE[index] = discovered
    return discovered


def reset_sample_cache() -> None:
    """Drop the cached samples. For tests, and for a server that switched target."""
    _SAMPLE_CACHE.clear()


def _discovered_section(
    discovered: Optional[List[str]], known: Dict[str, str]
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
    extra = [
        name
        for name in discovered
        if name not in known and not name.startswith(families)
    ]
    if not extra:
        return []

    return [
        "## Schema fields on this instance",
        "",
        f"Observed by sampling {SAMPLE_SIZE} documents, so this lists what is in use",
        "rather than everything the content model allows. Types are not shown;",
        "use nuxeo_get_metadata_schema for those.",
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
        schema_note=_discovered_section(discovered, AUDIT_FIELDS) if discovered else [],
        examples=AUDIT_USAGE,
        acl_note=(
            "The audit index is restricted to administrators; Nuxeo answers HTTP 403\n"
            "for everyone else."
        ),
    )


def _render_guide(
    *,
    title: str,
    tool: str,
    fields: Dict[str, str],
    schema_note: List[str],
    examples: str,
    acl_note: str,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"Fields available to {tool}.",
        "",
        "An unknown field name does not raise an error: it matches nothing and the",
        "search returns zero hits. Check names here before concluding that no",
        "entry matches.",
        "",
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
        f"- `top_hits` and `inner_hits` are capped at {MAX_TOP_HITS_SIZE} each, "
        f"and a request that would retrieve more than {MAX_COLLECTED_HITS} "
        "documents in total is rejected; `top_hits` beneath `histogram` or "
        "`date_histogram` is refused, as their bucket count is unbounded",
        f"- responses are capped at {MAX_RESPONSE_BYTES} bytes",
        "- `_source` defaults to a small projection; pass your own list to override",
        "- scripted queries are rejected: any key named `script` or ending in "
        "`_script`, at any depth -- including a field name such as "
        "`foo_script`, which therefore cannot be queried",
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
