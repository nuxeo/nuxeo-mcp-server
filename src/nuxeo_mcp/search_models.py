"""Normalized search result models shared by every search mode.

Field names follow the Hyland Product MCP Standard normalized content model
(``id``/``documentType``/``createdAt``/...) so that an agent reading results
from this server sees the same shape it sees from the other Hyland repository
MCP servers. Nuxeo-native values that have no normalized equivalent go under
``extensions.nuxeo``.

The envelope is deliberately identical for every query mode. A mode changes how
the caller expresses the query, never what comes back: fields that a given mode
cannot populate are left null or empty rather than omitted, so an agent can read
a result without first branching on which mode produced it.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# Mode names are part of the tool contract; keep them stable.
MODE_NXQL = "nxql"
MODE_NATURAL = "natural"
MODE_SEMANTIC = "semantic"
SEARCH_MODES = (MODE_NXQL, MODE_NATURAL, MODE_SEMANTIC)


class SearchHit(BaseModel):
    """One document returned by a search, in the normalized content model."""

    id: str = Field(description="Repository UUID of the document.")
    repository: Optional[str] = Field(
        default=None, description="Name of the Nuxeo repository holding the document."
    )
    documentType: Optional[str] = Field(
        default=None, description="Document type, e.g. File, Note, Folder."
    )
    title: Optional[str] = Field(default=None, description="Document title.")
    path: Optional[str] = Field(default=None, description="Repository path.")
    createdAt: Optional[str] = Field(
        default=None, description="ISO 8601 creation date."
    )
    modifiedAt: Optional[str] = Field(
        default=None, description="ISO 8601 last modification date."
    )
    createdBy: Optional[str] = Field(
        default=None, description="Username of the creator."
    )
    modifiedBy: Optional[str] = Field(
        default=None, description="Username of the last contributor."
    )
    version: Optional[str] = Field(
        default=None, description="Version label, when versioned."
    )
    state: Optional[str] = Field(default=None, description="Lifecycle state.")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Document properties, as returned by the repository.",
    )

    # Search-specific fields. Populated only by modes that rank or explain matches;
    # null/empty elsewhere so that the shape stays constant across modes.
    score: Optional[float] = Field(
        default=None,
        description="Relevance score. Null for modes that do not rank, such as nxql.",
    )
    snippets: List[str] = Field(
        default_factory=list,
        description=(
            "Passages explaining why this document matched -- semantic chunks or "
            "highlight fragments depending on the mode. Empty when the mode "
            "produces no evidence passages."
        ),
    )

    extensions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Repository-specific values with no normalized equivalent, keyed by repository.",
    )


class SearchResult(BaseModel):
    """Envelope returned by every search mode."""

    documents: List[SearchHit] = Field(default_factory=list)
    totalCount: int = Field(
        default=0,
        description=(
            "Total matches, not the page size. Exception: ranking modes such as "
            "semantic have no exhaustive match count -- there it is the number of "
            "candidates the retrieval considered, which grows with pageSize. Do not "
            "read it as a corpus-wide total in that mode."
        ),
    )
    pageIndex: int = Field(
        default=0, description="Zero-based index of the returned page."
    )
    pageSize: int = Field(
        default=0, description="Number of documents requested per page."
    )
    hasMore: bool = Field(
        default=False, description="True when further pages are available."
    )
    mode: str = Field(description="Query mode that produced this result.")
    interpretedQuery: Optional[str] = Field(
        default=None,
        description=(
            "The NXQL actually executed. For natural and semantic modes this is the "
            "generated query, so the caller can see how the request was understood."
        ),
    )
    # Deliberately no aggregations field. This tool returns documents; counts and
    # groupings are served by nuxeo_search_documents_with_query_dsl, which can
    # express them natively. A field the normalized modes never populate would
    # only invite a model to ask for aggregations here.
    degraded: Optional[str] = Field(
        default=None,
        description=(
            "Set when the request succeeded but not as asked -- for example when "
            "natural-language parsing failed and a fulltext fallback was used. "
            "Null on a normal result."
        ),
    )


def _first(
    entry: Dict[str, Any], properties: Dict[str, Any], *keys: str
) -> Optional[Any]:
    """Return the first non-null value found under ``keys``, entry before properties."""
    for key in keys:
        value = entry.get(key)
        if value is not None:
            return value
        value = properties.get(key)
        if value is not None:
            return value
    return None


def to_search_hit(
    entry: Dict[str, Any],
    *,
    score: Optional[float] = None,
    snippets: Optional[List[str]] = None,
) -> SearchHit:
    """Map one Nuxeo REST ``document`` entry onto the normalized model.

    Dublin Core values live in ``properties`` only when the caller asked for the
    schema, and some of them are mirrored at the top level of the entry, so each
    field is resolved from both places.
    """
    properties: Dict[str, Any] = entry.get("properties") or {}

    extensions: Dict[str, Any] = {}
    for key in (
        "isCheckedOut",
        "isVersion",
        "isProxy",
        "isTrashed",
        "isRecord",
        "hasLegalHold",
        "parentRef",
        "changeToken",
        "facets",
    ):
        if key in entry and entry[key] is not None:
            extensions[key] = entry[key]

    return SearchHit(
        id=entry.get("uid") or entry.get("id") or "",
        repository=entry.get("repository"),
        documentType=entry.get("type"),
        title=_first(entry, properties, "title", "dc:title"),
        path=entry.get("path"),
        createdAt=_first(entry, properties, "dc:created"),
        modifiedAt=_first(entry, properties, "lastModified", "dc:modified"),
        createdBy=_first(entry, properties, "dc:creator"),
        modifiedBy=_first(entry, properties, "dc:lastContributor"),
        version=entry.get("versionLabel"),
        state=entry.get("state"),
        metadata=properties,
        score=score,
        snippets=list(snippets or []),
        extensions={"nuxeo": extensions} if extensions else {},
    )


def _evidence(
    entry: Dict[str, Any], include_snippets: bool
) -> tuple[Optional[float], List[str]]:
    """Pull the relevance score and matching passages out of ``contextParameters``.

    Both come from document enrichers, so they are present only when the caller
    asked for them and the server supports them -- ``score`` needs Nuxeo 2025.22+.
    Absent enrichers mean a null score and no snippets, never an error, which is
    what keeps the envelope constant across modes and server versions.
    """
    context = entry.get("contextParameters") or {}

    raw_score = context.get("score")
    try:
        score = float(raw_score) if raw_score is not None else None
    except (TypeError, ValueError):
        score = None

    snippets: List[str] = []
    if include_snippets:
        for highlight in context.get("highlight") or []:
            for segment in highlight.get("segments") or []:
                text = (segment or "").replace("\n", " ").strip()
                if text:
                    snippets.append(text)

    return score, snippets


def to_search_result(
    query_result: Dict[str, Any],
    *,
    mode: str,
    interpreted_query: Optional[str] = None,
    page_size: int = 0,
    page_index: int = 0,
    degraded: Optional[str] = None,
    include_snippets: bool = True,
) -> SearchResult:
    """Map a Nuxeo paginated query response onto the envelope."""
    entries = query_result.get("entries") or []
    total = query_result.get("resultsCount")
    if total is None:
        total = query_result.get("totalSize", len(entries))

    documents = []
    for entry in entries:
        score, snippets = _evidence(entry, include_snippets)
        documents.append(to_search_hit(entry, score=score, snippets=snippets))

    return SearchResult(
        documents=documents,
        totalCount=int(total or 0),
        pageIndex=int(query_result.get("currentPageIndex", page_index) or 0),
        pageSize=int(query_result.get("pageSize", page_size) or 0),
        hasMore=bool(query_result.get("isNextPageAvailable", False)),
        mode=mode,
        interpretedQuery=interpreted_query,
        degraded=degraded,
    )
