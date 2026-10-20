"""
Unit tests for the Nuxeo MCP Server.

These tests verify the functionality of the MCP server using mocks,
without requiring a connection to a real Nuxeo server.
"""

import pytest
import unittest.mock as mock
import sys
from typing import List, Dict, Any, Optional, Callable, Union, Type
from unittest.mock import MagicMock, patch

# Create mocks for the unit tests
mock_nuxeo_client = MagicMock()
mock_fastmcp = MagicMock()

# Create a mock FastMCP class for unit tests
class MockFastMCP:
    def __init__(self, name: str):
        self.name: str = name
        self.tools: List[Dict[str, Any]] = []
        self.resources: List[Dict[str, Any]] = []
        self.prompts: List[Dict[str, Any]] = []
        self.custom_routes: List[Dict[str, Any]] = []
    
    def tool(self, name: Optional[str] = None, description: Optional[str] = None, input_schema: Optional[Dict[str, Any]] = None):
        def decorator(func):
            # Support both @mcp.tool() and @mcp.tool(name="...", description="...")
            tool_name = name if name else func.__name__
            tool_desc = description if description else (func.__doc__ or "").strip()
            self.tools.append({
                "name": tool_name, 
                "description": tool_desc, 
                "input_schema": input_schema,
                "func": func
            })
            return func
        return decorator
    
    def resource(self, uri: Optional[str] = None, name: Optional[str] = None, description: Optional[str] = None):
        def decorator(func):
            # Support both @mcp.resource() and @mcp.resource(uri="...", name="...", description="...")
            resource_uri = uri if uri else func.__name__
            resource_name = name if name else func.__name__
            resource_desc = description if description else (func.__doc__ or "").strip()
            self.resources.append({"uri": resource_uri, "name": resource_name, "description": resource_desc, "func": func})
            return func
        return decorator
    
    def prompt(self, func=None):
        if func is None:
            def decorator(f):
                self.prompts.append({
                    "name": f.__name__,
                    "description": f.__doc__ or "",
                    "func": f
                })
                return f
            return decorator
        else:
            self.prompts.append({
                "name": func.__name__,
                "description": func.__doc__ or "",
                "func": func
            })
            return func
    
    def custom_route(self, path: str, methods: Optional[List[str]] = None):
        """Mock custom_route decorator for health check endpoint."""
        def decorator(func):
            self.custom_routes.append({
                "path": path,
                "methods": methods or ["GET"],
                "func": func
            })
            return func
        return decorator
    
    def list_tools(self) -> List[Any]:
        return [type('Tool', (), {'name': t['name']}) for t in self.tools]
    
    def list_resources(self) -> List[Any]:
        return [type('Resource', (), {'uri': r['uri']}) for r in self.resources]
    
    
    def run(self) -> None:
        pass

# NuxeoMCPServer takes the FastMCP class as a parameter, so these tests inject
# MockFastMCP directly. Do not patch sys.modules['fastmcp']: that leaks a mock
# into every other test module for the whole session.
from nuxeo_mcp.server import NuxeoMCPServer


@pytest.mark.unit
def test_mcp_server_initialization() -> None:
    """Test that the MCP server can be initialized."""
    # Mock the Nuxeo client to avoid actual connection
    with mock.patch('nuxeo_mcp.server.Nuxeo'):
        server = NuxeoMCPServer(
            nuxeo_url="http://localhost:8080/nuxeo",
            username="Administrator",
            password="Administrator",
            fastmcp_class=MockFastMCP,
        )
        
        # Check that the server was initialized correctly
        assert server.nuxeo_url == "http://localhost:8080/nuxeo"
        assert server.username == "Administrator"
        assert server.password == "Administrator"
        assert server.mcp is not None


@pytest.mark.unit
def test_mcp_tools_registration() -> None:
    """Test that the MCP server registers tools correctly."""
    # Mock the Nuxeo client to avoid actual connection
    with mock.patch('nuxeo_mcp.server.Nuxeo'):
        server = NuxeoMCPServer(fastmcp_class=MockFastMCP)
        
        # Get the list of tools
        tools = server.mcp.list_tools()
        
        # Check that the expected tools are registered
        tool_names = [tool.name for tool in tools]
        assert "get_repository_info" in tool_names


@pytest.mark.unit
def test_mcp_resources_registration() -> None:
    """Test that the MCP server registers resources correctly."""
    # Mock the Nuxeo client to avoid actual connection
    with mock.patch('nuxeo_mcp.server.Nuxeo'):
        server = NuxeoMCPServer(fastmcp_class=MockFastMCP)
        
        # Get the list of resources
        resources = server.mcp.list_resources()
        
        # Check that the expected resources are registered
        resource_uris = [resource.uri for resource in resources]
        assert "nuxeo://info" in resource_uris
