#!/usr/bin/env python3
"""
Nuxeo MCP Server implementation.

This server provides tools, resources, and prompt templates for interacting with
a Nuxeo Content Repository Server.
"""

import os
import logging
import argparse
import sys
from typing import Any, Dict, List, Optional, Type, Callable, TypeVar, Union, cast

from fastmcp import FastMCP
from nuxeo.client import Nuxeo

# Import the tools, resources, and templates modules
from .tools import register_tools
from .resources import register_resources
from .prompts import register_prompts
from starlette.requests import Request
from starlette.responses import PlainTextResponse

# Import authentication modules
from .config import MCPAuthConfig, NuxeoServerConfig, AuthMethod, OAuth2Config
from .auth import create_auth_handler
from .middleware import AuthenticationManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("nuxeo_mcp")


class NuxeoMCPServer:
    """MCP Server for Nuxeo Content Repository."""

    def __init__(
        self,
        nuxeo_url: str = "http://localhost:8080/nuxeo",
        username: str = "Administrator",
        password: str = "Administrator",
        fastmcp_class: Optional[Type[FastMCP]] = None,
        use_oauth2: bool = False,
        auth_config: Optional[MCPAuthConfig] = None,
    ):
        """
        Initialize the Nuxeo MCP Server.

        Args:
            nuxeo_url: URL of the Nuxeo server
            username: Nuxeo username (for basic auth)
            password: Nuxeo password (for basic auth)
            fastmcp_class: FastMCP class to use (for testing)
            use_oauth2: Whether to use OAuth2 authentication
            auth_config: Authentication configuration
        """
        self.nuxeo_url = nuxeo_url
        self.username = username
        self.password = password
        self.use_oauth2 = use_oauth2
        self.auth_manager = AuthenticationManager()
        self.nuxeo = None
        
        # For basic auth, use simple direct connection (temporary fix)
        if not use_oauth2:
            logger.info(f"Using basic auth with URL: {nuxeo_url}, username: {username}")
            # Direct basic auth connection
            self.nuxeo = Nuxeo(
                host=nuxeo_url,
                auth=(username, password),
            )
            # Test the connection
            try:
                # Use requests directly for the auth test
                import requests
                test_response = requests.get(f'{nuxeo_url}/api/v1/me', auth=(username, password))
                if test_response.status_code == 200:
                    user_data = test_response.json()
                    logger.info(f"Successfully authenticated as: {user_data.get('id', 'unknown')}")
                else:
                    logger.error(f"Authentication failed with status: {test_response.status_code}")
            except Exception as e:
                logger.error(f"Failed to verify authentication: {e}")
        else:
            # Setup OAuth2 authentication
            if auth_config:
                self.auth_config = auth_config
            else:
                # Create config from environment or parameters
                self.auth_config = MCPAuthConfig.load()
                
            # Get server configuration
            server_config = self.auth_config.get_server_config()
            if not server_config:
                # Create OAuth2 server config
                oauth2_config = OAuth2Config.from_env()
                if not oauth2_config:
                    raise ValueError("OAuth2 configuration required when use_oauth2=True")
                server_config = NuxeoServerConfig(
                    url=nuxeo_url,
                    auth_method=AuthMethod.OAUTH2,
                    oauth2_config=oauth2_config,
                )
                self.auth_config.add_server("default", server_config)
            
            # Setup authentication manager for OAuth2
            if not self.auth_manager.setup(server_config):
                logger.error("Failed to setup OAuth2 authentication")
                raise ValueError("OAuth2 setup failed")
            else:
                # Authenticate and get Nuxeo client
                if self.auth_manager.authenticate():
                    self.nuxeo = self.auth_manager.get_nuxeo_client()
                else:
                    logger.warning("Initial OAuth2 authentication failed")
                    raise ValueError("OAuth2 authentication failed")

        # Initialize the MCP server
        FastMCPClass = fastmcp_class or FastMCP
        self.mcp = FastMCPClass(
            name="nuxeo-mcp-server",
        )

        # Add healthcheck with server configuration info
        server_info = {
            "nuxeo_url": self.nuxeo_url,
            "username": self.username,
            "auth_method": "oauth2" if use_oauth2 else "basic"
        }
        add_healthcheck(self.mcp, server_info)
        
        # Register tools and resources without authentication wrapper for basic auth
        # (The Nuxeo client already has the auth configured)
        # Skip server selection if explicitly configured (e.g., in Docker with pre-configured URL)
        skip_server_selection = os.environ.get("SKIP_SERVER_SELECTION", "false").lower() in ("true", "1", "yes")
        register_tools(self.mcp, self.nuxeo, skip_server_selection=skip_server_selection)
            
        # Register MCP resources.
        register_resources(self.mcp, self.nuxeo)
        # Register MCP prompts.
        register_prompts(self.mcp, self.nuxeo)

    def run(self) -> None:
        """Run the MCP server."""
        self.mcp.run()


