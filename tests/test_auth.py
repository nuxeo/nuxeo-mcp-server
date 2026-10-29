"""
Unit tests for authentication components.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest
import requests
from nuxeo.exceptions import Forbidden, Unauthorized

from nuxeo_mcp.auth import BasicAuthHandler, OAuth2AuthHandler
from nuxeo_mcp.config import (
    AuthMethod,
    AuthMode,
    MCPAuthConfig,
    NuxeoServerConfig,
    OAuth2Config,
)
from nuxeo_mcp.middleware import AuthenticationManager, AuthMiddleware
from nuxeo_mcp.token_store import EncryptedFileStorage, OAuth2Token, TokenManager


class TestOAuth2Config:
    """Test OAuth2 configuration."""

    def test_oauth2_config_from_env(self):
        """Test creating OAuth2Config from environment variables."""
        with patch.dict(
            os.environ,
            {
                "NUXEO_OAUTH_CLIENT_ID": "test-client-id",
                "NUXEO_OAUTH_CLIENT_SECRET": "test-secret",
                "NUXEO_OAUTH_REDIRECT_PORT": "8888",
                "NUXEO_OAUTH_SCOPE": "custom scope",
            },
        ):
            config = OAuth2Config.from_env()
            assert config is not None
            assert config.client_id == "test-client-id"
            assert config.client_secret == "test-secret"
            assert config.redirect_port == 8888
            assert config.scope == "custom scope"

    def test_oauth2_config_from_env_missing(self):
        """Test OAuth2Config returns None when required env vars missing."""
        with patch.dict(os.environ, {}, clear=True):
            config = OAuth2Config.from_env()
            assert config is None


class TestNuxeoServerConfig:
    """Test Nuxeo server configuration."""

    def test_basic_auth_config(self):
        """Test basic authentication configuration."""
        config = NuxeoServerConfig(
            url="http://localhost:8080/nuxeo",
            auth_method=AuthMethod.BASIC,
            username="admin",
            password="password",
        )
        assert config.auth_method == AuthMethod.BASIC
        assert config.username == "admin"
        assert config.password == "password"

    def test_oauth2_config(self):
        """Test OAuth2 configuration."""
        oauth2 = OAuth2Config(
            client_id="test-client",
            client_secret="test-secret",
        )
        config = NuxeoServerConfig(
            url="http://localhost:8080/nuxeo",
            auth_method=AuthMethod.OAUTH2,
            oauth2_config=oauth2,
        )
        assert config.auth_method == AuthMethod.OAUTH2
        assert config.oauth2_config.client_id == "test-client"

    def test_invalid_basic_auth_config(self):
        """Test that basic auth requires username and password."""
        with pytest.raises(ValueError, match="Username and password required"):
            NuxeoServerConfig(
                url="http://localhost:8080/nuxeo",
                auth_method=AuthMethod.BASIC,
            )

    def test_invalid_oauth2_config(self):
        """Test that OAuth2 requires oauth2_config."""
        with pytest.raises(ValueError, match="OAuth2 configuration required"):
            NuxeoServerConfig(
                url="http://localhost:8080/nuxeo",
                auth_method=AuthMethod.OAUTH2,
            )


class TestMCPAuthConfig:
    """Test MCP authentication configuration."""

    def test_default_config_path(self):
        """Test default configuration path generation."""
        config = MCPAuthConfig()
        assert config.config_file_path is not None
        assert "nuxeo-mcp" in str(config.config_file_path)

    def test_add_server(self):
        """Test adding server configurations."""
        config = MCPAuthConfig()
        server_config = NuxeoServerConfig(
            url="http://test.nuxeo.com",
            auth_method=AuthMethod.BASIC,
            username="user",
            password="pass",
        )
        config.add_server("test", server_config)

        assert "test" in config.servers
        assert config.default_server == "test"
        assert config.get_server_config("test") == server_config

    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            # Create and save config
            config = MCPAuthConfig(config_file_path=config_path)
            oauth2 = OAuth2Config(
                client_id="test-client",
                client_secret="test-secret",
            )
            server_config = NuxeoServerConfig(
                url="http://test.nuxeo.com",
                auth_method=AuthMethod.OAUTH2,
                oauth2_config=oauth2,
            )
            config.add_server("test", server_config)
            config.save()

            # Load config
            loaded_config = MCPAuthConfig.load(config_path)
            assert "test" in loaded_config.servers
            assert loaded_config.servers["test"].url == "http://test.nuxeo.com"
            assert loaded_config.servers["test"].auth_method == AuthMethod.OAUTH2
            # Client secret should be empty when loaded without env var
            assert loaded_config.servers["test"].oauth2_config.client_secret == ""

    def test_load_writes_nothing_to_disk(self, monkeypatch, tmp_path):
        """Loading the configuration creates no file or directory."""
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.delenv("APPDATA", raising=False)

        MCPAuthConfig.load()

        assert list(tmp_path.iterdir()) == []


class TestAuthMode:
    """Test the NUXEO_MCP_AUTH_MODE setting."""

    @pytest.mark.parametrize("value", [None, "", "local", " Local "])
    def test_local(self, monkeypatch, value):
        """Unset, empty, or any spelling of local means local."""
        if value is None:
            monkeypatch.delenv("NUXEO_MCP_AUTH_MODE", raising=False)
        else:
            monkeypatch.setenv("NUXEO_MCP_AUTH_MODE", value)
        assert AuthMode.from_env() == AuthMode.LOCAL

    def test_unsupported_value_is_rejected(self, monkeypatch):
        """Any other value fails and names the supported ones."""
        monkeypatch.setenv("NUXEO_MCP_AUTH_MODE", "delegated")
        with pytest.raises(ValueError, match="supported: local"):
            AuthMode.from_env()


class TestOAuth2Token:
    """Test OAuth2 token handling."""

    def test_token_creation(self):
        """Test creating an OAuth2 token."""
        token = OAuth2Token(
            access_token="access-123",
            refresh_token="refresh-456",
            expires_in=3600,
        )
        assert token.access_token == "access-123"
        assert token.refresh_token == "refresh-456"
        assert token.expires_at is not None

    def test_token_expiration_check(self):
        """Test checking if token is expired."""
        import time

        # Create expired token
        token = OAuth2Token(
            access_token="access-123",
            expires_at=time.time() - 100,  # Expired 100 seconds ago
        )
        assert token.is_expired()

        # Create valid token
        token = OAuth2Token(
            access_token="access-456",
            expires_at=time.time() + 3600,  # Expires in 1 hour
        )
        assert not token.is_expired()

    def test_token_serialization(self):
        """Test token serialization and deserialization."""
        token = OAuth2Token(
            access_token="access-123",
            refresh_token="refresh-456",
            token_type="Bearer",
            expires_in=3600,
            scope="openid profile",
        )

        # Serialize
        data = token.to_dict()
        assert data["access_token"] == "access-123"
        assert data["refresh_token"] == "refresh-456"

        # Deserialize
        restored = OAuth2Token.from_dict(data)
        assert restored.access_token == token.access_token
        assert restored.refresh_token == token.refresh_token
        assert restored.scope == token.scope


class TestEncryptedFileStorage:
    """Test encrypted file token storage."""

    def test_store_and_retrieve_token(self):
        """Test storing and retrieving tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EncryptedFileStorage(Path(tmpdir))

            token = OAuth2Token(
                access_token="test-access",
                refresh_token="test-refresh",
            )

            # Store token
            storage.store_token("http://test.nuxeo.com", token)

            # Retrieve token
            retrieved = storage.get_token("http://test.nuxeo.com")
            assert retrieved is not None
            assert retrieved.access_token == "test-access"
            assert retrieved.refresh_token == "test-refresh"

    def test_delete_token(self):
        """Test deleting tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EncryptedFileStorage(Path(tmpdir))

            token = OAuth2Token(access_token="test-access")
            storage.store_token("http://test.nuxeo.com", token)

            # Delete token
            storage.delete_token("http://test.nuxeo.com")

            # Should return None now
            retrieved = storage.get_token("http://test.nuxeo.com")
            assert retrieved is None

    def test_list_servers(self):
        """Test listing servers with stored tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EncryptedFileStorage(Path(tmpdir))

            # Store tokens for multiple servers
            token1 = OAuth2Token(access_token="access1")
            token2 = OAuth2Token(access_token="access2")

            storage.store_token("http://server1.com", token1)
            storage.store_token("http://server2.com", token2)

            servers = storage.list_servers()
            assert len(servers) == 2
            assert "http://server1.com" in servers
            assert "http://server2.com" in servers


