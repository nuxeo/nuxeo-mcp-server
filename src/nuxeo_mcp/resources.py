#!/usr/bin/env python3
"""
Nuxeo MCP Server resources.

This module defines the resources for the Nuxeo MCP Server.
"""

import logging
import os
from typing import Any, Dict, Optional, Callable
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

        print(f"CALLING adapter api on {uri}")
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
        description="Comprehensive documentation for NXQL (Nuxeo Query Language) syntax and usage",
    )
    def get_nxql_guide() -> Dict[str, Any]:
        """
        Get the NXQL guide documentation.

        Returns:
            The NXQL guide content or error message
        """
        try:
            # Get the path to the NXQL guide file
            guide_path = os.path.join(os.path.dirname(__file__), "../../specs/19_nxql_guide.md")

            # Read the guide content
            if os.path.exists(guide_path):
                with open(guide_path, "r", encoding="utf-8") as f:
                    content = f.read()

                return {
                    "content": content,
                    "format": "markdown",
                    "title": "NXQL Query Language Guide",
                    "description": "Complete reference for NXQL syntax, operators, properties, and MongoDB limitations",
                }
            else:
                return {"error": "NXQL guide file not found", "path": guide_path}
        except Exception as e:
            logger.error(f"Error reading NXQL guide: {e}")
            return {"error": str(e)}

    # Resource: Query DSL field references
    #
    # Nuxeo's /site/es passthrough exposes _search only -- _mapping, _field_caps
    # and _settings all answer 404 -- so field names cannot be discovered at
    # runtime and are served from here instead. This matters because an unknown
    # field name is not an error: it matches nothing and returns HTTP 200 with
    # zero hits, which reads as "no document matches".
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
        return {
            "content": query_dsl.field_guide(),
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
        return {
            "content": query_dsl.audit_field_guide(),
            "format": "markdown",
            "title": "Audit Query DSL Field Reference",
        }
