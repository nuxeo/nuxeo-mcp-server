#!/usr/bin/env python
"""
Debug natural language parsing
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import json

from nuxeo_mcp.nl_parser import NaturalLanguageParser, NXQLBuilder

print("Testing Natural Language Parser")
print("=" * 50)

parser = NaturalLanguageParser()

test_queries = ["documents modified today", "pictures", "files in workspaces"]

for query in test_queries:
    print(f"\nQuery: '{query}'")
    print("-" * 40)

    # Parse to structured format
    parsed = parser.parse(query)

    print("Parsed structure:")
    print(f"  Intent: {parsed.intent}")
    print(f"  Doc type: {parsed.doc_type}")
    print(f"  Conditions: {parsed.conditions}")
    print(f"  Order by: {parsed.order_by}")
    print(f"  Limit: {parsed.limit}")

    # Build NXQL
    builder = NXQLBuilder(parsed)
    nxql = builder.build()
    print(f"\nNXQL: {nxql}")

    # Build Elasticsearch query
    es_query = parser.build_elasticsearch_query(parsed, "nuxeo")
    print(f"\nElasticsearch query:")
    print(json.dumps(es_query, indent=2))
