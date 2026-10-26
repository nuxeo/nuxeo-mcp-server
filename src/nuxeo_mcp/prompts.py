#!/usr/bin/env python3
"""
Nuxeo MCP Server prompts.

This module defines the prompts for the Nuxeo MCP Server.
"""

import logging
from typing import Any, Callable, Dict, Optional

from nuxeo_mcp.utility import format_doc

# Configure logging
logger = logging.getLogger("nuxeo_mcp.resources")

# Type aliases
ResourceFunction = Callable[[], Dict[str, Any]]


def register_prompts(mcp, nuxeo) -> None:
    """
    Register MCP prompts with the FastMCP server.

    Args:
        mcp: The FastMCP server instance
        nuxeo: The Nuxeo client instance
    """
    # Get the Nuxeo URL and username from the client
    nuxeo_url = nuxeo.client.host  # Resource: Nuxeo Server Information

    @mcp.prompt
    def list_doc_by_type(type: str) -> str:
        """Do a search"""
        return f"Search for the 20 most recent documents of type {type}."
