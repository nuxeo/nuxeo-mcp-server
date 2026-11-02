"""Test doubles shared by the unit and integration tests."""

from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock

from nuxeo_mcp.resources import register_resources
from nuxeo_mcp.tools import register_tools

Captured = Dict[str, Callable[..., Any]]


class MockFastMCP:
    """FastMCP stand-in recording what the server registers.

    Pass it as NuxeoMCPServer(fastmcp_class=MockFastMCP). Do not patch
    sys.modules['fastmcp'] instead: the mock leaks into every later test.
    """

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
    ) -> Callable[[Callable], Callable]:
        def decorator(func: Callable) -> Callable:
            self.tools.append(
                {
                    "name": name or func.__name__,
                    "description": description or (func.__doc__ or "").strip(),
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
    ) -> Callable[[Callable], Callable]:
        def decorator(func: Callable) -> Callable:
            self.resources.append(
                {
                    "uri": uri or func.__name__,
                    "name": name or func.__name__,
                    "description": description or (func.__doc__ or "").strip(),
                    "func": func,
                }
            )
            return func

        return decorator

    def prompt(self, func: Optional[Callable] = None, **_: Any) -> Any:
        def record(f: Callable) -> Callable:
            self.prompts.append(
                {"name": f.__name__, "description": f.__doc__ or "", "func": f}
            )
            return f

        return record if func is None else record(func)

    def custom_route(
        self, path: str, methods: Optional[List[str]] = None
    ) -> Callable[[Callable], Callable]:
        def decorator(func: Callable) -> Callable:
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


def mock_nuxeo() -> MagicMock:
    """A Nuxeo client mock with the host and auth the passthrough reads."""
    nuxeo = MagicMock()
    nuxeo.client.host = "http://nuxeo:8080/nuxeo"
    nuxeo.client.auth = ("user", "pass")
    return nuxeo


def capture_tools(nuxeo: Any, *args: Any, **kwargs: Any) -> Captured:
    """Register the tools; return their functions by tool name.

    Extra arguments go to register_tools (file path policy, read_only).
    """
    mcp = MockFastMCP("test")
    register_tools(mcp, nuxeo, *args, **kwargs)
    return {t["name"]: t["func"] for t in mcp.tools}


def capture_resources(nuxeo: Any) -> Captured:
    """Register the resources; return their functions by URI."""
    mcp = MockFastMCP("test")
    register_resources(mcp, nuxeo)
    return {r["uri"]: r["func"] for r in mcp.resources}
