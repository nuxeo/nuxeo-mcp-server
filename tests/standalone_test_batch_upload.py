#!/usr/bin/env python
"""
Test batch upload directly with Nuxeo
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from nuxeo.client import Nuxeo
from nuxeo.documents import Document

# Configuration
url = "https://nightly-2023.nuxeocloud.com/nuxeo"
username = "automated_test_user"
password = "**********"
test_file = "/tmp/test_image.png"

print("Testing Batch Upload to Nuxeo")
print("=" * 50)
print(f"Server: {url}")
print(f"File: {test_file}")
print(f"File exists: {os.path.exists(test_file)}")
print(
    f"File size: {os.path.getsize(test_file) if os.path.exists(test_file) else 'N/A'} bytes"
)
print("=" * 50)

try:
    # Create Nuxeo client
    print("\n1. Connecting to Nuxeo...")
    nuxeo = Nuxeo(host=url, auth=(username, password))

    # Test authentication
    import requests

    response = requests.get(f"{url}/api/v1/me", auth=(username, password))
    if response.status_code == 200:
        print("✅ Authentication successful")
    else:
        print(f"❌ Authentication failed: {response.status_code}")
        sys.exit(1)

    # Create batch and upload file
    print("\n2. Creating batch upload...")
    from nuxeo.models import FileBlob

    # Create a FileBlob object which has the required attributes
    blob = FileBlob(test_file)
    batch = nuxeo.uploads.batch()
    print(f"✅ Batch created with ID: {batch.batchId}")

    print("\n3. Uploading file to batch...")
    uploaded = batch.upload(blob, chunked=True)
    print(f"✅ File uploaded to batch")

    # Create a Picture document with the uploaded file
    print("\n4. Creating Picture document...")
    doc = Document(
        name="test-batch-upload",
        type="Picture",
        properties={
            "dc:title": "Test Batch Upload",
            "dc:description": "Testing batch upload functionality",
            "file:content": {"upload-batch": batch.batchId, "upload-fileId": "0"},
        },
    )

    # Create in workspaces
    parent_path = "/default-domain/workspaces"
    created_doc = nuxeo.documents.create(doc, parent_path=parent_path)

    print(f"✅ Document created successfully!")
    print(f"   - Path: {created_doc.path}")
    print(f"   - UID: {created_doc.uid}")
    print(f"   - Title: {created_doc.properties.get('dc:title')}")

    print("\n✅ SUCCESS! Batch upload works correctly.")
    print(f"\nYou can view the document at:")
    print(f"{url}/ui/#!/browse{created_doc.path}")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()
