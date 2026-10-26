#!/usr/bin/env python
"""
Simple test of the fixed upload functionality
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from nuxeo.client import Nuxeo
from nuxeo.documents import Document
from nuxeo.models import FileBlob

# Configuration
url = "https://nightly-2023.nuxeocloud.com/nuxeo"
username = "automated_test_user"
password = "**********"

print("Testing Fixed Upload Functionality")
print("=" * 50)

# Test files to try
test_files = [
    "~/Downloads/image.png",  # Your actual image
    "/tmp/test_image.png",  # Test image we created
]

# Find which file exists
test_file = None
for f in test_files:
    if os.path.exists(f):
        test_file = f
        print(f"✅ Using file: {test_file}")
        print(f"   Size: {os.path.getsize(test_file)} bytes")
        break

if not test_file:
    print("❌ No test file found!")
    sys.exit(1)

try:
    # Create Nuxeo client
    print("\nConnecting to Nuxeo...")
    nuxeo = Nuxeo(host=url, auth=(username, password))

    # Create batch and upload
    print("Creating batch upload...")
    blob = FileBlob(test_file)
    batch = nuxeo.uploads.batch()
    print(f"Batch ID: {batch.batchId}")

    print("Uploading file...")
    uploaded = batch.upload(blob, chunked=True)
    print("✅ File uploaded successfully!")

    # Create document
    print("\nCreating Picture document...")
    doc = Document(
        name=f"upload-test-{os.path.basename(test_file)}",
        type="Picture",
        properties={
            "dc:title": f"Upload Test - {os.path.basename(test_file)}",
            "dc:description": "Testing fixed batch upload",
            "file:content": {"upload-batch": batch.batchId, "upload-fileId": "0"},
        },
    )

    created = nuxeo.documents.create(doc, parent_path="/default-domain/workspaces")

    print("✅ SUCCESS! Document created:")
    print(f"   - Path: {created.path}")
    print(f"   - UID: {created.uid}")
    print(f"   - URL: {url}/ui/#!/browse{created.path}")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 50)
print("\nYou can now use these commands in Claude Desktop:")
print(
    f'1. Create a Picture document with the file {test_file} titled "My Picture" in /default-domain/workspaces'
)
if test_file != "~/Downloads/image.png" and os.path.exists("~/Downloads/image.png"):
    print(
        f'2. Create a Picture document with the file ~/Downloads/image.png titled "Downloads Image" in /default-domain/workspaces'
    )
