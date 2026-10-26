"""
Integration tests for OAuth2 authentication flow.

These tests require a running Nuxeo instance with OAuth2 configured.
They are marked with pytest.mark.integration and can be skipped with:
    pytest -m "not integration"
"""

import os
import tempfile
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from nuxeo_mcp.auth import OAuth2AuthHandler, OAuth2CallbackHandler
from nuxeo_mcp.config import AuthMethod, MCPAuthConfig, NuxeoServerConfig, OAuth2Config
from nuxeo_mcp.server import NuxeoMCPServer
from nuxeo_mcp.token_store import EncryptedFileStorage, TokenManager


@pytest.mark.integration
class TestOAuth2Integration:
    """Integration tests for OAuth2 authentication."""

    @pytest.fixture
    def oauth2_config(self):
        """Create OAuth2 configuration from environment."""
        # Skip if OAuth2 not configured
        if not os.environ.get("NUXEO_OAUTH_CLIENT_ID"):
            pytest.skip("OAuth2 not configured in environment")

        return OAuth2Config(
            client_id=os.environ["NUXEO_OAUTH_CLIENT_ID"],
            client_secret=os.environ["NUXEO_OAUTH_CLIENT_SECRET"],
            redirect_port=8888,
        )

    @pytest.fixture
    def server_config(self, oauth2_config):
        """Create server configuration with OAuth2."""
        return NuxeoServerConfig(
            url=os.environ.get("NUXEO_URL", "http://localhost:8080/nuxeo"),
            auth_method=AuthMethod.OAUTH2,
            oauth2_config=oauth2_config,
        )

    def test_oauth2_callback_server(self):
        """Test OAuth2 callback server handling."""
        # Start callback server
        server = HTTPServer(("localhost", 0), OAuth2CallbackHandler)
        # Initialize required attributes
        server.auth_code = None
        server.state = None
        server.auth_error = None
        port = server.server_address[1]

        # Start server in thread
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        # Simulate successful callback
        import requests

        response = requests.get(
            f"http://localhost:{port}/callback",
            params={"code": "test-code", "state": "test-state"},
        )

        assert response.status_code == 200
        assert "Authentication Successful" in response.text
        assert server.auth_code == "test-code"
        assert server.state == "test-state"

        server.shutdown()

    def test_oauth2_error_callback(self):
        """Test OAuth2 callback server error handling."""
        # Start callback server
        server = HTTPServer(("localhost", 0), OAuth2CallbackHandler)
        # Initialize required attributes
        server.auth_code = None
        server.state = None
        server.auth_error = None
        port = server.server_address[1]

        # Start server in thread
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        # Simulate error callback
        import requests

        response = requests.get(
            f"http://localhost:{port}/callback",
            params={
                "error": "access_denied",
                "error_description": "User denied access",
            },
        )

        assert response.status_code == 400
        assert "Authentication Failed" in response.text
        assert server.auth_error == "access_denied"

        server.shutdown()

    @patch("webbrowser.open")
    @patch("nuxeo_mcp.auth.OAuth2")
    @patch("nuxeo_mcp.auth.secrets.token_urlsafe")
    def test_oauth2_auth_flow_simulation(
        self, mock_token_urlsafe, mock_oauth2_class, mock_browser_open
    ):
        """Test simulated OAuth2 authentication flow."""
        # Mock the state generation to return a known value
        mock_token_urlsafe.return_value = "test-state"

        # Setup mocks
        mock_oauth2 = MagicMock()
        mock_oauth2.create_authorization_url.return_value = (
            "http://test.com/authorize",
            "test-state",
            "test-verifier",
        )
        mock_oauth2.request_token.return_value = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "expires_in": 3600,
        }
        mock_oauth2_class.return_value = mock_oauth2

        # Mock Nuxeo client
        with patch("nuxeo_mcp.auth.Nuxeo") as mock_nuxeo_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "testuser"}
            mock_client.client.request.return_value = mock_response
            mock_client.client.auth = mock_oauth2
            mock_nuxeo_class.return_value = mock_client

            # Create handler with temp token storage
            with tempfile.TemporaryDirectory() as tmpdir:
                token_manager = TokenManager(backend="encrypted_file")
                token_manager.storage = EncryptedFileStorage(Path(tmpdir))

                oauth2_config = OAuth2Config(
                    client_id="test-client",
                    client_secret="test-secret",
                )
                server_config = NuxeoServerConfig(
                    url="http://test.com",
                    auth_method=AuthMethod.OAUTH2,
                    oauth2_config=oauth2_config,
                )

                handler = OAuth2AuthHandler(server_config, token_manager)

                # Simulate successful authentication
                with patch.object(handler, "_start_callback_server") as mock_callback:
                    # Setup mock callback server
                    mock_server = MagicMock()
                    mock_server.auth_code = "test-auth-code"
                    mock_server.state = "test-state"
                    mock_server.auth_error = None
                    mock_callback.return_value = mock_server

                    # Mock state validation
                    with patch.object(handler, "_generate_pkce_challenge") as mock_pkce:
                        mock_pkce.return_value = ("verifier", "challenge")

                        result = handler.authenticate(open_browser=True)

                        assert result is True
                        mock_browser_open.assert_called_once()

                        # Check token was stored
                        stored_token = token_manager.get_token("http://test.com")
                        assert stored_token is not None
                        assert stored_token["access_token"] == "test-access-token"

    def test_token_refresh_simulation(self):
        """Test token refresh mechanism."""
        # Use in-memory backend
        token_manager = TokenManager(backend="memory")

        # Store initial token
        initial_token = {
            "access_token": "old-access-token",
            "refresh_token": "refresh-token",
            "expires_at": time.time() - 100,  # Expired
        }

        # Setup handler
        oauth2_config = OAuth2Config(
            client_id="test-client",
            client_secret="test-secret",
        )
        server_config = NuxeoServerConfig(
            url="http://test.com",
            auth_method=AuthMethod.OAUTH2,
            oauth2_config=oauth2_config,
        )

        # Setup mocks before creating handler
        with patch("nuxeo_mcp.auth.OAuth2") as mock_oauth2_class:
            mock_oauth2 = MagicMock()
            mock_oauth2.refresh_token.return_value = {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 3600,
            }
            mock_oauth2_class.return_value = mock_oauth2

            with patch("nuxeo_mcp.auth.Nuxeo") as mock_nuxeo_class:
                mock_client = MagicMock()
                mock_client.client.auth = mock_oauth2
                mock_nuxeo_class.return_value = mock_client

                handler = OAuth2AuthHandler(server_config, token_manager)

                # Mock the token manager's get_token to return our initial token
                with patch.object(
                    token_manager, "get_token", return_value=initial_token
                ):
                    with patch.object(token_manager, "store_token") as mock_store:
                        # Trigger refresh
                        result = handler.refresh_token()

                        assert result is True

                        # Verify refresh_token was called with the correct token
                        mock_oauth2.refresh_token.assert_called_once_with(
                            refresh_token="refresh-token"
                        )

                        # Verify the new token was stored
                        assert mock_store.called
                        stored_url, stored_token = mock_store.call_args[0]
                        assert stored_url == "http://test.com"
                        assert stored_token["access_token"] == "new-access-token"


