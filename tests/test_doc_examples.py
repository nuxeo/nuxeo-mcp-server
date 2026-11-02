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

"""Tool calls shown in the docs must match the registered tool signatures.

Agents copy these examples. A renamed or removed parameter turns each copy
into a validation error, and nothing else catches the drift.
"""

import inspect
import re
from pathlib import Path
from typing import List, Set, Tuple
from unittest.mock import MagicMock

import pytest

from tests.helpers import Captured, capture_tools

ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    "README.md",
    "USAGE.md",
    "DEVELOPER.md",
    "llm.txt",
    "nuxeo_mcp_test_scenario.md",
]

_CALL = re.compile(r'use_tool\(\s*"nuxeo",\s*"(\w+)",\s*(\{.*?\})\s*\)', re.S)


def _tools() -> Captured:
    return capture_tools(MagicMock())


def _top_level_keys(body: str) -> Set[str]:
    keys: Set[str] = set()
    depth = 0
    for token in re.finditer(r'"([\w:-]+)"\s*:|[{}\[\]]', body):
        text = token.group(0)
        if text in "{[":
            depth += 1
        elif text in "}]":
            depth -= 1
        elif depth == 1:
            keys.add(token.group(1))
    return keys


def _examples() -> List[Tuple[str, str, Set[str]]]:
    found = []
    for doc in DOCS:
        path = ROOT / doc
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for match in _CALL.finditer(text):
            line = text[: match.start()].count("\n") + 1
            found.append(
                (f"{doc}:{line}", match.group(1), _top_level_keys(match.group(2)))
            )
    return found


EXAMPLES = _examples()


def test_docs_have_tool_examples() -> None:
    assert len(EXAMPLES) > 10


@pytest.mark.parametrize("where,name,keys", EXAMPLES, ids=[e[0] for e in EXAMPLES])
def test_doc_example_matches_tool_signature(
    where: str, name: str, keys: Set[str]
) -> None:
    tools = _tools()
    assert name in tools, f"{where}: no tool named {name}"

    params = inspect.signature(tools[name]).parameters
    required = {p for p, v in params.items() if v.default is inspect.Parameter.empty}

    assert keys <= set(params), f"{where}: unknown arguments {keys - set(params)}"
    assert required <= keys, f"{where}: missing arguments {required - keys}"


@pytest.mark.parametrize("doc", DOCS)
def test_docs_use_the_registered_resource_uris(doc: str) -> None:
    """nuxeo://document/... was never a registered resource."""
    path = ROOT / doc
    if path.exists():
        assert "nuxeo://document" not in path.read_text(encoding="utf-8")
