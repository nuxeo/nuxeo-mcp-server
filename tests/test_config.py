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


@pytest.mark.unit
def test_upload_dir_from_env(monkeypatch, tmp_path) -> None:
    """Unset is None; a folder is returned as its real path."""
    import os

    from nuxeo_mcp.config import upload_dir_from_env

    monkeypatch.delenv("NUXEO_MCP_UPLOAD_DIR", raising=False)
    assert upload_dir_from_env() is None
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    monkeypatch.setenv("NUXEO_MCP_UPLOAD_DIR", str(tmp_path / "link"))
    assert upload_dir_from_env() == os.path.realpath(tmp_path / "real")


@pytest.mark.unit
def test_upload_dir_from_env_rejects_a_missing_folder(monkeypatch, tmp_path) -> None:
    """A missing folder stops startup rather than changing what file_path reads."""
    from nuxeo_mcp.config import upload_dir_from_env

    monkeypatch.setenv("NUXEO_MCP_UPLOAD_DIR", str(tmp_path / "nope"))
    with pytest.raises(ValueError, match="is not a directory"):
        upload_dir_from_env()
