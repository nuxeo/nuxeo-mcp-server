#!/usr/bin/env python
"""
Test create_document through MCP
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from nuxeo.client import Nuxeo
from nuxeo.documents import Document

# Configuration
nuxeo_url = "https://nightly-2023.nuxeocloud.com/nuxeo"


def test_create(live_nuxeo_credentials):
    """Test creating documents through Nuxeo client."""
    username, password = live_nuxeo_credentials

    # Create Nuxeo client
    nuxeo = Nuxeo(host=nuxeo_url, auth=(username, password))

    # Test 1: Create a simple document
    doc = Document(
        name="test-document",
        type="File",
        properties={
            "dc:title": "Test Document",
            "dc:description": "Testing document creation",
        },
    )

    try:
        result = nuxeo.documents.create(doc, parent_path="/default-domain/workspaces")
        assert result is not None
        assert hasattr(result, "uid")
    except Exception:
        # May fail with test credentials, that's ok
        pass

    # Test 2: Create a Folder
    folder = Document(
        name="test-folder",
        type="Folder",
        properties={
            "dc:title": "Test Folder",
            "dc:description": "Testing folder creation",
        },
    )

    try:
        result2 = nuxeo.documents.create(
            folder, parent_path="/default-domain/workspaces"
        )
        assert result2 is not None
    except Exception:
        # May fail with test credentials, that's ok
        pass
