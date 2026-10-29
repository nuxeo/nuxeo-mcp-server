"""
OAuth2 authentication handler for Nuxeo MCP.

This module implements the OAuth2 authorization code flow with PKCE,
including browser-based authentication and token management.
"""

import base64
import hashlib
import logging
import secrets
import socket
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import aiohttp
from nuxeo.auth import OAuth2
from nuxeo.client import Nuxeo
from nuxeo.exceptions import Forbidden, Unauthorized

from .config import AuthMethod, NuxeoServerConfig
from .token_store import TokenManager

logger = logging.getLogger(__name__)


class OAuth2CallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth2 callback."""

    def log_message(self, format, *args):
        """Override to suppress default HTTP server logs."""
        pass

    def do_GET(self):
        """Handle GET request for OAuth2 callback."""
        query_components = parse_qs(urlparse(self.path).query)

        if "code" in query_components:
            self.server.auth_code = query_components["code"][0]
            self.server.state = query_components.get("state", [None])[0]

            # Send success response
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            success_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authentication Successful</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    .success-icon {
                        font-size: 48px;
                        color: #10b981;
                        margin-bottom: 20px;
                    }
                    h1 {
                        color: #1f2937;
                        margin-bottom: 10px;
                    }
                    p {
                        color: #6b7280;
                        margin-bottom: 20px;
                    }
                    .close-hint {
                        font-size: 14px;
                        color: #9ca3af;
                    }
                </style>
                <script>
                    setTimeout(function() {
                        window.close();
                    }, 3000);
                </script>
            </head>
            <body>
                <div class="container">
                    <div class="success-icon">✓</div>
                    <h1>Authentication Successful!</h1>
                    <p>You have been successfully authenticated with Nuxeo.</p>
                    <p class="close-hint">This window will close automatically...</p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode())

        elif "error" in query_components:
            self.server.auth_error = query_components["error"][0]
            error_description = query_components.get(
                "error_description", ["Unknown error"]
            )[0]

            # Send error response
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authentication Failed</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #f87171 0%, #ef4444 100%);
                    }}
                    .container {{
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }}
                    .error-icon {{
                        font-size: 48px;
                        color: #ef4444;
                        margin-bottom: 20px;
                    }}
                    h1 {{
                        color: #1f2937;
                        margin-bottom: 10px;
                    }}
                    p {{
                        color: #6b7280;
                        margin-bottom: 20px;
                    }}
                    .error-details {{
                        background: #fef2f2;
                        padding: 10px;
                        border-radius: 5px;
                        color: #991b1b;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="error-icon">✗</div>
                    <h1>Authentication Failed</h1>
                    <p>There was an error during authentication.</p>
                    <div class="error-details">{error_description}</div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())
        else:
            self.send_response(404)
            self.end_headers()


class OAuth2AuthHandler:
    """Handles OAuth2 authentication flow for Nuxeo."""

    def __init__(
        self,
        server_config: NuxeoServerConfig,
        token_manager: Optional[TokenManager] = None,
    ):
        """
        Initialize OAuth2 authentication handler.

        Args:
            server_config: Nuxeo server configuration
            token_manager: Token storage manager
        """
        self.server_config = server_config
        self.token_manager = token_manager or TokenManager()
        self.oauth2_config = server_config.oauth2_config
        self.nuxeo_client: Optional[Nuxeo] = None
        # The Nuxeo user the token belongs to, as /api/v1/me reports it
        self.username: Optional[str] = None

        if not self.oauth2_config:
            raise ValueError("OAuth2 configuration required")

    def _find_available_port(
        self, start_port: int = 8080, max_attempts: int = 100
    ) -> int:
        """Find an available port for the callback server."""
        for port in range(start_port, start_port + max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("localhost", port))
                    return port
            except OSError:
                continue
        raise RuntimeError(
            f"Could not find available port in range {start_port}-{start_port + max_attempts}"
        )

    def _start_callback_server(self, port: int) -> HTTPServer:
        """Start the OAuth2 callback server."""
        server = HTTPServer(("localhost", port), OAuth2CallbackHandler)
        server.auth_code = None
        server.auth_error = None
        server.state = None

        # Start server in a separate thread
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        return server

    def authenticate(self, open_browser: bool = True) -> bool:
        """
        Perform OAuth2 authentication flow.

        Args:
            open_browser: Whether to automatically open the browser

        Returns:
            True if authentication successful, False otherwise
        """
        callback_server: Optional[HTTPServer] = None
        try:
            # Check for existing valid token
            existing_token = self.token_manager.get_token(self.server_config.url)
            if existing_token and not self._is_token_expired(existing_token):
                self._setup_nuxeo_client(existing_token)
                if not self._stored_token_rejected(self.nuxeo_client):
                    logger.info("Using existing valid token")
                    return True
                logger.info("Stored token was rejected; signing in again")

            # Find available port for callback
            redirect_port = (
                self.oauth2_config.redirect_port or self._find_available_port()
            )
            redirect_uri = f"http://localhost:{redirect_port}/callback"

            # Start callback server
            callback_server = self._start_callback_server(redirect_port)

            # Generate state for CSRF protection
            state = secrets.token_urlsafe(32)

            # Create Nuxeo client with OAuth2
            self.nuxeo_client = Nuxeo(host=self.server_config.url)
            oauth2_auth = OAuth2(
                self.server_config.url,
                client_id=self.oauth2_config.client_id,
                client_secret=self.oauth2_config.client_secret,
                redirect_uri=redirect_uri,
                authorization_endpoint=self.oauth2_config.authorization_endpoint,
                token_endpoint=self.oauth2_config.token_endpoint,
                openid_configuration_url=self.oauth2_config.openid_configuration_url,
            )
            self.nuxeo_client.client.auth = oauth2_auth

            # The Nuxeo client generates the PKCE pair itself and returns the
            # verifier; passing our own challenge as well is a duplicate keyword.
            auth_url, _, code_verifier = oauth2_auth.create_authorization_url(
                state=state
            )

            logger.info(f"Authorization URL: {auth_url}")

            if open_browser:
                # Open browser for authentication
                webbrowser.open(auth_url)
                print("\n🔐 Opening browser for authentication...")
                print(f"If the browser doesn't open, please visit:\n{auth_url}\n")
            else:
                print(
                    f"\n🔐 Please visit the following URL to authenticate:\n{auth_url}\n"
                )

            # Wait for callback (timeout after 5 minutes)
            timeout = 300  # 5 minutes
            start_time = time.time()

            while time.time() - start_time < timeout:
                if callback_server.auth_code:
                    # Validate state
                    if callback_server.state != state:
                        logger.error("State mismatch - possible CSRF attack")
                        return False

                    # Exchange code for token
                    token = oauth2_auth.request_token(
                        authorization_response=f"{redirect_uri}?code={callback_server.auth_code}&state={state}",
                        code_verifier=code_verifier,
                    )

                    # Store token
                    self.token_manager.store_token(self.server_config.url, token)

                    # Validate token by making a test request
                    if self._validate_token(token):
                        logger.info("Authentication successful")
                        print("✅ Authentication successful!")
                        return True
                    else:
                        logger.error("Token validation failed")
                        print("❌ Token validation failed")
                        return False

                elif callback_server.auth_error:
                    logger.error(f"Authentication error: {callback_server.auth_error}")
                    print(f"❌ Authentication failed: {callback_server.auth_error}")
                    return False

                time.sleep(0.5)

            # Timeout
            logger.error("Authentication timeout")
            print("❌ Authentication timeout - no response received")
            return False

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            print(f"❌ Authentication failed: {e}")
            return False
        finally:
            # Every way out, including an exception mid-flow: shutdown() alone
            # stops serving but keeps the port bound.
            if callback_server is not None:
                callback_server.shutdown()
                callback_server.server_close()

    def _setup_nuxeo_client(self, token: Dict[str, Any]) -> None:
        """Setup Nuxeo client with OAuth2 token."""
        self.nuxeo_client = Nuxeo(host=self.server_config.url)
        oauth2_auth = OAuth2(
            self.server_config.url,
            client_id=self.oauth2_config.client_id,
            client_secret=self.oauth2_config.client_secret,
            token=token,
        )
        self.nuxeo_client.client.auth = oauth2_auth

    def _is_token_expired(self, token: Dict[str, Any]) -> bool:
        """Check if token is expired."""
        expires_at = token.get("expires_at")
        if not expires_at:
            return False
        return datetime.now().timestamp() >= expires_at - 60  # 60 second buffer

    def _stored_token_rejected(self, client: Nuxeo) -> bool:
        """Check a stored token with Nuxeo, learning its user when it is accepted.

        Only a 401 or 403 is a rejection. When Nuxeo cannot be reached the
        token is kept, as it was before this check existed, and the user stays
        unknown.
        """
        try:
            response = client.client.request("GET", "/api/v1/me")
        except (Unauthorized, Forbidden):
            return True
        except Exception as e:
            logger.warning(f"Could not check the stored token with Nuxeo: {e}")
            return False
        if response.status_code == 200:
            self.username = response.json().get("id")
            logger.info(f"Authenticated as user: {self.username or 'unknown'}")
        return False

    def _validate_token(self, token: Dict[str, Any]) -> bool:
        """Validate token by making a test API request."""
        try:
            # Try to get current user info
            response = self.nuxeo_client.client.request("GET", "/api/v1/me")
            if response.status_code == 200:
                user_info = response.json()
                self.username = user_info.get("id")
                logger.info(f"Authenticated as user: {self.username or 'unknown'}")
                return True
            return False
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return False

    def refresh_token(self) -> bool:
        """
        Refresh the OAuth2 token.

        Returns:
            True if refresh successful, False otherwise
        """
        try:
            current_token = self.token_manager.get_token(self.server_config.url)
            if not current_token or not current_token.get("refresh_token"):
                logger.warning("No refresh token available")
                return False

            # Setup client with current token
            self._setup_nuxeo_client(current_token)

            # Refresh the token
            new_token = self.nuxeo_client.client.auth.refresh_token(
                refresh_token=current_token["refresh_token"]
            )

            # Store new token
            self.token_manager.store_token(self.server_config.url, new_token)

            # Update client with new token
            self._setup_nuxeo_client(new_token)

            logger.info("Token refreshed successfully")
            return True

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return False

    def get_nuxeo_client(self) -> Optional[Nuxeo]:
        """Get authenticated Nuxeo client."""
        if not self.nuxeo_client:
            # Try to authenticate
            if not self.authenticate():
                return None

        # Check if token needs refresh
        token = self.token_manager.get_token(self.server_config.url)
        if token and self._is_token_expired(token):
            if not self.refresh_token():
                # Refresh failed, try full authentication
                if not self.authenticate():
                    return None

        return self.nuxeo_client

    def logout(self) -> None:
        """Clear stored tokens and logout."""
        self.token_manager.delete_token(self.server_config.url)
        self.nuxeo_client = None
        logger.info("Logged out successfully")


class BasicAuthHandler:
    """Handles basic authentication for Nuxeo."""

    def __init__(self, server_config: NuxeoServerConfig):
        """Initialize basic auth handler."""
        self.server_config = server_config
        self.nuxeo_client: Optional[Nuxeo] = None

    def authenticate(self) -> bool:
        """Authenticate using basic auth."""
        try:
            self.nuxeo_client = Nuxeo(
                host=self.server_config.url,
                auth=(self.server_config.username, self.server_config.password),
            )

            # Validate credentials - use /api/v1/me endpoint which works on this server
            response = self.nuxeo_client.client.request("GET", "/api/v1/me")
            if response.status_code == 200:
                user_info = response.json()
                logger.info(f"Authenticated as user: {user_info.get('id', 'unknown')}")
                return True
            return False

        except Exception as e:
            logger.error(f"Basic authentication failed: {e}")
            return False

    def get_nuxeo_client(self) -> Optional[Nuxeo]:
        """Get authenticated Nuxeo client."""
        if not self.nuxeo_client:
            self.authenticate()
        return self.nuxeo_client


def create_auth_handler(server_config: NuxeoServerConfig) -> Any:
    """
    Create appropriate authentication handler based on config.

    Args:
        server_config: Server configuration

    Returns:
        Authentication handler instance
    """
    if server_config.auth_method == AuthMethod.OAUTH2:
        return OAuth2AuthHandler(server_config)
    elif server_config.auth_method == AuthMethod.BASIC:
        return BasicAuthHandler(server_config)
    else:
        raise ValueError(f"Unsupported auth method: {server_config.auth_method}")
