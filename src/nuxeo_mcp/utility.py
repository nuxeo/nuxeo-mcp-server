#!/usr/bin/env python3
"""
Utility functions for the Nuxeo MCP Server.

This module provides utility functions for working with Nuxeo documents and other
common tasks.
"""

import base64
from typing import Dict, Any, List, Tuple
from nuxeo.models import Document
from mcp.types import ImageContent as Image, TextContent as File
from uuid import UUID


def is_uuid(v: str) -> bool:
    try:
        # Try parsing as a UUID version 4 (adjust version if needed)
        uuid_obj = UUID(v, version=4)
    except ValueError:
        return False
    # Ensure the string matches the canonical dashed format
    return str(uuid_obj) == v


def format_as_markdown_file(md_data):
    result = File(
        data="\n".join(md_data).encode(),
        #    name=f"doc_list_{id(docs)}.md",
        format="text",
    )
    result._mime_type = "text/markdown"

    return result


def format_result(result: Any) -> str | Image:

    if hasattr(result, "is_document") and result.is_document:
        return format_doc(result)
    elif (
        isinstance(result, list)
        and len(result) > 0
        and hasattr(result[0], "is_document")
        and result[0].is_document
    ):
        return format_docs(result)

    return None


def format(result: dict[str, Any], content_type="application/json") -> dict[str, Any]:
    match content_type:
        case "text/markdown":
            return format_page(result)
        case "application/json":
            return format_json(result)


def format_page(result: Dict[str, Any]) -> dict[str, Any]:
    md_output: list[str] = []
    md_output.append(f" resultsCount: {result['resultsCount']}")
    md_output.append(f" pageIndex: {result['pageIndex']}")
    md_output.append(f" pageCount: {result['pageCount']}")

    return {
        "content_type": "text/markdown",
        "content": format_docs(result["entries"], md_output),
    }


def format_json(result: dict[str, Any]) -> dict[str, Any]:
    json_output: dict[str, Any] = {
        "resultsCount": result["resultsCount"],
        "pageIndex": result["pageIndex"],
        "pageCount": result["pageCount"],
    }

    documents: list[tuple[Any, ...]] = []
    for doc in result["entries"]:
        documents.append((doc.uid, doc.path.split("/")[-1], doc.title, doc.type))

    json_output["documents"] = documents
    return {"content_type": "application/json", "content": json_output}


def format_docs(
    docs: list[Document], md_output: list[str] | None = None, as_resource: bool = False
) -> str:
    if as_resource:
        return [f"nuxeo://{doc.uid}" for doc in docs]

    if md_output is None:
        md_output: list[str] = []

    md_output.append("| uuid | name | title | type |")
    md_output.append("| ---- | ---- | ----- | ---- |")

    for doc in docs:
        md_output.append(
            f"| {doc.uid} | {doc.path.split('/')[-1]} | {doc.title} | {doc.type} |"
        )

    return ("\n".join(md_output),)


def format_doc(
    doc: Dict[str, Any] | Document, as_resource: bool = False
) -> Dict[str, str] | str:
    """
    Format a Nuxeo document as markdown text.

    Args:
        doc: A Nuxeo document as a dictionary
        as_resource : ask for the output to be a resource (nuxeo://)

    Returns:
        A dictionary with content and content_type keys or the uri of the Document
    """

    if as_resource:
        return f"nuxeo://{doc.uid}"

    if doc is None:
        return {"content": "No document provided", "content_type": "text/plain"}

    if type(doc) == Document:
        doc = doc.as_dict()

    # Extract basic document information
    uid = doc.get("uid", "Unknown")
    doc_type = doc.get("type", "Unknown")
    title = doc.get("title", "Untitled")
    path = doc.get("path", "Unknown")
    facets = doc.get("facets", [])

    # Extract flags
    is_proxy = doc.get("isProxy", False)
    is_checked_out = doc.get("isCheckedOut", False)
    is_trashed = doc.get("isTrashed", False)
    is_version = doc.get("isVersion", False)

    # Start building the markdown output
    md_output = f"# Document: {title}\n\n"

    # Add basic information
    md_output += "## Basic Information\n\n"
    md_output += f"- **UID**: {uid}\n"
    md_output += f"- **Type**: {doc_type}\n"
    md_output += f"- **Path**: {path}\n"

    # Add facets
    if facets:
        md_output += f"- **Facets**: {', '.join(facets)}\n"
    else:
        md_output += "- **Facets**: None\n"

    # Add flags
    md_output += "\n## Flags\n\n"
    md_output += f"- **Is Proxy**: {is_proxy}\n"
    md_output += f"- **Is Checked Out**: {is_checked_out}\n"
    md_output += f"- **Is Trashed**: {is_trashed}\n"
    md_output += f"- **Is Version**: {is_version}\n"

    # Process properties
    properties = doc.get("properties", {})
    if properties:
        md_output += "\n## Properties\n\n"

        # Group properties by namespace
        namespaces: Dict[str, List[Tuple[str, Any]]] = {}

        for prop_key, prop_value in properties.items():
            # Extract namespace from property key (e.g., "dc:title" -> "dc")
            namespace = prop_key.split(":")[0] if ":" in prop_key else "other"

            if namespace not in namespaces:
                namespaces[namespace] = []

            namespaces[namespace].append((prop_key, prop_value))

        # Create a table for each namespace
        for namespace, props in namespaces.items():
            md_output += f"### {namespace.upper()} Namespace\n\n"
            md_output += "| Property | Value |\n"
            md_output += "|----------|-------|\n"

            for prop_key, prop_value in props:
                # Format the property value for display
                formatted_value = format_property_value(prop_value)
                md_output += f"| {prop_key} | {formatted_value} |\n"

            md_output += "\n"

    # Return the markdown as a plain string - MCP will handle the wrapping
    # Don't return a dict with content/content_type as that causes structured_content errors
    return md_output


def format_property_value(value: Any) -> str:
    """
    Format a property value for display in markdown.

    Args:
        value: The property value to format

    Returns:
        A string representation of the value suitable for markdown
    """
    if value is None:
        return "*None*"
    elif isinstance(value, list):
        if not value:
            return "*Empty list*"
        return ", ".join(str(item) for item in value)
    elif isinstance(value, dict):
        if not value:
            return "*Empty object*"
        return "*Complex object*"
    elif isinstance(value, bool):
        return str(value)
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        if not value:
            return "*Empty string*"
        # Escape pipe characters in markdown tables
        return value.replace("|", "\\|")
    else:
        return str(value)


def return_blob(blob_info: dict):

    if "image/" in blob_info["mime_type"]:
        encoded = base64.b64encode(blob_info["content"]).decode("ascii")
        return Image(type="image", data=encoded, mimeType=blob_info["mime_type"])

    return blob_info["content"]
