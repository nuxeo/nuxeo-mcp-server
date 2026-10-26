#!/usr/bin/env python
"""
Test authentication with various Nuxeo API endpoints.
"""

import json

import requests

# Configuration
url = "https://nightly-2023.nuxeocloud.com/nuxeo"
username = "automated_test_user"
password = "**********"

print("Testing Nuxeo Authentication")
print("=" * 50)
print(f"Server: {url}")
print(f"Username: {username}")
print(f"Password: {'*' * len(password)}")
print("=" * 50)

# Test different endpoints
endpoints = [
    ("/api/v1/me", "Current user (me)"),
    ("/api/v1/user/current", "Current user"),
    ("/api/v1/user/" + username, "User by username"),
    ("/api/v1/repo/default", "Repository info"),
    ("/api/v1/path/", "Root path"),
    ("/automation", "Automation API"),
    ("/site/api/v1/me", "Site API - me"),
]

for endpoint, description in endpoints:
    full_url = url + endpoint
    print(f"\nTesting: {description}")
    print(f"URL: {full_url}")

    try:
        response = requests.get(full_url, auth=(username, password), timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            print("✅ SUCCESS!")
            try:
                data = response.json()
                if "entity-type" in data:
                    print(f"Entity type: {data['entity-type']}")
                if "id" in data:
                    print(f"ID: {data['id']}")
                if "username" in data:
                    print(f"Username: {data['username']}")
            except:
                print(f"Response: {response.text[:200]}")
        elif response.status_code == 401:
            print("❌ UNAUTHORIZED - Check credentials")
        elif response.status_code == 404:
            print("❌ NOT FOUND - Endpoint doesn't exist or user not found")
            try:
                error_data = response.json()
                if "message" in error_data:
                    print(f"Message: {error_data['message']}")
            except:
                pass
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text[:200]}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")

print("\n" + "=" * 50)
print("Testing NXQL Query with Authentication")
print("=" * 50)

# Test a simple NXQL query
query_url = f"{url}/api/v1/search/lang/NXQL/execute"
query = "SELECT * FROM Document WHERE ecm:primaryType = 'Workspace' AND ecm:isVersion = 0 AND ecm:isTrashed = 0"

print(f"Query: {query}")
try:
    response = requests.get(
        query_url,
        auth=(username, password),
        params={"query": query, "pageSize": 1},
        timeout=10,
    )

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        print("✅ Query successful!")
        data = response.json()
        print(f"Results found: {data.get('resultsCount', 0)}")
    elif response.status_code == 401:
        print("❌ UNAUTHORIZED - Authentication failed")
    else:
        print(f"❌ Query failed: {response.status_code}")
        print(f"Response: {response.text[:500]}")

except requests.exceptions.RequestException as e:
    print(f"❌ Request failed: {e}")

print("\n" + "=" * 50)
print("Testing with NO authentication (to verify it's needed)")
print("=" * 50)

try:
    response = requests.get(f"{url}/api/v1/repo/default", timeout=10)
    print(f"Status without auth: {response.status_code}")
    if response.status_code == 401:
        print("✅ Server correctly requires authentication")
    elif response.status_code == 200:
        print("⚠️  Server allows unauthenticated access!")
except Exception as e:
    print(f"Error: {e}")
