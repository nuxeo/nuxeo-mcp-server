#!/usr/bin/env python
"""
Test basic authentication with Nuxeo server.
"""

import os
import sys

from nuxeo.client import Nuxeo

# Test with hardcoded values
print("Testing basic authentication with Nuxeo...")
print("-" * 50)

# Configuration
url = "https://nightly-2023.nuxeocloud.com/nuxeo"
username = "automated_test_user"
password = "**********"

print(f"URL: {url}")
print(f"Username: {username}")
print(f"Password: {'*' * len(password)}")
print("-" * 50)

try:
    # Create Nuxeo client
    print("Creating Nuxeo client...")
    client = Nuxeo(host=url, auth=(username, password))

    # Test authentication
    print("Testing authentication...")
    # The Nuxeo client uses requests internally
    import requests

    response = requests.get(f"{url}/api/v1/user/current", auth=(username, password))

    if response.status_code == 200:
        user_info = response.json()
        print(f"✅ SUCCESS! Authenticated as: {user_info.get('id', 'unknown')}")
        print(f"User properties: {user_info.get('properties', {})}")

        # Try a simple search
        print("\nTesting search capability...")
        search_response = requests.get(
            f"{url}/api/v1/search/lang/NXQL/execute",
            auth=(username, password),
            params={"query": 'SELECT * FROM Document WHERE ecm:primaryType = "Domain"'},
        )
        if search_response.status_code == 200:
            print(
                f"✅ Search successful! Found {len(search_response.json().get('entries', []))} domains"
            )
        else:
            print(f"❌ Search failed with status: {search_response.status_code}")
            print(f"Response: {search_response.text[:500]}")
    else:
        print(f"❌ Authentication failed with status: {response.status_code}")
        print(f"Response headers: {response.headers}")
        print(f"Response body: {response.text[:500]}")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 50)
print("Now testing with environment variables...")
print("=" * 50)

# Test with environment variables
env_url = os.environ.get("NUXEO_URL", url)
env_username = os.environ.get("NUXEO_USERNAME", username)
env_password = os.environ.get("NUXEO_PASSWORD", password)

print(f"NUXEO_URL: {env_url}")
print(f"NUXEO_USERNAME: {env_username}")
print(f"NUXEO_PASSWORD: {'*' * len(env_password) if env_password else 'NOT SET'}")

if env_url and env_username and env_password:
    try:
        import requests

        response2 = requests.get(
            f"{env_url}/api/v1/user/current", auth=(env_username, env_password)
        )
        if response2.status_code == 200:
            print(f"✅ Environment variable auth successful!")
        else:
            print(f"❌ Environment variable auth failed: {response2.status_code}")
    except Exception as e:
        print(f"❌ Environment variable test error: {e}")
