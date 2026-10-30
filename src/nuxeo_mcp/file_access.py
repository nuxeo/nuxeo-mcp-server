"""Which files on the MCP server's own disk the upload tools may read.

``file_path`` names a file on the machine running this server, not on the
caller's. Over stdio that is the user's own machine. Over HTTP it lets any
caller upload, then read back with ``fetch_blob``, whatever the server process
can read: ``/proc/self/environ`` (holding ``NUXEO_PASSWORD``), the OAuth2 token
file and its key, SSH and cloud credentials, mounted secrets. So a path is
accepted only inside ``NUXEO_MCP_UPLOAD_DIR`` when it is set, anywhere over
stdio when it is not, and never over HTTP when it is not.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FilePathPolicy:
    """Decide whether a tool may read a ``file_path`` from the server's disk.

    Attributes:
        upload_dir: Real path of the only folder files may come from, or None
        allow_any: With no upload_dir, accept any path (stdio only)
    """

    upload_dir: Optional[str] = None
    allow_any: bool = False

    @classmethod
    def for_transport(cls, upload_dir: Optional[str], stdio: bool) -> "FilePathPolicy":
        """Build the policy for a transport and an optional upload folder."""
        return cls(upload_dir=upload_dir, allow_any=stdio and upload_dir is None)

    @property
    def mode(self) -> str:
        """``upload_dir``, ``any`` or ``disabled``, for /health and the log.

        The folder itself is left out: /health is public.
        """
        if self.upload_dir:
            return "upload_dir"
        return "any" if self.allow_any else "disabled"

    def resolve(self, file_path: str) -> str:
        """Return the real path to read, or raise ValueError if not allowed.

        Containment is checked on the real path, so ``..`` and symlinks cannot
        leave the folder, and before existence, so a refusal says nothing about
        files outside it. The real path is returned so the upload opens the file
        that was checked.
        """
        if self.upload_dir:
            joined = os.path.join(self.upload_dir, os.path.expanduser(file_path))
            real = os.path.realpath(joined)
            if os.path.commonpath([real, self.upload_dir]) != self.upload_dir:
                raise ValueError(
                    f"file_path {file_path!r} is outside the upload folder "
                    "(NUXEO_MCP_UPLOAD_DIR); give a path inside it"
                )
        elif self.allow_any:
            real = os.path.realpath(os.path.expanduser(file_path))
        else:
            raise ValueError(
                "file_path is disabled: this server runs over HTTP and "
                "NUXEO_MCP_UPLOAD_DIR is not set, so it reads no local files"
            )
        if not os.path.isfile(real):
            raise ValueError(f"File not found: {file_path}")
        return real
