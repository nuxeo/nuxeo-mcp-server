#!/usr/bin/env python3
"""
Script to call the nuxeo://info resource from the Nuxeo MCP server.

This script demonstrates how to call the nuxeo://info resource using both
HTTP and direct Python imports.
"""

import argparse
import json
import os
import requests
import sys
from typing import Dict, Any, Optional

def call_info_via_http(port: int = 8123, host: str = "localhost") -> Dict[str, Any]:
    """
    Call the nuxeo://info resource via HTTP.
    
    Args:
        port: The HTTP port of the MCP server
        host: The hostname of the MCP server
        
    Returns:
        The response from the nuxeo://info resource
    """
    url = f"http://{host}:{port}/resource/nuxeo%3A%2F%2Finfo"
    print(f"Calling {url}...")
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for 4XX/5XX responses
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling nuxeo://info via HTTP: {e}")
        return {"error": str(e)}

def call_info_via_import() -> Optional[Dict[str, Any]]:
    """
    Call the nuxeo://info resource via direct Python import.
    
    Returns:
        The response from the nuxeo://info resource, or None if an error occurs
    """
    try:
        # Import the server module
        from nuxeo_mcp.server import NuxeoMCPServer
        
        # Create a server instance; credentials have no default
        server = NuxeoMCPServer(
            nuxeo_url=os.environ.get("NUXEO_URL", "http://localhost:8080/nuxeo"),
            username=os.environ.get("NUXEO_USERNAME"),
            password=os.environ.get("NUXEO_PASSWORD"),
        )
        
        # Get the resources
        resources = server.mcp.list_resources()
        
        # Find the nuxeo://info resource
        for resource in resources:
            if resource.uri == "nuxeo://info":
                # Call the resource
                # Note: This is a simplified approach and may not work exactly like this
                # in a real implementation, as we'd need to access the actual function
                # that implements the resource
                print("Found nuxeo://info resource, but direct calling is not implemented")
                return None
        
        print("nuxeo://info resource not found")
        return None
    except ImportError:
        print("Error importing nuxeo_mcp.server. Make sure the package is installed.")
        return None
    except Exception as e:
        print(f"Error calling nuxeo://info via import: {e}")
        return None

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Call the nuxeo://info resource")
    parser.add_argument("--method", choices=["http", "import"], default="http",
                        help="Method to use for calling the resource")
    parser.add_argument("--port", type=int, default=8123,
                        help="HTTP port of the MCP server (for HTTP method)")
    parser.add_argument("--host", default="localhost",
                        help="Hostname of the MCP server (for HTTP method)")
    
    args = parser.parse_args()
    
    if args.method == "http":
        result = call_info_via_http(args.port, args.host)
    else:
        result = call_info_via_import()
        if result is None:
            print("Failed to call nuxeo://info via import")
            sys.exit(1)
    
    # Print the result
    print("\nResult from nuxeo://info resource:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
