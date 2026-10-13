"""
Server Manager for Nuxeo MCP - Handles multiple server configurations
and maintains context about which server is currently active.
"""

import json
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Name of the default server activated on first run
DEFAULT_SERVER_NAME = "local"


@dataclass
class ServerConfig:
    """Configuration for a Nuxeo server."""
    name: str
    url: str
    username: str
    password: str
    description: str = ""
    is_default: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServerConfig':
        """Create from dictionary."""
        return cls(**data)


class ServerManager:
    """Manages multiple Nuxeo server configurations and active server context."""
    
    def __init__(self, config_file: str = None):
        """
        Initialize the server manager.
        
        Args:
            config_file: Path to the configuration file. 
                        Defaults to ~/.nuxeo-mcp/servers.json
        """
        if config_file:
            self.config_file = Path(config_file)
        else:
            # Use user's home directory for persistent storage
            self.config_file = Path.home() / ".nuxeo-mcp" / "servers.json"
        
        # Ensure config directory exists
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Context file stores the currently active server
        self.context_file = self.config_file.parent / "context.json"
        
        # Load configurations
        self.servers: Dict[str, ServerConfig] = {}
        self.active_server: Optional[str] = None
        
        self._load_config()
        self._load_context()
        
        # Initialize with default servers if none exist
        if not self.servers:
            self._initialize_default_servers()
    
    def _initialize_default_servers(self):
        """Initialize with default server configurations."""
        default_servers = [
            ServerConfig(
                name=DEFAULT_SERVER_NAME,
                url="http://localhost:8080/nuxeo",
                username="Administrator",
                password="Administrator",
                description="Local Development Server",
                is_default=True
            ),
            ServerConfig(
                name="nightly",
                url="https://nightly-2023.nuxeocloud.com/nuxeo",
                username="automated_test_user",
                password="***********", # pwd required
                description="Demo Nuxeo Server",
                is_default=False
            )
        ]
        
        for server in default_servers:
            self.add_server(server)
        
        self.set_active_server(DEFAULT_SERVER_NAME)
        self._save_config()
        self._save_context()
    
    def _load_config(self):
        """Load server configurations from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    for name, config in data.get('servers', {}).items():
                        self.servers[name] = ServerConfig.from_dict(config)
                logger.info(f"Loaded {len(self.servers)} server configurations")
            except Exception as e:
                logger.error(f"Failed to load server config: {e}")
    
    def _save_config(self):
        """Save server configurations to file."""
        try:
            data = {
                'servers': {name: server.to_dict() 
                          for name, server in self.servers.items()}
            }
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Saved server configurations")
        except Exception as e:
            logger.error(f"Failed to save server config: {e}")
    
    def _load_context(self):
        """Load active server context from file."""
        if self.context_file.exists():
            try:
                with open(self.context_file, 'r') as f:
                    data = json.load(f)
                    self.active_server = data.get('active_server')
                logger.info(f"Loaded context - active server: {self.active_server}")
            except Exception as e:
                logger.error(f"Failed to load context: {e}")
    
    def _save_context(self):
        """Save active server context to file."""
        try:
            data = {
                'active_server': self.active_server
            }
            with open(self.context_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved context - active server: {self.active_server}")
        except Exception as e:
            logger.error(f"Failed to save context: {e}")
    
    def add_server(self, server: ServerConfig):
        """Add a new server configuration."""
        self.servers[server.name] = server
        self._save_config()
        logger.info(f"Added server: {server.name}")
    
    def remove_server(self, name: str):
        """Remove a server configuration."""
        if name in self.servers:
            del self.servers[name]
            if self.active_server == name:
                # Reset active server if we're removing the active one
                self.active_server = None
                self._save_context()
            self._save_config()
            logger.info(f"Removed server: {name}")
    
    def get_server(self, name: str) -> Optional[ServerConfig]:
        """Get a server configuration by name."""
        return self.servers.get(name)
    
    def get_active_server(self) -> Optional[ServerConfig]:
        """Get the currently active server configuration."""
        if self.active_server:
            return self.servers.get(self.active_server)
        # Return default server if no active server set
        for server in self.servers.values():
            if server.is_default:
                return server
        # Return first server if no default
        if self.servers:
            return list(self.servers.values())[0]
        return None
    
    def set_active_server(self, name: str):
        """Set the active server."""
        if name in self.servers:
            self.active_server = name
            self._save_context()
            logger.info(f"Set active server: {name}")
            return True
        logger.error(f"Server not found: {name}")
        return False
    
    def list_servers(self) -> Dict[str, Dict[str, Any]]:
        """List all server configurations."""
        result = {}
        for name, server in self.servers.items():
            server_info = server.to_dict()
            server_info['is_active'] = (name == self.active_server)
            result[name] = server_info
        return result
    
    def needs_server_selection(self) -> bool:
        """Check if server selection is needed."""
        # Need selection if no active server or if active server doesn't exist
        if not self.active_server:
            return True
        if self.active_server not in self.servers:
            return True
        return False
    
    def get_server_choices(self) -> str:
        """Get formatted string of server choices for user prompt."""
        choices = []
        for name, server in self.servers.items():
            status = " (active)" if name == self.active_server else ""
            status += " (default)" if server.is_default else ""
            choices.append(f"  - {name}: {server.description} [{server.url}]{status}")
        return "\n".join(choices)
    
    def update_server(self, name: str, **kwargs):
        """Update a server configuration."""
        if name in self.servers:
            server = self.servers[name]
            for key, value in kwargs.items():
                if hasattr(server, key):
                    setattr(server, key, value)
            self._save_config()
            logger.info(f"Updated server: {name}")
            return True
        return False


# Global instance
_server_manager: Optional[ServerManager] = None

def get_server_manager() -> ServerManager:
    """Get the global server manager instance."""
    global _server_manager
    if _server_manager is None:
        _server_manager = ServerManager()
    return _server_manager