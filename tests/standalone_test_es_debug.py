#!/usr/bin/env python
"""
Debug Elasticsearch query generation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import requests
import json
from nuxeo_mcp.nl_parser import NaturalLanguageParser

# Test the natural language to ES conversion
print("Testing Natural Language to Elasticsearch Query Conversion")
print("=" * 50)

parser = NaturalLanguageParser()

test_queries = [
    "pictures",
    "documents modified today",
    "files in workspaces"
]

for query in test_queries:
    print(f"\nNatural query: '{query}'")
    print("-" * 40)
    
    try:
        # Parse to Elasticsearch (ACL enforcement is server-side; no apply_acl needed)
        es_query = parser.parse_to_elasticsearch(
            query,
            index="nuxeo",
            include_sort=True,
            include_pagination=True,
            include_highlight=True,
            source_includes=None
        )
        
        print("Generated ES query:")
        print(json.dumps(es_query, indent=2))
        
    except Exception as e:
        print(f"❌ Error parsing: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 50)
print("\nNow testing direct simple queries against ES passthrough:")
print("-" * 50)

# Test with simple direct queries
nuxeo_url = "https://nightly-2023.nuxeocloud.com/nuxeo"
auth = ("automated_test_user", "**********")

simple_queries = [
    {
        "name": "Match all documents",
        "query": {
            "query": {"match_all": {}},
            "size": 3
        }
    },
    {
        "name": "Search for Picture type",
        "query": {
            "query": {
                "term": {"ecm:primaryType": "Picture"}
            },
            "size": 3
        }
    },
    {
        "name": "Documents in workspaces",
        "query": {
            "query": {
                "prefix": {"ecm:path": "/default-domain/workspaces/"}
            },
            "size": 3
        }
    }
]

for test in simple_queries:
    print(f"\n{test['name']}:")
    
    try:
        response = requests.post(
            f"{nuxeo_url}/site/es/nuxeo/_search",
            json=test['query'],
            auth=auth,
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            hits = result.get('hits', {}).get('hits', [])
            print(f"✅ Found {len(hits)} results")
            for hit in hits[:2]:
                source = hit.get('_source', {})
                print(f"   - {source.get('dc:title', 'Untitled')} ({source.get('ecm:primaryType', 'Unknown')})")
        else:
            print(f"❌ Error: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Connection error: {e}")