@pytest.mark.integration
class TestMCPServerWithOAuth2:
    """Test MCP server with OAuth2 authentication."""

    @patch("nuxeo_mcp.server.AuthenticationManager")
    @patch("nuxeo_mcp.server.MCPAuthConfig")
    def test_server_initialization_with_oauth2(
        self, mock_config_class, mock_auth_manager_class
    ):
        """Test initializing MCP server with OAuth2."""
        # Setup mocks
        mock_config = MagicMock()
        mock_server_config = MagicMock()
        mock_server_config.auth_method = AuthMethod.OAUTH2
        mock_config.get_server_config.return_value = mock_server_config
        mock_config_class.load.return_value = mock_config

        mock_auth_manager = MagicMock()
        mock_auth_manager.setup.return_value = True
        mock_auth_manager.authenticate.return_value = True
        mock_auth_manager.get_nuxeo_client.return_value = MagicMock()
        mock_auth_manager.middleware = MagicMock()
        mock_auth_manager_class.return_value = mock_auth_manager

        # Create server with OAuth2
        server = NuxeoMCPServer(
            nuxeo_url="http://test.com",
            use_oauth2=True,
        )

        assert server.use_oauth2 is True
        assert server.auth_manager is not None
        mock_auth_manager.setup.assert_called_once()
        mock_auth_manager.authenticate.assert_called_once()

    def test_server_fallback_to_basic_auth(self):
        """Test server fallback to basic auth when OAuth2 not configured."""
        with patch("nuxeo_mcp.server.Nuxeo") as mock_nuxeo_class:
            mock_client = MagicMock()
            mock_nuxeo_class.return_value = mock_client

            # Clear OAuth2 environment variables
            with patch.dict(os.environ, {}, clear=True):
                server = NuxeoMCPServer(
                    nuxeo_url="http://test.com",
                    username="admin",
                    password="admin",
                    use_oauth2=False,
                )

                assert server.use_oauth2 is False
                assert server.nuxeo is not None
                mock_nuxeo_class.assert_called_with(
                    host="http://test.com",
                    auth=("admin", "admin"),
                )


@pytest.mark.integration
class TestEndToEndOAuth2:
    """End-to-end OAuth2 tests (requires real Nuxeo with OAuth2)."""

    @pytest.mark.skipif(
        not os.environ.get("NUXEO_OAUTH_CLIENT_ID"),
        reason="OAuth2 credentials not configured",
    )
    def test_real_oauth2_flow(self):
        """Test real OAuth2 flow with actual Nuxeo server."""
        # This test requires manual interaction for browser authentication
        # It's meant to be run manually during development
        pytest.skip("Manual test - requires browser interaction")

        # Uncomment to run manually:
        # oauth2_config = OAuth2Config.from_env()
        # server_config = NuxeoServerConfig(
        #     url=os.environ["NUXEO_URL"],
        #     auth_method=AuthMethod.OAUTH2,
        #     oauth2_config=oauth2_config,
        # )
        #
        # handler = OAuth2AuthHandler(server_config)
        # result = handler.authenticate()
        #
        # assert result is True
        # assert handler.get_nuxeo_client() is not None
