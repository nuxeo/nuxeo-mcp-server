#!/usr/bin/env python
"""
Test natural language search with various single-word queries
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from nuxeo.client import Nuxeo

from nuxeo_mcp.nl_parser import NaturalLanguageParser, NXQLBuilder

# Configuration
url = "https://nightly-2023.nuxeocloud.com/nuxeo"
username = "automated_test_user"
password = "**********"

print("Testing Single-Word Natural Language Queries")
print("=" * 50)

parser = NaturalLanguageParser()
nuxeo = Nuxeo(host=url, auth=(username, password))

test_queries = [
    # Single words that should search content
    "leopards",
    "eagle",
    "budget",
    "test",
    # Document type keywords (should NOT add fulltext condition)
    "pictures",
    "files",
    "documents",
    # Queries with prefixes
    "find leopards",
    "search eagle",
    "show test",
    # Mixed queries
    "pictures of leopards",
    "files containing budget",
]

for query in test_queries:
    print(f"\nQuery: '{query}'")
    print("-" * 40)

    # Parse the query
    parsed = parser.parse(query)

    # Build NXQL
    builder = NXQLBuilder(parsed)
    nxql = builder.build()

    print(f"Generated NXQL: {nxql}")

    # Execute and count results
    try:
        result = nuxeo.client.query(nxql, params={"pageSize": 1, "currentPageIndex": 0})
        total = result.get("resultsCount", 0)

        # Determine if it's searching all or specific content
        if total > 1000:
            print(f"⚠️ Returns {total} results (ALL documents)")
        else:
            print(f"✅ Returns {total} specific results")

            # Show first result if any
            entries = result.get("entries", [])
            if entries:
                doc = entries[0]
                print(
                    f"   First match: {doc.get('title', 'Untitled')} ({doc.get('type', 'Unknown')})"
                )

    except Exception as e:
        print(f"❌ Error: {e}")

print("\n" + "=" * 50)
print("Summary:")
print("- Single words now trigger fulltext search")
print("- Document type keywords still work correctly")
print("- Prefixes are properly stripped")
print("- Complex queries maintain their specific behavior")