class TestTokenManager:
    """Test high-level token management."""

    def test_store_and_get_token(self):
        """Test storing and retrieving tokens via manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Force encrypted file backend
            manager = TokenManager(backend="encrypted_file")
            manager.storage = EncryptedFileStorage(Path(tmpdir))

            token_data = {
                "access_token": "access-123",
                "refresh_token": "refresh-456",
                "expires_in": 3600,
            }

            # Store token
            manager.store_token("http://test.com", token_data)

            # Get token
            retrieved = manager.get_token("http://test.com")
            assert retrieved is not None
            assert retrieved["access_token"] == "access-123"

    def test_expired_token_returns_none(self):
        """Test that expired tokens return None."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TokenManager(backend="encrypted_file")
            manager.storage = EncryptedFileStorage(Path(tmpdir))

            # Store expired token
            token_data = {
                "access_token": "expired-token",
                "expires_at": time.time() - 100,  # Expired
            }
            manager.store_token("http://test.com", token_data)

            # Should return None for expired token
            retrieved = manager.get_token("http://test.com")
            assert retrieved is None


class TestBasicAuthHandler:
    """Test basic authentication handler."""

    @patch("nuxeo_mcp.auth.Nuxeo")
    def test_basic_auth_success(self, mock_nuxeo_class):
        """Test successful basic authentication."""
        # Setup mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "testuser"}
        mock_client.client.request.return_value = mock_response
        mock_nuxeo_class.return_value = mock_client

        config = NuxeoServerConfig(
            url="http://test.com",
            auth_method=AuthMethod.BASIC,
            username="user",
            password="pass",
        )

        handler = BasicAuthHandler(config)
        result = handler.authenticate()

        assert result is True
        assert handler.nuxeo_client is not None
        mock_nuxeo_class.assert_called_with(
            host="http://test.com",
            auth=("user", "pass"),
        )

    @patch("nuxeo_mcp.auth.Nuxeo")
    def test_basic_auth_failure(self, mock_nuxeo_class):
        """Test failed basic authentication."""
        # Setup mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client.client.request.return_value = mock_response
        mock_nuxeo_class.return_value = mock_client

        config = NuxeoServerConfig(
            url="http://test.com",
            auth_method=AuthMethod.BASIC,
            username="user",
            password="wrong",
        )

        handler = BasicAuthHandler(config)
        result = handler.authenticate()

        assert result is False


