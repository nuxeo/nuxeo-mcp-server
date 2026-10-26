"""
Integration tests for the Nuxeo MCP Server.

These tests require a running Nuxeo server and test the actual integration
with the Nuxeo Content Repository.
"""

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

import pytest
from nuxeo.client import Nuxeo

from nuxeo_mcp.server import NuxeoMCPServer

logging.basicConfig(level=logging.INFO)


# Create a mock FastMCP class for integration tests
class MockFastMCP:
    def __init__(self, name: str):
        self.name: str = name
        self.tools: List[Dict[str, Any]] = []
        self.resources: List[Dict[str, Any]] = []
        self.prompts: List[Dict[str, Any]] = []
        self.custom_routes: List[Dict[str, Any]] = []

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        annotations: Any = None,
    ):
        def decorator(func):
            # Support both @mcp.tool() and @mcp.tool(name="...", description="...")
            tool_name = name if name else func.__name__
            tool_desc = description if description else (func.__doc__ or "").strip()
            self.tools.append(
                {
                    "name": tool_name,
                    "description": tool_desc,
                    "input_schema": input_schema,
                    "annotations": annotations,
                    "func": func,
                }
            )
            return func

        return decorator

    def resource(self, uri: str, name: str, description: str):
        def decorator(func):
            self.resources.append(
                {"uri": uri, "name": name, "description": description, "func": func}
            )
            return func

        return decorator

    def prompt(self, func=None):
        if func is None:

            def decorator(f):
                self.prompts.append(
                    {"name": f.__name__, "description": f.__doc__ or "", "func": f}
                )
                return f

            return decorator
        else:
            self.prompts.append(
                {"name": func.__name__, "description": func.__doc__ or "", "func": func}
            )
            return func

    def custom_route(self, path: str, methods: Optional[List[str]] = None):
        """Mock custom_route decorator for health check endpoint."""

        def decorator(func):
            self.custom_routes.append(
                {"path": path, "methods": methods or ["GET"], "func": func}
            )
            return func

        return decorator

    def list_tools(self) -> List[Any]:
        return [type("Tool", (), {"name": t["name"]}) for t in self.tools]

    def list_resources(self) -> List[Any]:
        return [type("Resource", (), {"uri": r["uri"]}) for r in self.resources]

    def run(self) -> None:
        pass


@pytest.mark.integration
def test_nuxeo_client_connection(
    nuxeo_container: Any, nuxeo_url: str, nuxeo_credentials: Tuple[str, str]
) -> None:
    """Test that we can connect to the Nuxeo server."""
    # This is an integration test that requires a running Nuxeo server
    print("\nWaiting for Nuxeo server to be ready for testing...")

    username, password = nuxeo_credentials

    # Create a real Nuxeo instance
    nuxeo = Nuxeo(
        host=nuxeo_url,
        auth=(username, password),
    )

    # Test connection to runningstatus endpoint only
    print("Testing connection to Nuxeo server runningstatus endpoint...")

    try:
        print("Trying endpoint: /runningstatus")
        response = nuxeo.client.request("GET", "/runningstatus")
        print(f"Response status: {response.status_code}")

        assert (
            response.status_code == 200
        ), f"Expected status code 200, got {response.status_code}"
        print("Successfully connected to Nuxeo server via /runningstatus!")

        # Check response content
        print(f"Response content: {response.text}")
        # The response is a JSON object with status information, not just "true"
        assert "ok" in response.text.lower(), "Expected 'ok' in response content"
    except Exception as e:
        print(f"Error connecting to /runningstatus: {e}")
        raise


@pytest.mark.integration
def test_nuxeo_mcp_server_with_real_nuxeo(
    nuxeo_container: Any, nuxeo_url: str, nuxeo_credentials: Tuple[str, str]
) -> None:
    """Test that the MCP server can connect to a real Nuxeo server."""
    print("\nTesting MCP server connection to Nuxeo...")

    username, password = nuxeo_credentials

    # Create a real NuxeoMCPServer instance with MockFastMCP
    server = NuxeoMCPServer(
        nuxeo_url=nuxeo_url,
        username=username,
        password=password,
        fastmcp_class=MockFastMCP,
    )

    # Check that the server was initialized correctly
    assert server.nuxeo_url == nuxeo_url
    assert server.username == username
    assert server.password == password
    assert server.nuxeo is not None
    assert server.mcp is not None

    # Check that the tools are registered
    print("Checking MCP server tools...")
    tools = server.mcp.list_tools()
    tool_names = [tool.name for tool in tools]
    print(f"Registered tools: {tool_names}")
    assert "nuxeo_get_repository_info" in tool_names
    assert "nuxeo_list_children" in tool_names
    assert "nuxeo_search_documents" in tool_names

    # Check that the resources are registered
    print("Checking MCP server resources...")
    resources = server.mcp.list_resources()
    resource_uris = [resource.uri for resource in resources]
    print(f"Registered resources: {resource_uris}")
    assert "nuxeo://info" in resource_uris
    assert "nuxeo://{uid}" in resource_uris
    assert "nuxeo://{path*}" in resource_uris

    print("MCP server successfully initialized!")


