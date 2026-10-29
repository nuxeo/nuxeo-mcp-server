"""Safety annotations for every registered tool.

MCP annotations tell a client what a tool will do before it is called, so a host
can gate writes behind confirmation and let reads run freely. They are hints,
not enforcement -- the repository's ACLs remain the authority -- but without them
every tool looks equally dangerous and a cautious client has to prompt for all
of them.

``open_world_hint`` is the one worth reasoning about rather than copying. It is
False for tools that reach one fixed, tenant-scoped Nuxeo API with a closed set
of operations, and True for the two that accept caller-supplied payloads the
server does not interpret: ``nuxeo_execute_operation``, which runs an arbitrary
named Automation operation, and the Query DSL tools, which forward an arbitrary
engine query. Those three can reach places the schema does not describe.

``destructive_hint`` only means something when ``read_only_hint`` is False. It
is True where a call removes or overwrites state that the caller cannot trivially
reconstruct.
"""

from typing import Dict

from mcp.types import ToolAnnotations


def _read(title: str, *, open_world: bool = False) -> ToolAnnotations:
    """A read-only call: no state changes, safe to repeat."""
    return ToolAnnotations(
        title=title,
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=open_world,
    )


def _write(
    title: str,
    *,
    destructive: bool = False,
    idempotent: bool = False,
    open_world: bool = False,
) -> ToolAnnotations:
    """A call that changes repository state."""
    return ToolAnnotations(
        title=title,
        read_only_hint=False,
        destructive_hint=destructive,
        idempotent_hint=idempotent,
        open_world_hint=open_world,
    )


TOOL_ANNOTATIONS: Dict[str, ToolAnnotations] = {
    # Discovery and introspection
    "nuxeo_get_repository_info": _read("Get repository information"),
    "nuxeo_list_document_types": _read("List document types"),
    "nuxeo_get_metadata_schema": _read("Get metadata schemas"),
    "nuxeo_list_operations": _read("List Automation operations"),
    # Read
    "nuxeo_list_children": _read("List children of a folder"),
    "nuxeo_get_document": _read("Get a document"),
    "nuxeo_search_documents": _read("Search documents"),
    # Raw engine queries: the caller supplies a body this server does not
    # interpret, so the reachable surface is not described by the tool schema.
    "nuxeo_search_documents_with_query_dsl": _read(
        "Search documents with Query DSL", open_world=True
    ),
    "nuxeo_search_audit_with_query_dsl": _read(
        "Search the audit log with Query DSL", open_world=True
    ),
    # Write
    "nuxeo_create_document": _write("Create a document"),
    # Overwrites the previous property values; repeating the same call converges
    # on the same state.
    "nuxeo_update_metadata": _write(
        "Update document metadata", destructive=True, idempotent=True
    ),
    # Not idempotent: the source is a UID, which survives the move, so a replay
    # moves the document into the folder it is already in and Nuxeo renames it
    # with a timestamp suffix (verified on LTS 2025).
    "nuxeo_move_document": _write("Move or rename a document", destructive=True),
    "nuxeo_delete_document": _write(
        "Delete a document", destructive=True, idempotent=True
    ),
    # Runs an arbitrary named Automation operation: the effect depends entirely
    # on which operation the caller picks, so assume the worst on every axis.
    "nuxeo_execute_operation": _write(
        "Execute a Nuxeo Automation operation", destructive=True, open_world=True
    ),
}
