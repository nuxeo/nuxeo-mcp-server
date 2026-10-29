#!/usr/bin/env python3
"""
Nuxeo MCP Server resources.

This module defines the resources for the Nuxeo MCP Server.
"""

import logging
import os
from importlib import resources
from typing import Any, Callable, Dict, Optional, Tuple

from fastmcp.exceptions import ToolError

from nuxeo_mcp import query_dsl
from nuxeo_mcp.utility import format_doc, return_blob

# Configure logging
logger = logging.getLogger("nuxeo_mcp.resources")

# Type aliases
ResourceFunction = Callable[[], Dict[str, Any]]


def register_resources(mcp, nuxeo) -> None:
    """
    Register MCP resources with the FastMCP server.

    Args:
        mcp: The FastMCP server instance
        nuxeo: The Nuxeo client instance
    """
    # Get the Nuxeo URL and username from the client
    nuxeo_url = nuxeo.client.host  # Resource: Nuxeo Server Information

    @mcp.resource(
        uri="nuxeo://info",
        name="Nuxeo Server Information",
        description="Basic information about the connected Nuxeo server",
    )
    def get_nuxeo_info() -> Dict[str, Any]:
        """
        Get basic information about the Nuxeo server.

        Returns:
            Basic information about the Nuxeo server
        """
        try:
            # Get server information from the Nuxeo client
            try:
                server_info = nuxeo.client.server_info()
                version = server_info.get("productVersion", "Unknown")
            except Exception:
                version = "Unknown"

            info = {
                "url": nuxeo_url,
                "connected": True,
                "version": version,
            }
            return info
        except Exception as e:
            logger.error(f"Error getting Nuxeo info: {e}")
            return {"error": str(e)}

    @mcp.resource(
        uri="nuxeo://{uid}",
        name="Get  Document using UUID",
        description="Get  Document using UUID",
    )
    def get_document(uid: str) -> Dict[str, Any]:

        return format_doc(nuxeo.documents.get(uid=uid).as_dict())

    @mcp.resource(
        uri="nuxeo://{path*}",
        name="Get  Document using the path",
        description="Get  Document using the path",
    )
    def get_document_by_path(path: str) -> Dict[str, Any]:

        if not path.startswith("/"):
            path = f"/{path}"

        if "@" in path:
            parts = path.split("@")
            path = parts[0]
            adapter_path = parts[1]
            parts = adapter_path.split("/")
            adapter = parts[0]
            adapter_param = None
            if len(parts) > 1:
                adapter_param = adapter_path[len[adapter] :]

            return get_document_with_dapater(
                uid, adapter=adapter, adapter_param=adapter_param
            )

        return format_doc(nuxeo.documents.get(path=path).as_dict())

    @mcp.resource(
        uri="nuxeo://{uid}@{adapter}/{adapter_param}",
        name="Get Document with adapter",
        description="Get Document with adapter ",
    )
    def get_document_with_dapater(
        uid: str, adapter: str, adapter_param: str | None
    ) -> Dict[str, Any]:

        uid = uid.trim()

        uri: str = f"api/v1/repo/default/id/{uid}/@{adapter}"
        if adapter_param:
            uri = f"{uri}/{adapter_param}"

        logger.debug(f"Calling adapter API on {uri}")
        r = nuxeo.client.request("GET", uri)

        disposition = r.headers.get("content-disposition", None)
        if disposition:
            filename = disposition.split(";")[-1].split("=")[-1]
            content_length = int(r.headers["content-length"])
            mime = r.headers["content-type"]
            blob_info = {
                "name": filename,
                "mime_type": mime,
                "size": content_length,
                "content": r.content,
            }
            return return_blob(blob_info)

        else:
            return r.content

    # Resource: NXQL Guide Documentation
    @mcp.resource(
        uri="nuxeo://nxql-guide",
        name="NXQL Query Language Guide",
        description=(
            "NXQL for nuxeo_search_documents: the default filter to start from, "
            "syntax, full-text search, properties and examples"
        ),
    )
    def get_nxql_guide() -> Dict[str, Any]:
        """Return the NXQL syntax reference.

        Read from the installed package rather than a path relative to this
        file: the guide used to live in specs/, which ships in neither the
        wheel nor the container image, so this resource only ever worked from
        a source checkout.

        Raises:
            ToolError: if the packaged guide is missing, rather than returning
                an error payload a model would read as content.
        """
        try:
            content = (
                resources.files("nuxeo_mcp.guides")
                .joinpath("nxql.md")
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError) as e:
            logger.error(f"Packaged NXQL guide is missing: {e}")
            raise ToolError(
                "The NXQL guide is missing from this installation. "
                "Reinstall the package or report this as a packaging bug."
            )

        return {
            "content": content,
            "format": "markdown",
            "title": "NXQL Query Language Guide",
            "description": "NXQL for nuxeo_search_documents: default filter, syntax, "
            "full-text search, properties and examples",
        }

    # Resource: Query DSL field references
    #
    # Nuxeo's /site/es passthrough exposes _search only -- _mapping, _field_caps
    # and _settings all answer 404 -- so there is no schema endpoint to read.
    # The curated tables cover the fields every Nuxeo has; the instance-specific
    # ones are discovered by sampling _source keys from real documents. This
    # matters because an unknown field name is not an error: it matches nothing
    # and returns HTTP 200 with zero hits, which reads as "no document matches".
    def _discover_fields(index: str) -> Tuple[Optional[list], Optional[str]]:
        """Sample field names from an index.

        Returns:
            ``(fields, unavailable)``. ``fields`` is None when sampling failed;
            ``unavailable`` explains why when the failure means the matching
            Query DSL tool cannot work on this server for the current user.

        A guide that is slightly less complete is far better than a guide that
        fails, so every error here degrades to the curated tables. But a guide
        that looks normal for a tool that can only fail sends the model into a
        retry loop, so that case is stated upfront.
        """
        from .es_passthrough import ElasticsearchPassthrough, PassthroughError

        try:
            passthrough = ElasticsearchPassthrough(
                nuxeo_url=os.environ.get("NUXEO_URL", nuxeo.client.host),
                auth=nuxeo.client.auth,
            )
            return query_dsl.sample_field_names(passthrough.execute_query, index), None
        except PassthroughError as e:
            logger.info(f"Could not sample {index} fields: {e}")
            return None, str(e) if e.unavailable else None
        except Exception as e:
            logger.info(
                f"Could not sample {index} fields, serving curated guide only: {e}"
            )
            return None, None

    def _with_warning(content: str, unavailable: Optional[str]) -> str:
        if not unavailable:
            return content
        return f"> **Unavailable on this server:** {unavailable}\n\n{content}"

    @mcp.resource(
        uri="nuxeo://query-dsl-guide",
        name="Repository Query DSL Field Reference",
        description=(
            "Field names, limits and worked examples for "
            "nuxeo_search_documents_with_query_dsl"
        ),
    )
    def get_query_dsl_guide() -> Dict[str, Any]:
        """Return the repository index field reference."""
        fields, unavailable = _discover_fields("nuxeo")
        return {
            "content": _with_warning(query_dsl.field_guide(fields), unavailable),
            "format": "markdown",
            "title": "Repository Query DSL Field Reference",
        }

    @mcp.resource(
        uri="nuxeo://audit-query-dsl-guide",
        name="Audit Query DSL Field Reference",
        description=(
            "Field names, limits and worked examples for "
            "nuxeo_search_audit_with_query_dsl"
        ),
    )
    def get_audit_query_dsl_guide() -> Dict[str, Any]:
        """Return the audit index field reference."""
        fields, unavailable = _discover_fields("audit")
        return {
            "content": _with_warning(query_dsl.audit_field_guide(fields), unavailable),
            "format": "markdown",
            "title": "Audit Query DSL Field Reference",
        }