def add_healthcheck(mcp, server_info: Dict[str, str] = None):
    """Add health check endpoint with server configuration info."""
    
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> PlainTextResponse:
        import json
        health_data = {
            "status": "OK",
            "server": "Nuxeo MCP Server"
        }
        
        # Add server configuration info if available
        if server_info:
            health_data.update(server_info)
        
        # Return as JSON for easier parsing
        from starlette.responses import JSONResponse
        return JSONResponse(health_data)


def main() -> None:
    """Run the Nuxeo MCP server."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Nuxeo MCP Server")
    parser.add_argument("--http", action="store_true", help="Run in HTTP mode")
    parser.add_argument("--sse", action="store_true", help="Run in SSE mode")
    parser.add_argument(
        "--port", type=int, default=8080, help="HTTP port (default: 8080)"
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0", help="HTTP host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--oauth2", action="store_true", help="Use OAuth2 authentication"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't open browser for OAuth2 authentication"
    )
    args = parser.parse_args()

    # Get configuration from environment variables
    # Use the hardcoded defaults if not provided
    nuxeo_url = os.environ.get("NUXEO_URL", "http://localhost:8080/nuxeo")
    username = os.environ.get("NUXEO_USERNAME", "Administrator")
    password = os.environ.get("NUXEO_PASSWORD", "Administrator")
    auth_method = os.environ.get("NUXEO_AUTH_METHOD", "basic").lower()
    
    logger.info(f"Starting Nuxeo MCP Server")
    logger.info(f"  NUXEO_URL from env: {os.environ.get('NUXEO_URL', 'NOT SET')}")
    logger.info(f"  Using URL: {nuxeo_url}")
    logger.info(f"  Using username: {username}")
    logger.info(f"  Auth method: {auth_method}")
    
    # Check if OAuth2 should be used
    use_oauth2 = args.oauth2 or auth_method == "oauth2"

    # Create the server
    try:
        server = NuxeoMCPServer(
            nuxeo_url=nuxeo_url,
            username=username,
            password=password,
            use_oauth2=use_oauth2,
        )
        
        # If OAuth2 and browser auth is enabled, perform initial authentication
        if use_oauth2 and not args.no_browser:
            logger.info("Starting OAuth2 authentication flow...")
            if not server.auth_manager.authenticate():
                logger.error("OAuth2 authentication failed")
                sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to create server: {e}")
        sys.exit(1)

    # Run the server in the appropriate mode
    if args.http:
        logger.info(f"Starting MCP server in HTTP mode on {args.host}:{args.port}")
        try:
            # Run the server with streamable-http transport
            server.mcp.run(
                transport="streamable-http",
                host=args.host,
                port=args.port,
            )
        except Exception as e:
            logger.error(f"Error starting HTTP server: {e}")
            logger.error(
                "Please check the FastMCP documentation for HTTP mode instructions."
            )
            sys.exit(1)

    elif args.sse:
        logger.info(f"Starting MCP server in SSE mode on {args.host}:{args.port}")
        try:
            # Run the server with streamable-http transport
            server.mcp.run(
                transport="sse",
                host=args.host,
                port=args.port,
            )
        except Exception as e:
            logger.error(f"Error starting HTTP server: {e}")
            logger.error(
                "Please check the FastMCP documentation for HTTP mode instructions."
            )
            sys.exit(1)
    else:
        logger.info("Starting MCP server in stdio mode")
        server.run()


if __name__ == "__main__":
    main()
