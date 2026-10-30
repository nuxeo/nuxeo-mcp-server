"""Tests for the file_path policy of the upload tools."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nuxeo_mcp.file_access import FilePathPolicy
from nuxeo_mcp.tools import register_tools


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    """An upload folder holding one file, beside a secret outside it."""
    folder = tmp_path / "uploads"
    folder.mkdir()
    (folder / "report.pdf").write_bytes(b"%PDF")
    (tmp_path / "secret.key").write_bytes(b"key")
    return folder


def _policy(folder: Path) -> FilePathPolicy:
    return FilePathPolicy.for_transport(os.path.realpath(folder), stdio=False)


@pytest.mark.unit
@pytest.mark.parametrize("name", ["report.pdf", "./report.pdf", "sub/../report.pdf"])
def test_upload_dir_accepts_a_file_inside(upload_dir: Path, name: str) -> None:
    """A relative path is resolved against the upload folder."""
    (upload_dir / "sub").mkdir(exist_ok=True)
    real = _policy(upload_dir).resolve(name)
    assert real == os.path.realpath(upload_dir / "report.pdf")


@pytest.mark.unit
def test_upload_dir_accepts_an_absolute_path_inside(upload_dir: Path) -> None:
    """An absolute path inside the folder is accepted."""
    path = str(upload_dir / "report.pdf")
    assert _policy(upload_dir).resolve(path) == os.path.realpath(path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "name", ["../secret.key", "/proc/self/environ", "/etc/passwd", "~/.ssh/id_rsa"]
)
def test_upload_dir_refuses_a_path_outside(upload_dir: Path, name: str) -> None:
    """``..``, absolute paths and ``~`` cannot leave the folder."""
    with pytest.raises(ValueError, match="outside the upload folder"):
        _policy(upload_dir).resolve(name)


@pytest.mark.unit
def test_upload_dir_refuses_a_symlink_out(upload_dir: Path) -> None:
    """A symlink inside the folder pointing out of it is refused."""
    (upload_dir / "link").symlink_to(upload_dir.parent / "secret.key")
    with pytest.raises(ValueError, match="outside the upload folder"):
        _policy(upload_dir).resolve("link")


@pytest.mark.unit
def test_upload_dir_refuses_a_sibling_with_a_common_prefix(tmp_path: Path) -> None:
    """``/x/uploads-other`` is not inside ``/x/uploads``."""
    (tmp_path / "uploads").mkdir()
    other = tmp_path / "uploads-other"
    other.mkdir()
    (other / "f").write_bytes(b"x")
    with pytest.raises(ValueError, match="outside the upload folder"):
        _policy(tmp_path / "uploads").resolve(str(other / "f"))


@pytest.mark.unit
@pytest.mark.parametrize("name", ["missing.pdf", "."])
def test_upload_dir_requires_a_regular_file(upload_dir: Path, name: str) -> None:
    """A missing file or a folder is not uploaded."""
    with pytest.raises(ValueError, match="File not found"):
        _policy(upload_dir).resolve(name)


@pytest.mark.unit
def test_http_without_upload_dir_refuses_every_path(upload_dir: Path) -> None:
    """Over HTTP with no folder configured, file_path reads nothing."""
    policy = FilePathPolicy.for_transport(None, stdio=False)
    assert policy.mode == "disabled"
    with pytest.raises(ValueError, match="file_path is disabled"):
        policy.resolve(str(upload_dir / "report.pdf"))


@pytest.mark.unit
def test_stdio_without_upload_dir_accepts_any_file(upload_dir: Path) -> None:
    """Over stdio the server runs on the user's machine: any file is accepted."""
    policy = FilePathPolicy.for_transport(None, stdio=True)
    assert policy.mode == "any"
    secret = str(upload_dir.parent / "secret.key")
    assert policy.resolve(secret) == os.path.realpath(secret)


@pytest.mark.unit
def test_stdio_with_upload_dir_is_restricted(upload_dir: Path) -> None:
    """A configured folder restricts stdio too."""
    policy = FilePathPolicy.for_transport(os.path.realpath(upload_dir), stdio=True)
    assert policy.mode == "upload_dir"
    with pytest.raises(ValueError, match="outside the upload folder"):
        policy.resolve("../secret.key")


def _tools(policy: FilePathPolicy) -> tuple:
    """Register the tools on a capturing fake; return them and the Nuxeo mock."""
    captured = {}

    class FakeMCP:
        def tool(self, **kwargs):
            def decorator(fn):
                captured[kwargs["name"]] = fn
                return fn

            return decorator

    nuxeo = MagicMock()
    register_tools(FakeMCP(), nuxeo, policy)
    return captured, nuxeo


@pytest.mark.unit
@pytest.mark.parametrize(
    "tool,args",
    [
        (
            "nuxeo_create_document",
            {"name": "n", "type": "File", "properties": {}, "parent_path": "/"},
        ),
        ("nuxeo_execute_operation", {"operation_id": "Op", "input_type": "file"}),
    ],
)
def test_tools_refuse_a_path_before_uploading(tool: str, args: dict) -> None:
    """A refused file_path never reaches the Nuxeo upload."""
    tools, nuxeo = _tools(FilePathPolicy())
    with patch("nuxeo.models.FileBlob") as blob:
        with pytest.raises(ValueError, match="file_path is disabled"):
            tools[tool](file_path="/proc/self/environ", **args)
    blob.assert_not_called()
    nuxeo.uploads.batch.assert_not_called()


@pytest.mark.unit
def test_create_document_uploads_the_resolved_path(upload_dir: Path) -> None:
    """The upload opens the real path that was checked."""
    tools, nuxeo = _tools(_policy(upload_dir))
    with patch("nuxeo.models.FileBlob") as blob, patch("nuxeo_mcp.tools.Document"):
        tools["nuxeo_create_document"](
            name="n",
            type="File",
            properties={},
            parent_path="/",
            file_path="report.pdf",
        )
    blob.assert_called_once_with(os.path.realpath(upload_dir / "report.pdf"))


@pytest.mark.unit
def test_upload_keeps_the_callers_file_name(upload_dir: Path) -> None:
    """A symlink is read through its target but uploaded under its own name."""
    (upload_dir / "latest.pdf").symlink_to(upload_dir / "report.pdf")
    tools, nuxeo = _tools(FilePathPolicy.for_transport(None, stdio=True))
    with patch("nuxeo.models.FileBlob") as blob, patch("nuxeo_mcp.tools.Document"):
        tools["nuxeo_create_document"](
            name="n",
            type="File",
            properties={},
            parent_path="/",
            file_path=str(upload_dir / "latest.pdf"),
        )
    blob.assert_called_once_with(os.path.realpath(upload_dir / "report.pdf"))
    assert blob.return_value.name == "latest.pdf"
