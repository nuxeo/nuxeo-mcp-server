#!/usr/bin/env python
"""
Simple test to verify credential prompting works correctly.
Run this directly with: python tests/test_credential_prompt.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from test_credentials import clear_cached_credentials, get_test_credentials


def main():
    """Test the credential prompt system."""
    print("\n" + "=" * 60)
    print("Testing Credential Prompt System")
    print("=" * 60)

    # Clear any cached credentials
    clear_cached_credentials()

    # Test 1: Get credentials (should prompt)
    print("\nTest 1: Initial credential request (should prompt if not in env)")
    username1, password1 = get_test_credentials()
    print(f"✅ Got username: {username1}")
    print(f"✅ Got password: {'*' * len(password1)}")

    # Test 2: Get credentials again (should use cache)
    print("\nTest 2: Second request (should use cached credentials)")
    username2, password2 = get_test_credentials()
    assert username1 == username2, "Username should be cached"
    assert password1 == password2, "Password should be cached"
    print("✅ Credentials were cached correctly")

    # Test 3: Clear cache and get again
    print("\nTest 3: After clearing cache")
    clear_cached_credentials()
    print(
        "Cache cleared. Set NUXEO_TEST_USERNAME and NUXEO_TEST_PASSWORD to avoid re-prompting."
    )

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
    print(
        "\nTo use in pytest tests, the credentials will be prompted once per session."
    )
    print("You can also set these environment variables to avoid prompting:")
    print("  - NUXEO_TEST_USERNAME")
    print("  - NUXEO_TEST_PASSWORD")


if __name__ == "__main__":
    main()