class TestOAuth2AuthHandler:
    """Test the OAuth2 handler's use of a stored token."""

    @staticmethod
    def _handler_with_stored_token() -> OAuth2AuthHandler:
        server_config = NuxeoServerConfig(
            url="http://test.com",
            auth_method=AuthMethod.OAUTH2,
            oauth2_config=OAuth2Config(client_id="client", client_secret="secret"),
        )
        token_manager = MagicMock()
        token_manager.get_token.return_value = {
            "access_token": "access",
            "expires_at": time.time() + 3600,
        }
        return OAuth2AuthHandler(server_config, token_manager=token_manager)

    @patch("nuxeo_mcp.auth.OAuth2")
    @patch("nuxeo_mcp.auth.Nuxeo")
    def test_stored_token_reports_its_user(self, mock_nuxeo_class, mock_oauth2):
        """A stored token is checked with Nuxeo, which names its user."""
        response = mock_nuxeo_class.return_value.client.request.return_value
        response.status_code = 200
        response.json.return_value = {"id": "jdoe"}
        handler = self._handler_with_stored_token()

        with patch.object(handler, "_start_callback_server") as start:
            assert handler.authenticate() is True

        assert handler.username == "jdoe"
        start.assert_not_called()

    @pytest.mark.parametrize("refusal", [Unauthorized, Forbidden])
    @patch("nuxeo_mcp.auth.OAuth2")
    @patch("nuxeo_mcp.auth.Nuxeo")
    def test_rejected_stored_token_signs_in_again(
        self, mock_nuxeo_class, mock_oauth2, refusal
    ):
        """A stored token Nuxeo rejects leads to a new sign-in."""
        mock_nuxeo_class.return_value.client.request.side_effect = refusal()
        handler = self._handler_with_stored_token()

        with (
            patch.object(handler, "_find_available_port", return_value=8765),
            patch.object(
                handler, "_start_callback_server", side_effect=RuntimeError("sign-in")
            ) as start,
        ):
            assert handler.authenticate() is False

        start.assert_called_once_with(8765)
        assert handler.username is None

    @patch("nuxeo_mcp.auth.OAuth2")
    @patch("nuxeo_mcp.auth.Nuxeo")
    def test_unreachable_nuxeo_keeps_stored_token(self, mock_nuxeo_class, mock_oauth2):
        """When Nuxeo cannot be reached, the stored token is kept, not replaced."""
        mock_nuxeo_class.return_value.client.request.side_effect = (
            requests.ConnectionError("connection refused")
        )
        handler = self._handler_with_stored_token()

        with patch.object(handler, "_start_callback_server") as start:
            assert handler.authenticate() is True

        start.assert_not_called()
        assert handler.username is None


