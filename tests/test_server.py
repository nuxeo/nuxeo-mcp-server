"""
Unit tests for the Nuxeo MCP Server.

These tests verify the functionality of the MCP server using mocks,
without requiring a connection to a real Nuxeo server.
"""

import sys
import unittest.mock as mock
from typing import Any, Callable, Dict, List, Optional, Type, Union
from unittest.mock import MagicMock, patch

import pytest

# Create mocks for the unit tests
mock_nuxeo_client = MagicMock()
mock_fastmcp = MagicMock()


# Create a mock FastMCP class for unit tests
class MockFastMCP:
    def __init__(self, name: str):
        self.name: str = name
        self.tools: List[Dict[str, Any]] = []
        self.resources: List[Dict[str, Any]] = []
        self.prompts: List[Dict[str, Any]] = []
        self.custom_routes: List[Dict[str, Any]] = []

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        annotations: Any = None,
    ):
        def decorator(func):
            # Support both @mcp.tool() and @mcp.tool(name="...", description="...")
            tool_name = name if name else func.__name__
            tool_desc = description if description else (func.__doc__ or "").strip()
            self.tools.append(
                {
                    "name": tool_name,
                    "description": tool_desc,
                    "input_schema": input_schema,
                    "annotations": annotations,
                    "func": func,
                }
            )
            return func

        return decorator

    def resource(
        self,
        uri: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        def decorator(func):
            # Support both @mcp.resource() and @mcp.resource(uri="...", name="...", description="...")
            resource_uri = uri if uri else func.__name__
            resource_name = name if name else func.__name__
            resource_desc = description if description else (func.__doc__ or "").strip()
            self.resources.append(
                {
                    "uri": resource_uri,
                    "name": resource_name,
                    "description": resource_desc,
                    "func": func,
                }
            )
            return func

        return decorator

    def prompt(self, func=None):
        if func is None:

            def decorator(f):
                self.prompts.append(
                    {"name": f.__name__, "description": f.__doc__ or "", "func": f}
                )
                return f

            return decorator
        else:
            self.prompts.append(
                {"name": func.__name__, "description": func.__doc__ or "", "func": func}
            )
            return func

    def custom_route(self, path: str, methods: Optional[List[str]] = None):
        """Mock custom_route decorator for health check endpoint."""

        def decorator(func):
            self.custom_routes.append(
                {"path": path, "methods": methods or ["GET"], "func": func}
            )
            return func

        return decorator

    def list_tools(self) -> List[Any]:
        return [type("Tool", (), {"name": t["name"]}) for t in self.tools]

    def list_resources(self) -> List[Any]:
        return [type("Resource", (), {"uri": r["uri"]}) for r in self.resources]

    def run(self) -> None:
        pass


# NuxeoMCPServer takes the FastMCP class as a parameter, so these tests inject
# MockFastMCP directly. Do not patch sys.modules['fastmcp']: that leaks a mock
# into every other test module for the whole session.
from nuxeo_mcp.server import NuxeoMCPServer


@pytest.mark.unit
def test_mcp_server_initialization() -> None:
    """Test that the MCP server can be initialized."""
    # Mock the Nuxeo client to avoid actual connection
    with mock.patch("nuxeo_mcp.server.Nuxeo"):
        server = NuxeoMCPServer(
            nuxeo_url="http://localhost:8080/nuxeo",
            username="Administrator",
            password="Administrator",
            fastmcp_class=MockFastMCP,
        )

        # Check that the server was initialized correctly
        assert server.nuxeo_url == "http://localhost:8080/nuxeo"
        assert server.username == "Administrator"
        assert server.password == "Administrator"
        assert server.mcp is not None


@pytest.mark.unit
def test_mcp_tools_registration() -> None:
    """Test that the MCP server registers tools correctly."""
    # Mock the Nuxeo client to avoid actual connection
    with mock.patch("nuxeo_mcp.server.Nuxeo"):
        server = NuxeoMCPServer(
            username="user", password="pass", fastmcp_class=MockFastMCP
        )

        # Get the list of tools
        tools = server.mcp.list_tools()

        # Check that the expected tools are registered
        tool_names = [tool.name for tool in tools]
        assert "nuxeo_get_repository_info" in tool_names


@pytest.mark.unit
def test_mcp_resources_registration() -> None:
    """Test that the MCP server registers resources correctly."""
    # Mock the Nuxeo client to avoid actual connection
    with mock.patch("nuxeo_mcp.server.Nuxeo"):
        server = NuxeoMCPServer(
            username="user", password="pass", fastmcp_class=MockFastMCP
        )

        # Get the list of resources
        resources = server.mcp.list_resources()

        # Check that the expected resources are registered
        resource_uris = [resource.uri for resource in resources]
        assert "nuxeo://info" in resource_uris


@pytest.mark.unit
@pytest.mark.parametrize("basic_credentials", [False, True])
def test_oauth2_flag_uses_oauth2_when_auth_method_unset(
    monkeypatch, tmp_path, basic_credentials
) -> None:
    """--oauth2 means OAuth2 even when NUXEO_AUTH_METHOD is unset."""
    from nuxeo_mcp.config import AuthMethod

    for name in ("NUXEO_AUTH_METHOD", "NUXEO_USERNAME", "NUXEO_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NUXEO_URL", "http://localhost:8080/nuxeo")
    monkeypatch.setenv("NUXEO_OAUTH_CLIENT_ID", "client")
    monkeypatch.setenv("NUXEO_OAUTH_CLIENT_SECRET", "secret")
    if basic_credentials:
        monkeypatch.setenv("NUXEO_USERNAME", "user")
        monkeypatch.setenv("NUXEO_PASSWORD", "pass")
    monkeypatch.setattr(
        "nuxeo_mcp.config.MCPAuthConfig._get_default_config_path",
        staticmethod(lambda: tmp_path / "auth_config.json"),
    )

    with patch("nuxeo_mcp.server.AuthenticationManager") as manager_class:
        manager = manager_class.return_value
        manager.setup.return_value = True
        manager.authenticate.return_value = True
        NuxeoMCPServer(use_oauth2=True, fastmcp_class=MockFastMCP)

    server_config = manager.setup.call_args.args[0]
    assert server_config.auth_method == AuthMethod.OAUTH2


@pytest.mark.unit
def test_oauth2_ignores_a_non_oauth2_default_server(monkeypatch, tmp_path) -> None:
    """A basic default server from a config file does not stand in for OAuth2."""
    from nuxeo_mcp.config import AuthMethod, MCPAuthConfig, NuxeoServerConfig

    monkeypatch.setenv("NUXEO_OAUTH_CLIENT_ID", "client")
    monkeypatch.setenv("NUXEO_OAUTH_CLIENT_SECRET", "secret")
    auth_config = MCPAuthConfig(config_file_path=tmp_path / "auth_config.json")
    auth_config.add_server(
        "default",
        NuxeoServerConfig(
            url="http://localhost:8080/nuxeo",
            auth_method=AuthMethod.BASIC,
            username="user",
            password="pass",
        ),
    )

    with patch("nuxeo_mcp.server.AuthenticationManager") as manager_class:
        manager = manager_class.return_value
        manager.setup.return_value = True
        manager.authenticate.return_value = True
        NuxeoMCPServer(
            use_oauth2=True, auth_config=auth_config, fastmcp_class=MockFastMCP
        )

    server_config = manager.setup.call_args.args[0]
    assert server_config.auth_method == AuthMethod.OAUTH2


@pytest.mark.unit
@pytest.mark.parametrize(
    "username,password",
    [(None, "s3cret-pw"), ("user", None), ("user", ""), ("", "s3cret-pw")],
)
def test_basic_auth_requires_explicit_credentials(username, password) -> None:
    """Basic auth refuses to start without both credentials, and never echoes them."""
    with mock.patch("nuxeo_mcp.server.Nuxeo") as nuxeo_class:
        with pytest.raises(ValueError, match="NUXEO_USERNAME and NUXEO_PASSWORD") as e:
            NuxeoMCPServer(
                username=username, password=password, fastmcp_class=MockFastMCP
            )

    assert "s3cret-pw" not in str(e.value)
    nuxeo_class.assert_not_called()


@pytest.mark.unit
def test_health_reports_auth_mode() -> None:
    """The /health endpoint stays public and reports the auth mode."""
    import asyncio
    import json

    with mock.patch("nuxeo_mcp.server.Nuxeo"):
        server = NuxeoMCPServer(
            username="user", password="pass", fastmcp_class=MockFastMCP
        )

    health = server.mcp.custom_routes[0]
    response = asyncio.run(health["func"](MagicMock()))
    body = json.loads(response.body)
    assert health["path"] == "/health"
    assert body["auth_mode"] == "local"
    assert body["auth_method"] == "basic"


@pytest.mark.unit
def test_health_reports_the_oauth2_user() -> None:
    """Under OAuth2, /health names the user Nuxeo authenticated."""
    import asyncio
    import json

    from nuxeo_mcp.config import AuthMethod

    auth_config = MagicMock()
    auth_config.get_server_config.return_value.auth_method = AuthMethod.OAUTH2
    with patch("nuxeo_mcp.server.AuthenticationManager") as manager_class:
        manager = manager_class.return_value
        manager.setup.return_value = True
        manager.authenticate.return_value = True
        manager.get_username.return_value = "jdoe"
        server = NuxeoMCPServer(
            use_oauth2=True, auth_config=auth_config, fastmcp_class=MockFastMCP
        )

    health = server.mcp.custom_routes[0]
    body = json.loads(asyncio.run(health["func"](MagicMock())).body)
    assert body["username"] == "jdoe"
    assert body["auth_method"] == "oauth2"


def _prepare_main(monkeypatch, env: Dict[str, str]) -> None:
    """Give main() a clean environment and command line."""
    for name in (
        "NUXEO_URL",
        "NUXEO_USERNAME",
        "NUXEO_PASSWORD",
        "NUXEO_AUTH_METHOD",
        "NUXEO_MCP_AUTH_MODE",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["nuxeo-mcp"])


@pytest.mark.unit
def test_main_refuses_to_start_without_credentials(monkeypatch, caplog) -> None:
    """With no credentials configured, main() exits instead of running as anyone."""
    from nuxeo_mcp.server import main

    _prepare_main(monkeypatch, {})
    caplog.set_level("INFO", logger="nuxeo_mcp")
    with mock.patch("nuxeo_mcp.server.Nuxeo") as nuxeo_class:
        with pytest.raises(SystemExit) as e:
            main()

    assert e.value.code == 1
    assert "NUXEO_USERNAME and NUXEO_PASSWORD" in caplog.text
    nuxeo_class.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    "name,value,expected",
    [
        ("NUXEO_MCP_AUTH_MODE", "delegated", "supported: local"),
        ("NUXEO_AUTH_METHOD", "jwt", "supported: basic, oauth2"),
    ],
)
def test_main_rejects_unsupported_settings(
    monkeypatch, caplog, name, value, expected
) -> None:
    """An unknown auth mode or auth method stops startup with a clear error."""
    from nuxeo_mcp.server import main

    _prepare_main(
        monkeypatch, {"NUXEO_USERNAME": "user", "NUXEO_PASSWORD": "pass", name: value}
    )
    with mock.patch("nuxeo_mcp.server.NuxeoMCPServer") as server_class:
        with pytest.raises(SystemExit) as e:
            main()

    assert e.value.code == 1
    assert expected in caplog.text
    server_class.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    "mode,source", [(None, "default"), ("LOCAL", "NUXEO_MCP_AUTH_MODE")]
)
def test_main_starts_in_local_mode_and_logs_it(
    monkeypatch, caplog, mode, source
) -> None:
    """main() runs in local mode by default, says so, and never logs the password."""
    from nuxeo_mcp.config import AuthMode
    from nuxeo_mcp.server import main

    env = {"NUXEO_USERNAME": "user", "NUXEO_PASSWORD": "s3cret-pw"}
    if mode:
        env["NUXEO_MCP_AUTH_MODE"] = mode
    _prepare_main(monkeypatch, env)
    caplog.set_level("INFO", logger="nuxeo_mcp")
    with (
        mock.patch("nuxeo_mcp.server.Nuxeo"),
        mock.patch("requests.get"),
        mock.patch("nuxeo_mcp.server.FastMCP", MockFastMCP),
        mock.patch.object(NuxeoMCPServer, "run") as run,
    ):
        main()

    run.assert_called_once()
    assert f"Auth mode: local ({source})" in caplog.text
    assert "s3cret-pw" not in caplog.text
