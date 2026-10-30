#!/usr/bin/env python3
"""
Nuxeo MCP Server implementation.

This server provides tools, resources, and prompt templates for interacting with
a Nuxeo Content Repository Server.
"""

import argparse
import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union, cast

from fastmcp import FastMCP
from nuxeo.client import Nuxeo
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from .auth import create_auth_handler

# Import authentication modules
from .config import (
    AuthMethod,
    AuthMode,
    MCPAuthConfig,
    NuxeoServerConfig,
    OAuth2Config,
)
from .middleware import AuthenticationManager
from .prompts import register_prompts
from .resources import register_resources

# Import the tools, resources, and templates modules
from .tools import register_tools

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("nuxeo_mcp")

# Seconds to wait for Nuxeo when checking the credentials at startup
STARTUP_CHECK_TIMEOUT = 10


class NuxeoMCPServer:
    """MCP Server for Nuxeo Content Repository."""

    def __init__(
        self,
        nuxeo_url: str = "http://localhost:8080/nuxeo",
        username: Optional[str] = None,
        password: Optional[str] = None,
        fastmcp_class: Optional[Type[FastMCP]] = None,
        use_oauth2: bool = False,
        auth_config: Optional[MCPAuthConfig] = None,
        auth_mode: AuthMode = AuthMode.LOCAL,
        open_browser: bool = True,
    ):
        """
        Initialize the Nuxeo MCP Server.

        Args:
            nuxeo_url: URL of the Nuxeo server
            username: Nuxeo username (required for basic auth, no default)
            password: Nuxeo password (required for basic auth, no default)
            fastmcp_class: FastMCP class to use (for testing)
            use_oauth2: Whether to use OAuth2 authentication
            auth_config: Authentication configuration
            auth_mode: Whose identity the server uses when calling Nuxeo
            open_browser: For OAuth2, open the sign-in page in a browser; when
                False the URL is only printed, on stderr
        """
        self.nuxeo_url = nuxeo_url
        self.username = username
        self.password = password
        self.use_oauth2 = use_oauth2
        self.auth_mode = auth_mode
        self.auth_manager = AuthenticationManager()
        self.nuxeo = None

        # For basic auth, use simple direct connection (temporary fix)
        if not use_oauth2:
            # Never fall back to a default identity: a misconfigured deployment
            # must fail here rather than run as an administrator.
            if not username or not password:
                raise ValueError(
                    "Basic authentication requires NUXEO_USERNAME and "
                    "NUXEO_PASSWORD; there is no default identity"
                )
            logger.info(f"Using basic auth with URL: {nuxeo_url}, username: {username}")
            # Direct basic auth connection
            self.nuxeo = Nuxeo(
                host=nuxeo_url,
                auth=(username, password),
            )
            # Test the connection. Nuxeo refusing the credentials stops the
            # server, as no restart can fix them; a Nuxeo that cannot be
            # reached does not, as it may still be starting.
            status = None
            try:
                # Use requests directly for the auth test
                import requests

                test_response = requests.get(
                    f"{nuxeo_url}/api/v1/me",
                    auth=(username, password),
                    timeout=STARTUP_CHECK_TIMEOUT,
                )
                status = test_response.status_code
                if status == 200:
                    user_data = test_response.json()
                    logger.info(
                        f"Successfully authenticated as: {user_data.get('id', 'unknown')}"
                    )
                elif status not in (401, 403):
                    logger.error(f"Authentication failed with status: {status}")
            except Exception as e:
                logger.error(f"Failed to verify authentication: {e}")
            if status in (401, 403):
                raise ValueError(
                    f"Nuxeo rejected the credentials for user {username} "
                    f"(HTTP {status})"
                )
        else:
            # Setup OAuth2 authentication
            if auth_config:
                self.auth_config = auth_config
            else:
                # Create config from environment or parameters
                self.auth_config = MCPAuthConfig.load(auth_method=AuthMethod.OAUTH2)

            # Get server configuration; only an OAuth2 one will do here, or
            # the server would run as another identity while reporting oauth2
            server_config = self.auth_config.get_server_config()
            if not server_config or server_config.auth_method != AuthMethod.OAUTH2:
                # Create OAuth2 server config
                oauth2_config = OAuth2Config.from_env()
                if not oauth2_config:
                    raise ValueError(
                        "OAuth2 configuration required when use_oauth2=True"
                    )
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
                if self.auth_manager.authenticate(open_browser=open_browser):
                    self.nuxeo = self.auth_manager.get_nuxeo_client()
                    # Report the signed-in user, as basic auth reports its own
                    self.username = self.auth_manager.get_username()
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
            "auth_method": "oauth2" if use_oauth2 else "basic",
            "auth_mode": auth_mode.value,
        }
        add_healthcheck(self.mcp, server_info)

        # Register tools and resources without authentication wrapper for basic auth
        # (The Nuxeo client already has the auth configured)
        register_tools(self.mcp, self.nuxeo)

        # Register MCP resources.
        register_resources(self.mcp, self.nuxeo)
        # Register MCP prompts.
        register_prompts(self.mcp, self.nuxeo)

    def run(self) -> None:
        """Run the MCP server."""
        self.mcp.run()


