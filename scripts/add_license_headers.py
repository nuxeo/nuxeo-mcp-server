"""Add the Apache 2.0 license header to every tracked Python file missing it.

Usage:
    uv run python scripts/add_license_headers.py          # add
    uv run python scripts/add_license_headers.py --check  # fail if one is missing
"""

import subprocess
import sys
from pathlib import Path

HEADER = """\
# (C) Copyright 2026 Hyland (https://hyland.com/) and others.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
MARKER = "Licensed under the Apache License, Version 2.0"


def with_header(text: str) -> str:
    """Insert the header after a shebang or encoding line, if any."""
    lines = text.splitlines(keepends=True)
    keep = 0
    while keep < len(lines) and (
        lines[keep].startswith("#!") or "coding" in lines[keep][:30]
    ):
        keep += 1
    head = "".join(lines[:keep])
    body = "".join(lines[keep:]).lstrip("\n")
    return head + HEADER + ("\n" + body if body else "")


def main() -> int:
    files = subprocess.run(
        ["git", "ls-files", "*.py"], capture_output=True, text=True, check=True
    ).stdout.split()
    missing = [f for f in files if MARKER not in Path(f).read_text()[:2000]]
    if "--check" in sys.argv:
        for f in missing:
            print(f"missing license header: {f}")
        return 1 if missing else 0
    for f in missing:
        path = Path(f)
        path.write_text(with_header(path.read_text()))
    print(f"added the header to {len(missing)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
