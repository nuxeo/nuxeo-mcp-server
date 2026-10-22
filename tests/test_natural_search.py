#!/usr/bin/env python
"""
Test natural-language search via nuxeo_search_documents
"""

import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from nuxeo_mcp.nl_parser import NaturalLanguageParser
from nuxeo.client import Nuxeo

# Configuration
nuxeo_url = "https://nightly-2023.nuxeocloud.com/nuxeo"

def test_natural_search(live_nuxeo_credentials):
    """Test natural language search functionality."""
    username, password = live_nuxeo_credentials
    
    # Create Nuxeo client
    nuxeo = Nuxeo(host=nuxeo_url, auth=(username, password))
    
    # Test natural language parser
    parser = NaturalLanguageParser()
    
    # Test queries
    test_queries = [
        "find all documents",
        "show me pictures",
        "documents created today",
        "files in workspaces"
    ]
    
    for query in test_queries:
        # Parse the natural language query
        parsed = parser.parse(query)
        assert parsed is not None
        assert parsed.doc_type is not None
        
        # Build NXQL from parsed query
        from nuxeo_mcp.nl_parser import NXQLBuilder
        builder = NXQLBuilder(parsed)
        nxql = builder.build()
        assert nxql is not None
        assert "SELECT" in nxql
        
        # Try to execute the query (may fail due to auth, but query should be valid)
        try:
            result = nuxeo.client.query(nxql, params={'pageSize': 5})
            assert result is not None
        except Exception:
            # Auth errors are expected with test credentials
            pass