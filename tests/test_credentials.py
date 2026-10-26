"""
Test credentials management module.

This module handles prompting for and caching test credentials
to avoid hardcoding sensitive information in test files.
"""

import getpass
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

# Try to load .env file if it exists
try:
    from dotenv import load_dotenv

    # Look for .env file in the project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded credentials from .env file: {env_path}")
except ImportError:
    pass  # python-dotenv not installed

# Cache credentials for the session
_cached_credentials: Optional[Tuple[str, str]] = None


def get_test_credentials(prompt_prefix: str = "") -> Tuple[str, str]:
    """
    Get test credentials either from environment variables or by prompting the user.

    Credentials are cached for the duration of the test session to avoid
    repeated prompts.

    :param prompt_prefix: Optional prefix for the prompt messages
    :return: Tuple of (username, password)
    """
    global _cached_credentials

    # Return cached credentials if available
    if _cached_credentials is not None:
        return _cached_credentials

    # First check environment variables
    username = os.environ.get("NUXEO_TEST_USERNAME")
    password = os.environ.get("NUXEO_TEST_PASSWORD")

    # If not in environment, prompt the user
    if not username or not password:
        # Check if we're in pytest and can't do interactive input
        # In that case, provide instructions and use dummy credentials
        if hasattr(sys, "_called_from_test") or "pytest" in sys.modules:
            # We're in pytest but don't have credentials
            if not username and not password:
                print("\n" + "=" * 60)
                print("NUXEO TEST CREDENTIALS REQUIRED")
                print("=" * 60)
                print("\nTo run tests against the live Nuxeo server, please provide")
                print("credentials using one of these methods:")
                print("\n1. Set environment variables:")
                print("   export NUXEO_TEST_USERNAME='your_username'")
                print("   export NUXEO_TEST_PASSWORD='your_password'")
                print("   python -m pytest tests/")
                print("\n2. Run pytest with -s flag to allow interactive input:")
                print("   python -m pytest tests/ -s")
                print("\n3. Create a .env file with:")
                print("   NUXEO_TEST_USERNAME=your_username")
                print("   NUXEO_TEST_PASSWORD=your_password")
                print(
                    "\nUsing dummy credentials for now (tests requiring auth will fail)"
                )
                print("=" * 60 + "\n")
                username = "dummy_user"
                password = "dummy_pass"
        else:
            # We can do interactive input
            print("\n" + "=" * 60)
            print("Nuxeo Test Authentication Required")
            print("=" * 60)
            if prompt_prefix:
                print(f"{prompt_prefix}")
            print("Please enter your credentials for the Nuxeo test server.")
            print(
                "(You can also set NUXEO_TEST_USERNAME and NUXEO_TEST_PASSWORD environment variables)"
            )
            print("-" * 60)

            if not username:
                username = input("Username: ").strip()
            if not password:
                password = getpass.getpass("Password: ").strip()

            print("=" * 60 + "\n")

    # Cache the credentials
    _cached_credentials = (username, password)

    return username, password


def clear_cached_credentials():
    """Clear the cached credentials (useful for testing)."""
    global _cached_credentials
    _cached_credentials = None


def prompt_for_credentials_if_needed():
    """
    Check if credentials are available and prompt if needed.
    This should be called early in the test run.
    """
    # Check if credentials are already available
    if os.environ.get("NUXEO_TEST_USERNAME") and os.environ.get("NUXEO_TEST_PASSWORD"):
        return True

    # Try to prompt
    try:
        # Try to get credentials - this will prompt if possible
        username, password = get_test_credentials()
        if username != "dummy_user":
            # Set them in environment for this session
            os.environ["NUXEO_TEST_USERNAME"] = username
            os.environ["NUXEO_TEST_PASSWORD"] = password
            return True
    except Exception:
        pass

    return False
