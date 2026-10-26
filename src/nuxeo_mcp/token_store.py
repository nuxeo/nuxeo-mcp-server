"""
Secure token storage for OAuth2 authentication.

This module provides secure storage for OAuth2 tokens using OS keychains
with fallback to encrypted file storage.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import keyring

    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


@dataclass
class OAuth2Token:
    """OAuth2 token with metadata."""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    expires_at: Optional[float] = None
    scope: Optional[str] = None

    def __post_init__(self):
        """Calculate expiration time if not provided."""
        if self.expires_in and not self.expires_at:
            self.expires_at = datetime.now().timestamp() + self.expires_in

    def is_expired(self, buffer_seconds: int = 60) -> bool:
        """Check if token is expired or will expire soon."""
        if not self.expires_at:
            return False
        return datetime.now().timestamp() + buffer_seconds >= self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OAuth2Token":
        """Create from dictionary."""
        return cls(**data)


class TokenStorage(ABC):
    """Abstract base class for token storage backends."""

    @abstractmethod
    def store_token(self, server_url: str, token: OAuth2Token) -> None:
        """Store a token for a server."""
        pass

    @abstractmethod
    def get_token(self, server_url: str) -> Optional[OAuth2Token]:
        """Retrieve a token for a server."""
        pass

    @abstractmethod
    def delete_token(self, server_url: str) -> None:
        """Delete a token for a server."""
        pass

    @abstractmethod
    def list_servers(self) -> list[str]:
        """List all servers with stored tokens."""
        pass


class KeyringStorage(TokenStorage):
    """Token storage using OS keychain."""

    SERVICE_NAME = "nuxeo-mcp"

    def __init__(self):
        """Initialize keyring storage."""
        if not KEYRING_AVAILABLE:
            raise ImportError("keyring package not available")
        logger.info("Using OS keyring for token storage")

    def _get_key(self, server_url: str) -> str:
        """Generate storage key for server."""
        # Sanitize URL for keyring storage
        return f"{self.SERVICE_NAME}:{server_url.replace('://', '_').replace('/', '_')}"

    def store_token(self, server_url: str, token: OAuth2Token) -> None:
        """Store token in keyring."""
        try:
            key = self._get_key(server_url)
            token_data = json.dumps(token.to_dict())
            keyring.set_password(self.SERVICE_NAME, key, token_data)
            logger.debug(f"Token stored in keyring for {server_url}")
        except Exception as e:
            logger.error(f"Failed to store token in keyring: {e}")
            raise

    def get_token(self, server_url: str) -> Optional[OAuth2Token]:
        """Retrieve token from keyring."""
        try:
            key = self._get_key(server_url)
            token_data = keyring.get_password(self.SERVICE_NAME, key)
            if token_data:
                data = json.loads(token_data)
                return OAuth2Token.from_dict(data)
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve token from keyring: {e}")
            return None

    def delete_token(self, server_url: str) -> None:
        """Delete token from keyring."""
        try:
            key = self._get_key(server_url)
            keyring.delete_password(self.SERVICE_NAME, key)
            logger.debug(f"Token deleted from keyring for {server_url}")
        except Exception as e:
            logger.warning(f"Failed to delete token from keyring: {e}")

    def list_servers(self) -> list[str]:
        """List all servers with stored tokens."""
        # Note: keyring doesn't provide a way to list all keys
        # This would need to be tracked separately
        logger.warning("Listing servers not fully supported with keyring backend")
        return []


class EncryptedFileStorage(TokenStorage):
    """Token storage using encrypted file."""

    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize encrypted file storage."""
        self.storage_dir = storage_dir or self._get_default_storage_dir()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_file = self.storage_dir / "tokens.enc"
        self.key_file = self.storage_dir / ".key"
        self._ensure_encryption_key()
        logger.info(f"Using encrypted file storage at {self.storage_dir}")

    @staticmethod
    def _get_default_storage_dir() -> Path:
        """Get default storage directory based on OS."""
        if os.name == "nt":  # Windows
            base_path = Path(
                os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
            )
        elif os.name == "posix":
            if "Darwin" in os.uname().sysname:  # macOS
                base_path = Path.home() / "Library" / "Application Support"
            else:  # Linux
                base_path = Path(
                    os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
                )
        else:
            base_path = Path.home() / ".local" / "share"

        return base_path / "nuxeo-mcp" / "tokens"

    def _ensure_encryption_key(self) -> None:
        """Ensure encryption key exists."""
        if not self.key_file.exists():
            # Generate a new key
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)
            # Set restrictive permissions (owner read/write only)
            if os.name != "nt":
                os.chmod(self.key_file, 0o600)
        else:
            # Ensure permissions are correct
            if os.name != "nt":
                current_mode = os.stat(self.key_file).st_mode & 0o777
                if current_mode != 0o600:
                    os.chmod(self.key_file, 0o600)

    def _get_cipher(self) -> Fernet:
        """Get cipher for encryption/decryption."""
        key = self.key_file.read_bytes()
        return Fernet(key)

    def _load_tokens(self) -> Dict[str, Dict[str, Any]]:
        """Load all tokens from encrypted storage."""
        if not self.storage_file.exists():
            return {}

        try:
            cipher = self._get_cipher()
            encrypted_data = self.storage_file.read_bytes()
            decrypted_data = cipher.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            logger.error(f"Failed to load tokens: {e}")
            return {}

    def _save_tokens(self, tokens: Dict[str, Dict[str, Any]]) -> None:
        """Save all tokens to encrypted storage."""
        try:
            cipher = self._get_cipher()
            data = json.dumps(tokens).encode()
            encrypted_data = cipher.encrypt(data)
            self.storage_file.write_bytes(encrypted_data)

            # Set restrictive permissions
            if os.name != "nt":
                os.chmod(self.storage_file, 0o600)
        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")
            raise

    def store_token(self, server_url: str, token: OAuth2Token) -> None:
        """Store token in encrypted file."""
        tokens = self._load_tokens()
        tokens[server_url] = token.to_dict()
        self._save_tokens(tokens)
        logger.debug(f"Token stored in encrypted file for {server_url}")

    def get_token(self, server_url: str) -> Optional[OAuth2Token]:
        """Retrieve token from encrypted file."""
        tokens = self._load_tokens()
        token_data = tokens.get(server_url)
        if token_data:
            return OAuth2Token.from_dict(token_data)
        return None

    def delete_token(self, server_url: str) -> None:
        """Delete token from encrypted file."""
        tokens = self._load_tokens()
        if server_url in tokens:
            del tokens[server_url]
            self._save_tokens(tokens)
            logger.debug(f"Token deleted from encrypted file for {server_url}")

    def list_servers(self) -> list[str]:
        """List all servers with stored tokens."""
        tokens = self._load_tokens()
        return list(tokens.keys())


