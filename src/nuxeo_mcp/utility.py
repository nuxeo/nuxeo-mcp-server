#!/usr/bin/env python3
# (C) Copyright 2026 Hyland (https://hyland.com/) and others.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Utility functions for the Nuxeo MCP Server.

This module provides utility functions for working with Nuxeo documents and other
common tasks.
"""

import base64
from typing import Any, Dict, List, Tuple
from uuid import UUID

from mcp.types import ImageContent as Image
from nuxeo.models import Document


def is_uuid(v: str) -> bool:
    try:
        # Try parsing as a UUID version 4 (adjust version if needed)
        uuid_obj = UUID(v, version=4)
    except ValueError:
        return False
    # Ensure the string matches the canonical dashed format
    return str(uuid_obj) == v


def format_docs(docs: list[Document], as_resource: bool = False) -> str:
    if as_resource:
        return "\n".join(f"nuxeo://{doc.uid}" for doc in docs)

    md_output: list[str] = []
    md_output.append("| uuid | name | title | type |")
    md_output.append("| ---- | ---- | ----- | ---- |")

    for doc in docs:
        md_output.append(
            f"| {doc.uid} | {doc.path.split('/')[-1]} | {doc.title} | {doc.type} |"
        )

    return "\n".join(md_output)


def format_doc(doc: Dict[str, Any] | Document) -> str:
    """Format a Nuxeo document, or its dictionary form, as markdown text."""
    if isinstance(doc, Document):
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


def return_blob(blob_info: Dict[str, Any]) -> str | bytes | Image:
    """Return image blobs as ImageContent, anything else as its raw content."""

    content: str | bytes = blob_info["content"]
    if "image/" in blob_info["mime_type"]:
        # ImageContent.data is a base64-encoded string, never raw bytes.
        if isinstance(content, bytes):
            content = base64.b64encode(content).decode("ascii")
        return Image(type="image", data=content, mime_type=blob_info["mime_type"])
    return content
