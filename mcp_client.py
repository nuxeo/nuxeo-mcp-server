#!/usr/bin/env python3
"""
Nuxeo MCP Client

A command-line client for interacting with the Nuxeo MCP Server using the FastMCP client library.
"""

import argparse
import asyncio
from collections.abc import Iterable
import json
import sys
from typing import Dict, Any, Optional
from mcp.types import TextContent

from fastmcp import Client


async def search(
    url: str,
    query: str,
    mode: str = "nxql",
    page_size: int = 20,
    page_index: int = 0,
) -> str:
    """
    Search for documents using the search tool.
    
    Args:
        url: The URL of the MCP server
        query: Natural language (mode="natural") or NXQL (mode="nxql")
        mode: Query mode -- natural, nxql or semantic
        page_size: Number of results per page
        page_index: Page index
        
    Returns:
        The search results
    """
    try:
        # Ensure the URL includes the /mcp path if it's not already there
        mcp_url = url
        if not url.endswith('/mcp') and '/mcp' not in url:
            mcp_url = f"{url}/mcp"
        
        print(f"Connecting to MCP server at: {mcp_url}")
        client = Client(mcp_url)
        
        async with client:
            print("Connected successfully, calling search tool...")
            result = await client.call_tool(
                "nuxeo_search_documents",
                {
                    "query": query,
                    "mode": mode,
                    "page_size": page_size,
                    "page_index": page_index,
                },
            )
            # The tool returns one envelope for every mode, so there is nothing
            # to branch on here.
            return json.dumps(result.structured_content, indent=2)

    except Exception as e:
        print(f"Error in search: {e}")
        print(f"Error type: {type(e)}")
        raise


async def nuxeo_get_document(url: str, path: Optional[str] = None, uid: Optional[str] = None, 
                      fetch_blob: bool = False, conversion_format: Optional[str] = None, 
                      rendition: Optional[str] = None) -> Dict[str, Any]:
    """
    Get a document by path or ID.
    
    Args:
        url: The URL of the MCP server
        path: The path of the document
        uid: The UID of the document
        fetch_blob: Whether to fetch the document's blob
        conversion_format: Format to convert the document to
        rendition: Rendition to fetch
        
    Returns:
        The document
    """
    if not path and not uid:
        raise ValueError("Either path or uid must be provided")
    
    arguments = {}
    # Use ref parameter instead of path/uid
    if path:
        arguments["ref"] = path
    elif uid:
        arguments["ref"] = uid
    
    if fetch_blob:
        arguments["fetch_blob"] = fetch_blob
    if conversion_format:
        arguments["conversion_format"] = conversion_format
    if rendition:
        arguments["rendition"] = rendition
    
    try:
        # Ensure the URL includes the /mcp path if it's not already there
        mcp_url = url
        if not url.endswith('/mcp') and '/mcp' not in url:
            mcp_url = f"{url}/mcp"
        
        print(f"Connecting to MCP server at: {mcp_url}")
        client = Client(mcp_url)
        
        async with client:
            print("Connected successfully, calling nuxeo_get_document tool...")
            result = await client.call_tool("nuxeo_get_document", arguments)

            if isinstance(result, Iterable):
                for content in result:
                    if type(content) == TextContent:
                        return content.text
                    else:
                        print(f"#### Unhandled Content Type {type(content)} ")

            return result
        

    except Exception as e:
        print(f"Error in nuxeo_get_document: {e}")
        print(f"Error type: {type(e)}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Nuxeo MCP Client")
    parser.add_argument("--url", default="http://localhost:8080", help="URL of the MCP server")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search for documents")
    search_parser.add_argument("query", help="NXQL query")
    search_parser.add_argument("--page-size", type=int, default=20, help="Number of results per page")
    search_parser.add_argument("--page-index", type=int, default=0, help="Page index")
    search_parser.add_argument(
        "--mode",
        choices=["natural", "nxql", "semantic"],
        default="nxql",
        help="How the query is expressed (default: nxql)",
    )

    # Get document command
    get_doc_parser = subparsers.add_parser("get-document", help="Get a document")
    get_doc_parser.add_argument("--path", help="Path of the document")
    get_doc_parser.add_argument("--uid", help="UID of the document")
    get_doc_parser.add_argument("--fetch-blob", action="store_true", help="Fetch the document's blob")
    get_doc_parser.add_argument("--conversion-format", help="Format to convert the document to")
    get_doc_parser.add_argument("--rendition", help="Rendition to fetch")
    
    args = parser.parse_args()
    
    if args.command == "search":
        print(
            asyncio.run(
                search(
                    args.url,
                    args.query,
                    args.mode,
                    args.page_size,
                    args.page_index,
                )
            )
        )
    elif args.command == "get-document":
        result = asyncio.run(nuxeo_get_document(args.url, args.path, args.uid, args.fetch_blob, 
                                        args.conversion_format, args.rendition))
        print(result)
        
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
