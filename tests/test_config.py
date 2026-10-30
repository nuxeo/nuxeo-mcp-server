"""Tests for MCPAuthConfig loading."""

import pytest


@pytest.mark.unit
def test_oauth2_override_survives_a_saved_config_file(monkeypatch, tmp_path) -> None:
    """The loop over saved servers must not overwrite the caller's auth method."""
    import json

    from nuxeo_mcp.config import AuthMethod, MCPAuthConfig

    saved = tmp_path / "auth_config.json"
    saved.write_text(
        json.dumps(
            {
                "servers": {
                    "old": {
                        "url": "http://old/nuxeo",
                        "auth_method": "basic",
                        "username": "u",
                    }
                }
            }
        )
    )
    for name in ("NUXEO_USERNAME", "NUXEO_PASSWORD", "NUXEO_AUTH_METHOD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NUXEO_URL", "http://nuxeo.test/nuxeo")
    monkeypatch.setenv("NUXEO_OAUTH_CLIENT_ID", "c")
    monkeypatch.setenv("NUXEO_OAUTH_CLIENT_SECRET", "s")

    config = MCPAuthConfig.load(config_path=saved, auth_method=AuthMethod.OAUTH2)

    assert config.servers["default"].auth_method == AuthMethod.OAUTH2


@pytest.mark.unit
def test_empty_auth_method_loads_as_basic(monkeypatch, tmp_path) -> None:
    """An empty NUXEO_AUTH_METHOD is unset, not an invalid method."""
    from nuxeo_mcp.config import AuthMethod, MCPAuthConfig

    monkeypatch.setenv("NUXEO_URL", "http://nuxeo.test/nuxeo")
    monkeypatch.setenv("NUXEO_USERNAME", "u")
    monkeypatch.setenv("NUXEO_PASSWORD", "p")
    monkeypatch.setenv("NUXEO_AUTH_METHOD", "")

    config = MCPAuthConfig.load(config_path=tmp_path / "none.json")

    assert config.servers["default"].auth_method == AuthMethod.BASIC


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, False),
        ("", False),
        ("false", False),
        ("0", False),
        ("off", False),
        ("true", True),
        (" TRUE ", True),
        ("1", True),
        ("yes", True),
        ("on", True),
    ],
)
def test_read_only_from_env(monkeypatch, value, expected) -> None:
    """NUXEO_MCP_READ_ONLY accepts the usual boolean spellings; unset is off."""
    from nuxeo_mcp.config import read_only_from_env

    monkeypatch.delenv("NUXEO_MCP_READ_ONLY", raising=False)
    if value is not None:
        monkeypatch.setenv("NUXEO_MCP_READ_ONLY", value)
    assert read_only_from_env() is expected


@pytest.mark.unit
def test_read_only_from_env_rejects_a_typo(monkeypatch) -> None:
    """A typo stops startup rather than silently exposing the write tools."""
    from nuxeo_mcp.config import read_only_from_env

    monkeypatch.setenv("NUXEO_MCP_READ_ONLY", "ture")
    with pytest.raises(ValueError, match="supported: true, false"):
        read_only_from_env()