def add_healthcheck(mcp, server_info: Optional[Dict[str, Optional[str]]] = None):
    """Add health check endpoint with server configuration info."""

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> PlainTextResponse:
        import json

        health_data: Dict[str, Optional[str]] = {
            "status": "OK",
            "server": "Nuxeo MCP Server",
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
    # --http and --sse select mutually exclusive transport modes; rejecting both
    # up front avoids one silently overriding the other (and hiding the SSE
    # deprecation warning).
    transport_group = parser.add_mutually_exclusive_group()
    transport_group.add_argument("--http", action="store_true", help="Run in HTTP mode")
    transport_group.add_argument(
        "--sse",
        action="store_true",
        help="Run in SSE mode (DEPRECATED: use --http streamable-http instead)",
    )
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
        "--no-browser",
        action="store_true",
        help="Don't open browser for OAuth2 authentication",
    )
    args = parser.parse_args()

    # Get configuration from environment variables. Credentials have no
    # default: basic auth refuses to start without them.
    nuxeo_url = os.environ.get("NUXEO_URL", "http://localhost:8080/nuxeo")
    username = os.environ.get("NUXEO_USERNAME")
    password = os.environ.get("NUXEO_PASSWORD")
    # Empty counts as unset, as for NUXEO_MCP_AUTH_MODE: a templated
    # "NUXEO_AUTH_METHOD=" means the default, not an unknown method.
    auth_method = os.environ.get("NUXEO_AUTH_METHOD", "").strip().lower() or "basic"

    if auth_method not in ("basic", "oauth2"):
        logger.error(
            f"Unsupported NUXEO_AUTH_METHOD {auth_method!r}; supported: basic, oauth2"
        )
        sys.exit(1)
    try:
        auth_mode = AuthMode.from_env()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Check if OAuth2 should be used
    use_oauth2 = args.oauth2 or auth_method == "oauth2"
    mode_source = (
        "NUXEO_MCP_AUTH_MODE"
        if os.environ.get("NUXEO_MCP_AUTH_MODE", "").strip()
        else "default"
    )

    logger.info(f"Starting Nuxeo MCP Server")
    logger.info(f"  NUXEO_URL from env: {os.environ.get('NUXEO_URL', 'NOT SET')}")
    logger.info(f"  Using URL: {nuxeo_url}")
    logger.info(f"  Auth method: {'oauth2' if use_oauth2 else 'basic'}")
    logger.info(
        f"  Auth mode: {auth_mode.value} ({mode_source}); every caller acts as "
        "the same Nuxeo identity"
    )

    # Create the server
    try:
        server = NuxeoMCPServer(
            nuxeo_url=nuxeo_url,
            username=username,
            password=password,
            use_oauth2=use_oauth2,
            auth_mode=auth_mode,
            # The OAuth2 sign-in runs while the server is created, so the flag
            # has to reach it here, not after.
            open_browser=not args.no_browser,
        )
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
        # SSE transport is deprecated in FastMCP (the sse_app helper was removed
        # in 3.x) and is expected to be dropped in a future major release.
        # streamable-http is the supported HTTP transport; --sse is retained only
        # for backward compatibility with existing clients.
        logger.warning(
            "SSE mode is deprecated and will be removed in a future release; "
            "migrate clients to --http (streamable-http)."
        )
        logger.info(f"Starting MCP server in SSE mode on {args.host}:{args.port}")
        try:
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
