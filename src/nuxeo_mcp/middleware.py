"""
Authentication middleware for Nuxeo MCP.

This module provides middleware to handle authentication checks,
token refresh, and re-authentication prompts.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from .auth import BasicAuthHandler, OAuth2AuthHandler
from .config import AuthMethod

logger = logging.getLogger(__name__)


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

    def get_username(self) -> Optional[str]:
        """Return the Nuxeo user the handler authenticated as, if known."""
        return getattr(self.auth_handler, "username", None)

    def get_nuxeo_client(self):
        """
        Get authenticated Nuxeo client.

        Returns:
            Nuxeo client or None
        """
        if not self.middleware:
            return None

        return self.middleware.get_nuxeo_client()