@pytest.mark.integration
def test_get_repository_info_tool(
    nuxeo_container: Any, nuxeo_url: str, nuxeo_credentials: Tuple[str, str]
) -> None:
    """Test the get_repository_info tool."""
    print("\nTesting get_repository_info tool...")

    username, password = nuxeo_credentials

    # Create a real NuxeoMCPServer instance with MockFastMCP
    server = NuxeoMCPServer(
        nuxeo_url=nuxeo_url,
        username=username,
        password=password,
        fastmcp_class=MockFastMCP,
    )

    # Find the get_repository_info tool
    get_repository_info_tool = None
    for tool in server.mcp.tools:
        if tool["name"] == "nuxeo_get_repository_info":
            get_repository_info_tool = tool["func"]
            break

    assert get_repository_info_tool is not None, "get_repository_info tool not found"

    # Call the tool
    result = get_repository_info_tool()

    # Check the result
    assert isinstance(result, dict), "Expected a dictionary result"
    assert "productName" in result, "Expected productName in result"
    assert "productVersion" in result, "Expected productVersion in result"
    assert "vendorName" in result, "Expected vendorName in result"

    print(f"Repository info: {json.dumps(result, indent=2)}")


@pytest.mark.integration
def test_get_children_tool(
    nuxeo_container: Any,
    nuxeo_url: str,
    nuxeo_credentials: Tuple[str, str],
    seeded_folder_info: Dict[str, str],
) -> None:
    """Test the nuxeo_list_children tool."""
    print("\nTesting nuxeo_list_children tool...")

    username, password = nuxeo_credentials

    # Create a real NuxeoMCPServer instance with MockFastMCP
    server = NuxeoMCPServer(
        nuxeo_url=nuxeo_url,
        username=username,
        password=password,
        fastmcp_class=MockFastMCP,
    )

    # Find the nuxeo_list_children tool
    get_children_tool = None
    for tool in server.mcp.tools:
        if tool["name"] == "nuxeo_list_children":
            get_children_tool = tool["func"]
            break

    assert get_children_tool is not None, "nuxeo_list_children tool not found"

    # Call the tool with the path to the workspaces folder
    result = get_children_tool(ref="/default-domain/workspaces")

    # Check the result - now returns a string directly
    assert isinstance(result, str), "Expected a string result"
    content = result
    assert (
        "| uuid | name | title | type |" in content
    ), "Expected table header in result"

    # The result should contain the seeded folder
    assert "MCP Test Folder" in content, "Expected seeded folder in result"

    print(f"Children of /default-domain/workspaces:\n{content}")


@pytest.mark.integration
def test_search_tool(
    nuxeo_container: Any, nuxeo_url: str, nuxeo_credentials: Tuple[str, str]
) -> None:
    """Test the nuxeo_search_documents tool against a real repository."""
    print("\nTesting nuxeo_search_documents tool...")

    username, password = nuxeo_credentials

    # Create a real NuxeoMCPServer instance with MockFastMCP
    server = NuxeoMCPServer(
        nuxeo_url=nuxeo_url,
        username=username,
        password=password,
        fastmcp_class=MockFastMCP,
    )

    search_tool = None
    for tool in server.mcp.tools:
        if tool["name"] == "nuxeo_search_documents":
            search_tool = tool["func"]
            break

    assert search_tool is not None, "nuxeo_search_documents tool not found"

    result = search_tool(query="SELECT * FROM Folder", mode="nxql")

    assert result.mode == "nxql"
    assert result.interpretedQuery == "SELECT * FROM Folder"
    assert isinstance(result.totalCount, int)
    assert result.documents, "Expected at least the seeded folder"

    titles = [doc.title for doc in result.documents]
    assert any(
        isinstance(t, str) and t.startswith("MCP Test Folder") for t in titles
    ), f"Expected seeded folder in {titles}"

    # The envelope is the same for every mode, including the fields a mode
    # cannot populate.
    first = result.documents[0]
    assert first.id
    assert first.documentType
    assert first.score is None
    assert first.snippets == []

    natural = search_tool(query="all folders", mode="natural")
    assert natural.mode == "natural"
    assert natural.interpretedQuery.upper().startswith("SELECT")

    print(f"Search results for 'SELECT * FROM Folder': {titles}")


