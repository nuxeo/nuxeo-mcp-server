#!/usr/bin/env python3
"""Generate the tool reference from the live FastMCP schema.

Every peer MCP server we looked at ships documentation that disagrees with its
code -- one publishes a registry manifest declaring ten tools that do not exist
in its source. Hand-maintained tool tables drift the moment a tool is renamed,
so this reads the registered schema instead and rewrites the tables in place
between the generated markers.

Usage:
    uv run python scripts/generate_tool_reference.py        # rewrite
    uv run python scripts/generate_tool_reference.py --check # fail if stale
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

BEGIN = "<!-- BEGIN GENERATED TOOLS -->"
END = "<!-- END GENERATED TOOLS -->"


async def _collect() -> List[Dict[str, Any]]:
    from fastmcp import Client, FastMCP

    from nuxeo_mcp.tools import register_tools

    server = FastMCP("nuxeo-mcp")
    register_tools(server, MagicMock())

    async with Client(server) as client:
        return [
            {
                "name": tool.name,
                "description": (tool.description or "").strip().split("\n")[0],
                "annotations": tool.annotations,
            }
            for tool in sorted(await client.list_tools(), key=lambda t: t.name)
        ]


def _render(tools: List[Dict[str, Any]]) -> str:
    def mark(value: Any) -> str:
        return "yes" if value else "no"

    lines = [
        BEGIN,
        "",
        f"{len(tools)} tools, generated from the registered MCP schema by "
        "`scripts/generate_tool_reference.py` -- do not edit by hand.",
        "",
        "| Tool | Read-only | Destructive | Open-world | Description |",
        "|------|-----------|-------------|------------|-------------|",
    ]
    for tool in tools:
        a = tool["annotations"]
        lines.append(
            f"| `{tool['name']}` | {mark(a.read_only_hint)} | "
            f"{mark(a.destructive_hint)} | {mark(a.open_world_hint)} | "
            f"{tool['description']} |"
        )
    lines += ["", END]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if out of date")
    args = parser.parse_args()

    table = _render(asyncio.run(_collect()))
    stale: List[str] = []

    for relative in ("AGENTS.md", "README.md", "USAGE.md", "llm.txt"):
        path = ROOT / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if BEGIN not in text or END not in text:
            continue
        head, _, rest = text.partition(BEGIN)
        _, _, tail = rest.partition(END)
        updated = head + table + tail
        if updated == text:
            continue
        if args.check:
            stale.append(relative)
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"updated {relative}")

    if stale:
        print(
            "Tool reference is out of date in: "
            + ", ".join(stale)
            + "\nRun: uv run python scripts/generate_tool_reference.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
