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
Nuxeo MCP Server prompts.

This module defines the prompts for the Nuxeo MCP Server.
"""

import logging
from typing import Any

# Configure logging
logger = logging.getLogger("nuxeo_mcp.prompts")


def register_prompts(mcp: Any, nuxeo: Any) -> None:
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