@pytest.mark.integration
def test_nuxeo_info_resource(
    nuxeo_container: Any, nuxeo_url: str, nuxeo_credentials: Tuple[str, str]
) -> None:
    """Test the nuxeo://info resource."""
    print("\nTesting nuxeo://info resource...")

    username, password = nuxeo_credentials

    # Create a real NuxeoMCPServer instance with MockFastMCP
    server = NuxeoMCPServer(
        nuxeo_url=nuxeo_url,
        username=username,
        password=password,
        fastmcp_class=MockFastMCP,
    )

    # Find the nuxeo://info resource
    get_nuxeo_info_resource = None
    for resource in server.mcp.resources:
        if resource["uri"] == "nuxeo://info":
            get_nuxeo_info_resource = resource["func"]
            break

    assert get_nuxeo_info_resource is not None, "nuxeo://info resource not found"

    # Call the resource
    result = get_nuxeo_info_resource()

    # Check the result
    assert isinstance(result, dict), "Expected a dictionary result"
    assert "url" in result, "Expected url in result"
    assert "connected" in result, "Expected connected in result"
    assert "version" in result, "Expected version in result"
    assert result["connected"] is True, "Expected connected to be True"

    print(f"Nuxeo info: {json.dumps(result, indent=2)}")


@pytest.mark.integration
def test_get_document_by_path_resource(
    nuxeo_container: Any, nuxeo_url: str, nuxeo_credentials: Tuple[str, str]
) -> None:
    """Test the nuxeo://{path*} resource."""
    print("\nTesting nuxeo://{path*} resource...")

    username, password = nuxeo_credentials

    # Create a real NuxeoMCPServer instance with MockFastMCP
    server = NuxeoMCPServer(
        nuxeo_url=nuxeo_url,
        username=username,
        password=password,
        fastmcp_class=MockFastMCP,
    )

    # Find the nuxeo://{path*} resource
    get_document_by_path_resource = None
    for resource in server.mcp.resources:
        if resource["uri"] == "nuxeo://{path*}":
            get_document_by_path_resource = resource["func"]
            break

    assert (
        get_document_by_path_resource is not None
    ), "nuxeo://{path*} resource not found"

    # Call the resource with the path to the root document
    result = get_document_by_path_resource("default-domain")

    # Check the result - now returns a string directly
    assert isinstance(result, str), "Expected a string result"
    content = result
    assert "# Document:" in content, "Expected document title in result"
    assert "**Type**: Domain" in content, "Expected document type in result"
    assert "**Path**: /default-domain" in content, "Expected document path in result"

    print(f"Document at path 'default-domain':\n{content}")


@pytest.mark.integration
def test_get_document_by_uid_resource(
    nuxeo_container: Any, nuxeo_url: str, nuxeo_credentials: Tuple[str, str]
) -> None:
    """Test the nuxeo://{uid} resource."""
    print("\nTesting nuxeo://{uid} resource...")

    username, password = nuxeo_credentials

    # Create a real Nuxeo instance to get a document UID
    nuxeo = Nuxeo(
        host=nuxeo_url,
        auth=(username, password),
    )

    # Get the root document to get its UID
    root_doc = nuxeo.documents.get(path="/")
    root_uid = root_doc.uid

    # Create a real NuxeoMCPServer instance with MockFastMCP
    server = NuxeoMCPServer(
        nuxeo_url=nuxeo_url,
        username=username,
        password=password,
        fastmcp_class=MockFastMCP,
    )

    # Find the nuxeo://{uid} resource
    get_document_by_uid_resource = None
    for resource in server.mcp.resources:
        if resource["uri"] == "nuxeo://{uid}":
            get_document_by_uid_resource = resource["func"]
            break

    assert get_document_by_uid_resource is not None, "nuxeo://{uid} resource not found"

    # Call the resource with the UID of the root document
    result = get_document_by_uid_resource(root_uid)

    # Check the result - now returns a string directly
    assert isinstance(result, str), "Expected a string result"
    content = result
    assert "# Document:" in content, "Expected document title in result"
    assert "**Type**: Root" in content, "Expected document type in result"
    assert "**Path**: /" in content, "Expected document path in result"
    assert f"**UID**: {root_uid}" in content, "Expected document UID in result"

    print(f"Document with UID '{root_uid}':\n{content}")
