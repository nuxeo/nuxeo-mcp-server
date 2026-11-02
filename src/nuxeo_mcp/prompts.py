#!/usr/bin/env python3
"""
Nuxeo MCP Server prompts.

This module defines the prompts for the Nuxeo MCP Server.
"""

import logging

# Configure logging
logger = logging.getLogger("nuxeo_mcp.prompts")


def register_prompts(mcp, nuxeo) -> None:
    """
    Register MCP prompts with the FastMCP server.

    Args:
        mcp: The FastMCP server instance
        nuxeo: The Nuxeo client instance
    """
    # Get the Nuxeo URL and username from the client

    @mcp.prompt
    def list_doc_by_type(type: str) -> str:
        """Do a search"""
        return f"Search for the 20 most recent documents of type {type}."
