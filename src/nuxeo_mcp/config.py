"""
Configuration management for Nuxeo MCP authentication.

This module handles authentication configuration including OAuth2 settings,
credential management, and multiple Nuxeo instance support.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)


class AuthMethod(Enum):
    """Supported authentication methods."""

    OAUTH2 = "oauth2"
    BASIC = "basic"
    JWT = "jwt"


@dataclass
class OAuth2Config:
    """OAuth2 configuration settings."""

    client_id: str
    client_secret: str
    redirect_port: Optional[int] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    openid_configuration_url: Optional[str] = None
    scope: str = "openid profile email"

    @classmethod
    def from_env(cls) -> Optional["OAuth2Config"]:
        """Create OAuth2Config from environment variables."""
        client_id = os.environ.get("NUXEO_OAUTH_CLIENT_ID")
        client_secret = os.environ.get("NUXEO_OAUTH_CLIENT_SECRET")

        if not client_id or not client_secret:
            return None

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_port=int(os.environ.get("NUXEO_OAUTH_REDIRECT_PORT", "0")),
            authorization_endpoint=os.environ.get("NUXEO_OAUTH_AUTH_ENDPOINT"),
            token_endpoint=os.environ.get("NUXEO_OAUTH_TOKEN_ENDPOINT"),
            openid_configuration_url=os.environ.get("NUXEO_OAUTH_OPENID_URL"),
            scope=os.environ.get("NUXEO_OAUTH_SCOPE", "openid profile email"),
        )


@dataclass
class NuxeoServerConfig:
    """Configuration for a Nuxeo server instance."""

    url: str
    auth_method: AuthMethod = AuthMethod.BASIC
    username: Optional[str] = None
    password: Optional[str] = None
    oauth2_config: Optional[OAuth2Config] = None
    jwt_secret: Optional[str] = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.auth_method == AuthMethod.OAUTH2 and not self.oauth2_config:
            raise ValueError("OAuth2 configuration required when auth_method is OAUTH2")
        if self.auth_method == AuthMethod.BASIC and (
            not self.username or not self.password
        ):
            raise ValueError("Username and password required when auth_method is BASIC")
        if self.auth_method == AuthMethod.JWT and not self.jwt_secret:
            raise ValueError("JWT secret required when auth_method is JWT")


@dataclass
class MCPAuthConfig:
    """Main authentication configuration for MCP server."""

    servers: Dict[str, NuxeoServerConfig] = field(default_factory=dict)
    default_server: Optional[str] = None
    enable_browser_auth: bool = True
    token_storage_backend: Literal["keyring", "encrypted_file"] = "keyring"
    config_file_path: Optional[Path] = None

    def __post_init__(self):
        """Set default config file path if not provided."""
        if not self.config_file_path:
            self.config_file_path = self._get_default_config_path()

    @staticmethod
    def _get_default_config_path() -> Path:
        """Get the default configuration file path based on the OS."""
        if os.name == "nt":  # Windows
            base_path = Path(
                os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
            )
        elif os.name == "posix":
            if "Darwin" in os.uname().sysname:  # macOS
                base_path = Path.home() / "Library" / "Application Support"
            else:  # Linux
                base_path = Path(
                    os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
                )
        else:
            base_path = Path.home() / ".config"

        config_dir = base_path / "nuxeo-mcp"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "auth_config.json"

    def save(self) -> None:
        """Save configuration to file."""
        if not self.config_file_path:
            return

        config_data = {
            "servers": {
                name: {
                    "url": server.url,
                    "auth_method": server.auth_method.value,
                    "username": server.username,
                    "oauth2_config": (
                        asdict(server.oauth2_config) if server.oauth2_config else None
                    ),
                }
                for name, server in self.servers.items()
            },
            "default_server": self.default_server,
            "enable_browser_auth": self.enable_browser_auth,
            "token_storage_backend": self.token_storage_backend,
        }

        # Don't save sensitive data like passwords or secrets
        for server_data in config_data["servers"].values():
            if "password" in server_data:
                del server_data["password"]
            if server_data.get("oauth2_config", {}).get("client_secret"):
                server_data["oauth2_config"]["client_secret"] = "***"

        self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file_path, "w") as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Configuration saved to {self.config_file_path}")

    @classmethod
    def load(
        cls,
        config_path: Optional[Path] = None,
        auth_method: Optional[AuthMethod] = None,
    ) -> "MCPAuthConfig":
        """Load configuration from file and environment.

        ``auth_method`` overrides NUXEO_AUTH_METHOD for the default server.
        """
        config = cls()

        # Load from file if it exists
        file_path = config_path or config._get_default_config_path()
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)

                config.default_server = data.get("default_server")
                config.enable_browser_auth = data.get("enable_browser_auth", True)
                config.token_storage_backend = data.get(
                    "token_storage_backend", "keyring"
                )

                # Load server configurations
                for name, server_data in data.get("servers", {}).items():
                    # Not auth_method: that is the caller's override, applied to
                    # the env-defined default server below.
                    server_auth_method = AuthMethod(
                        server_data.get("auth_method", "basic")
                    )
                    oauth2_config = None

                    if server_auth_method == AuthMethod.OAUTH2 and server_data.get(
                        "oauth2_config"
                    ):
                        oauth2_data = server_data["oauth2_config"]
                        # Try to get client_secret from environment if masked
                        if oauth2_data.get("client_secret") == "***":
                            oauth2_data["client_secret"] = os.environ.get(
                                f"NUXEO_OAUTH_CLIENT_SECRET_{name.upper()}",
                                os.environ.get("NUXEO_OAUTH_CLIENT_SECRET", ""),
                            )
                        oauth2_config = OAuth2Config(**oauth2_data)

                    config.servers[name] = NuxeoServerConfig(
                        url=server_data["url"],
                        auth_method=server_auth_method,
                        username=server_data.get("username"),
                        oauth2_config=oauth2_config,
                    )

            except Exception as e:
                logger.warning(f"Failed to load config from {file_path}: {e}")

        # Override with environment variables for default server
        config._load_env_config(auth_method)

        return config

    def _load_env_config(self, auth_method: Optional[AuthMethod] = None) -> None:
        """Load configuration from environment variables.

        An explicit ``auth_method`` wins over NUXEO_AUTH_METHOD, so that
        ``--oauth2`` means OAuth2 even when the variable is unset.
        """
        nuxeo_url = os.environ.get("NUXEO_URL")
        if not nuxeo_url:
            return

        if auth_method is None:
            auth_method_str = os.environ.get("NUXEO_AUTH_METHOD", "basic").lower()
            try:
                auth_method = AuthMethod(auth_method_str)
            except ValueError:
                logger.warning(
                    f"Invalid auth method: {auth_method_str}, falling back to basic"
                )
                auth_method = AuthMethod.BASIC

        oauth2_config = (
            OAuth2Config.from_env() if auth_method == AuthMethod.OAUTH2 else None
        )

        # Create or update the "default" server configuration
        self.servers["default"] = NuxeoServerConfig(
            url=nuxeo_url,
            auth_method=auth_method,
            username=os.environ.get("NUXEO_USERNAME"),
            password=os.environ.get("NUXEO_PASSWORD"),
            oauth2_config=oauth2_config,
            jwt_secret=os.environ.get("NUXEO_JWT_SECRET"),
        )

        if not self.default_server:
            self.default_server = "default"

    def get_server_config(
        self, server_name: Optional[str] = None
    ) -> Optional[NuxeoServerConfig]:
        """Get configuration for a specific server or the default."""
        name = server_name or self.default_server
        if not name:
            return None
        return self.servers.get(name)

    def add_server(self, name: str, config: NuxeoServerConfig) -> None:
        """Add or update a server configuration."""
        self.servers[name] = config
        if not self.default_server:
            self.default_server = name