class TokenManager:
    """High-level token management with automatic backend selection."""

    def __init__(self, backend: Optional[str] = None):
        """
        Initialize token manager.

        Args:
            backend: Force specific backend ('keyring' or 'encrypted_file')
        """
        self.storage = self._init_storage(backend)

    def _init_storage(self, backend: Optional[str] = None) -> TokenStorage:
        """Initialize the appropriate storage backend."""
        if backend == "keyring" or (backend is None and KEYRING_AVAILABLE):
            try:
                return KeyringStorage()
            except Exception as e:
                logger.warning(f"Failed to initialize keyring storage: {e}")
                if backend == "keyring":
                    raise

        # Fallback to encrypted file storage
        return EncryptedFileStorage()

    def store_token(self, server_url: str, token_data: Dict[str, Any]) -> None:
        """
        Store OAuth2 token for a server.

        Args:
            server_url: The Nuxeo server URL
            token_data: Token data from OAuth2 response
        """
        token = OAuth2Token(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in"),
            expires_at=token_data.get("expires_at"),
            scope=token_data.get("scope"),
        )
        self.storage.store_token(server_url, token)

    def get_token(self, server_url: str) -> Optional[Dict[str, Any]]:
        """
        Get OAuth2 token for a server.

        Args:
            server_url: The Nuxeo server URL

        Returns:
            Token data or None if not found/expired
        """
        token = self.storage.get_token(server_url)
        if token:
            # Check if token is expired
            if token.is_expired():
                logger.info(f"Token for {server_url} is expired")
                return None
            return token.to_dict()
        return None

    def delete_token(self, server_url: str) -> None:
        """Delete stored token for a server."""
        self.storage.delete_token(server_url)

    def list_servers(self) -> list[str]:
        """List all servers with stored tokens."""
        return self.storage.list_servers()

    def clear_all_tokens(self) -> None:
        """Clear all stored tokens."""
        for server in self.list_servers():
            self.delete_token(server)
