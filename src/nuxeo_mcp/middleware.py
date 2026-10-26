"""
Authentication middleware for Nuxeo MCP.

This module provides middleware to handle authentication checks,
token refresh, and re-authentication prompts.
"""

import functools
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from nuxeo.exceptions import Unauthorized

from .auth import BasicAuthHandler, OAuth2AuthHandler
from .config import AuthMethod

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class AuthMiddleware:
    """Middleware for handling authentication in MCP requests."""

    def __init__(self, auth_handler: Any):
        """
        Initialize authentication middleware.

        Args:
            auth_handler: OAuth2AuthHandler or BasicAuthHandler instance
        """
        self.auth_handler = auth_handler
        self._authenticated = False
        self._last_auth_check = None

    def require_auth(self, func: Callable) -> Callable:
        """
        Decorator to require authentication for a function.

        Args:
            func: Function to wrap

        Returns:
            Wrapped function with authentication check
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check if we need to authenticate
            if not self._authenticated or self._should_recheck_auth():
                if not self.ensure_authenticated():
                    raise AuthenticationError("Authentication required but failed")

            try:
                # Call the original function
                return func(*args, **kwargs)
            except Unauthorized:
                # Token might be expired, try to refresh or re-authenticate
                logger.info("Received 401 Unauthorized, attempting to re-authenticate")

                # Try to refresh token if OAuth2
                if isinstance(self.auth_handler, OAuth2AuthHandler):
                    if self.auth_handler.refresh_token():
                        # Retry the function
                        return func(*args, **kwargs)

                # Full re-authentication
                self._authenticated = False
                if self.ensure_authenticated():
                    # Retry the function
                    return func(*args, **kwargs)
                else:
                    raise AuthenticationError("Re-authentication failed")

        return wrapper

    def ensure_authenticated(self) -> bool:
        """
        Ensure the user is authenticated.

        Returns:
            True if authenticated, False otherwise
        """
        if self._authenticated and not self._should_recheck_auth():
            return True

        logger.info("Attempting authentication...")

        # Try to authenticate
        if self.auth_handler.authenticate():
            self._authenticated = True
            self._last_auth_check = datetime.now()
            return True

        # Authentication failed
        self._authenticated = False
        return False

    def _should_recheck_auth(self) -> bool:
        """
        Check if we should re-verify authentication.

        Returns:
            True if we should recheck, False otherwise
        """
        if not self._last_auth_check:
            return True

        # Re-check every 30 minutes
        elapsed = (datetime.now() - self._last_auth_check).total_seconds()
        return elapsed > 1800  # 30 minutes

    def get_nuxeo_client(self):
        """
        Get authenticated Nuxeo client.

        Returns:
            Authenticated Nuxeo client or None
        """
        if self.ensure_authenticated():
            return self.auth_handler.get_nuxeo_client()
        return None

    def logout(self) -> None:
        """Logout and clear authentication state."""
        if hasattr(self.auth_handler, "logout"):
            self.auth_handler.logout()
        self._authenticated = False
        self._last_auth_check = None
        logger.info("Logged out successfully")

    def wrap_tool(self, tool_func: Callable) -> Callable:
        """
        Wrap an MCP tool function with authentication.

        Args:
            tool_func: Tool function to wrap

        Returns:
            Wrapped function with authentication
        """

        @functools.wraps(tool_func)
        async def async_wrapper(*args, **kwargs):
            # Ensure authenticated before tool execution
            if not self.ensure_authenticated():
                return {
                    "error": "Authentication required. Please authenticate first.",
                    "auth_required": True,
                }

            try:
                # Execute the tool
                result = await tool_func(*args, **kwargs)
                return result
            except Unauthorized:
                # Try to refresh/re-authenticate
                logger.info("Tool received 401, attempting re-authentication")

                if isinstance(self.auth_handler, OAuth2AuthHandler):
                    if self.auth_handler.refresh_token():
                        # Retry the tool
                        return await tool_func(*args, **kwargs)

                # Full re-authentication
                self._authenticated = False
                if self.ensure_authenticated():
                    # Retry the tool
                    return await tool_func(*args, **kwargs)
                else:
                    return {
                        "error": "Authentication failed. Please check your credentials.",
                        "auth_required": True,
                    }
            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                return {"error": str(e)}

        @functools.wraps(tool_func)
        def sync_wrapper(*args, **kwargs):
            # Ensure authenticated before tool execution
            if not self.ensure_authenticated():
                return {
                    "error": "Authentication required. Please authenticate first.",
                    "auth_required": True,
                }

            try:
                # Execute the tool
                result = tool_func(*args, **kwargs)
                return result
            except Unauthorized:
                # Try to refresh/re-authenticate
                logger.info("Tool received 401, attempting re-authentication")

                if isinstance(self.auth_handler, OAuth2AuthHandler):
                    if self.auth_handler.refresh_token():
                        # Retry the tool
                        return tool_func(*args, **kwargs)

                # Full re-authentication
                self._authenticated = False
                if self.ensure_authenticated():
                    # Retry the tool
                    return tool_func(*args, **kwargs)
                else:
                    return {
                        "error": "Authentication failed. Please check your credentials.",
                        "auth_required": True,
                    }
            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                return {"error": str(e)}

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(tool_func):
            return async_wrapper
        else:
            return sync_wrapper


class AuthenticationManager:
    """Manages authentication for the MCP server."""

    def __init__(self):
        """Initialize authentication manager."""
        self.middleware: Optional[AuthMiddleware] = None
        self.auth_handler: Optional[Any] = None

    def setup(self, server_config) -> bool:
        """
        Setup authentication based on server configuration.

        Args:
            server_config: NuxeoServerConfig instance

        Returns:
            True if setup successful, False otherwise
        """
        try:
            # Create appropriate auth handler
            if server_config.auth_method == AuthMethod.OAUTH2:
                self.auth_handler = OAuth2AuthHandler(server_config)
            elif server_config.auth_method == AuthMethod.BASIC:
                self.auth_handler = BasicAuthHandler(server_config)
            else:
                logger.error(f"Unsupported auth method: {server_config.auth_method}")
                return False

            # Create middleware
            self.middleware = AuthMiddleware(self.auth_handler)

            return True

        except Exception as e:
            logger.error(f"Failed to setup authentication: {e}")
            return False

    def authenticate(self) -> bool:
        """
        Perform authentication.

        Returns:
            True if authenticated, False otherwise
        """
        if not self.middleware:
            logger.error("Authentication not setup")
            return False

        return self.middleware.ensure_authenticated()

    def get_nuxeo_client(self):
        """
        Get authenticated Nuxeo client.

        Returns:
            Nuxeo client or None
        """
        if not self.middleware:
            return None

        return self.middleware.get_nuxeo_client()

    def wrap_tools(self, tools: dict) -> dict:
        """
        Wrap all tools with authentication middleware.

        Args:
            tools: Dictionary of tool functions

        Returns:
            Dictionary of wrapped tool functions
        """
        if not self.middleware:
            return tools

        wrapped_tools = {}
        for name, tool_func in tools.items():
            wrapped_tools[name] = self.middleware.wrap_tool(tool_func)

        return wrapped_tools