class TestAuthMiddleware:
    """Test authentication middleware."""

    def test_logout(self):
        """Test logout functionality."""
        mock_handler = MagicMock()
        middleware = AuthMiddleware(mock_handler)

        middleware.logout()

        assert middleware._authenticated is False
        assert middleware._last_auth_check is None
        mock_handler.logout.assert_called_once()


class TestAuthenticationManager:
    """Test authentication manager."""

    @patch("nuxeo_mcp.middleware.OAuth2AuthHandler")
    def test_setup_oauth2(self, mock_oauth2_handler):
        """Test setting up OAuth2 authentication."""
        oauth2_config = OAuth2Config(
            client_id="test-client",
            client_secret="test-secret",
        )
        server_config = NuxeoServerConfig(
            url="http://test.com",
            auth_method=AuthMethod.OAUTH2,
            oauth2_config=oauth2_config,
        )

        manager = AuthenticationManager()
        result = manager.setup(server_config)

        assert result is True
        assert manager.auth_handler is not None
        assert manager.middleware is not None
        mock_oauth2_handler.assert_called_once_with(server_config)

    @patch("nuxeo_mcp.middleware.BasicAuthHandler")
    def test_setup_basic_auth(self, mock_basic_handler):
        """Test setting up basic authentication."""
        server_config = NuxeoServerConfig(
            url="http://test.com",
            auth_method=AuthMethod.BASIC,
            username="user",
            password="pass",
        )

        manager = AuthenticationManager()
        result = manager.setup(server_config)

        assert result is True
        assert manager.auth_handler is not None
        assert manager.middleware is not None
        mock_basic_handler.assert_called_once_with(server_config)


def test_authorization_url_uses_the_real_nuxeo_client() -> None:
    """The mocked flow hid a duplicate code_challenge keyword for a year.

    Build the sign-in URL with the real nuxeo.auth.OAuth2, so a signature
    change in the client fails here rather than at the first real sign-in.
    """
    from unittest.mock import patch

    from nuxeo_mcp.auth import OAuth2AuthHandler
    from nuxeo_mcp.config import AuthMethod, NuxeoServerConfig, OAuth2Config

    handler = OAuth2AuthHandler(
        NuxeoServerConfig(
            url="http://nuxeo.test/nuxeo",
            auth_method=AuthMethod.OAUTH2,
            oauth2_config=OAuth2Config(
                client_id="mcp", client_secret="s", redirect_port=18777
            ),
        ),
        token_manager=MagicMock(get_token=MagicMock(return_value=None)),
    )
    seen = {}

    class StopAfterUrl(Exception):
        pass

    def capture(url: str) -> bool:
        seen["url"] = url
        raise StopAfterUrl

    with patch("webbrowser.open", side_effect=capture):
        assert handler.authenticate(open_browser=True) is False

    assert seen["url"].startswith("http://nuxeo.test/nuxeo/oauth2/authorize?")
    assert "code_challenge=" in seen["url"]
    assert "code_challenge_method=S256" in seen["url"]
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A18777%2Fcallback" in seen["url"]

    # The sign-in failed mid-flow: its callback listener must be gone.
    import socket

    with socket.socket() as probe:
        assert probe.connect_ex(("localhost", 18777)) != 0
