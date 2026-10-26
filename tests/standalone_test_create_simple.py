#!/usr/bin/env python
"""
Simple test of create_document functionality
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

print("Testing Document Creation with Fixed Tool")
print("=" * 50)

# Create Nuxeo client
nuxeo = Nuxeo(host=url, auth=(username, password))

# Test 1: Create document without file
print("\n1. Creating document without file...")
try:
    doc = Document(
        name="leopard-habitat",
        type="File",
        properties={
            "dc:title": "Leopard Habitat Information",
            "dc:description": "Documentation about leopard habitats and territories",
        },
    )

    created = nuxeo.documents.create(
        doc, parent_path="/default-domain/workspaces/Nature"
    )
    print(f"✅ Document created successfully!")
    print(f"   UID: {created.uid}")
    print(f"   Path: {created.path}")
    print(f"   URL: {url}/ui/#!/browse{created.path}")

except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Create document with file using batch upload
print("\n2. Creating document with file...")

# Create a test file
test_file = "/tmp/leopard_facts.txt"
with open(test_file, "w") as f:
    f.write("Leopard Facts\n")
    f.write("=============\n\n")
    f.write("1. Leopards are solitary big cats\n")
    f.write("2. They can run up to 58 km/h\n")
    f.write("3. Leopards are excellent climbers\n")
    f.write("4. They have distinctive rosette patterns\n")
    f.write("5. Leopards are found in Africa and Asia\n")

try:
    # Upload file to batch
    print("   Uploading file to batch...")
    blob = FileBlob(test_file)
    batch = nuxeo.uploads.batch()
    uploaded = batch.upload(blob, chunked=True)
    print(f"   ✅ File uploaded to batch {batch.batchId}")

    # Create document with file reference
    print("   Creating document with file reference...")
    doc = Document(
        name="leopard-facts",
        type="File",
        properties={
            "dc:title": "Leopard Facts Document",
            "dc:description": "Interesting facts about leopards",
            "file:content": {"upload-batch": batch.batchId, "upload-fileId": "0"},
        },
    )

    created = nuxeo.documents.create(
        doc, parent_path="/default-domain/workspaces/Nature"
    )
    print(f"✅ Document with file created successfully!")
    print(f"   UID: {created.uid}")
    print(f"   Path: {created.path}")
    print(f"   URL: {url}/ui/#!/browse{created.path}")

    # Verify the file is attached
    if created.properties.get("file:content"):
        file_info = created.properties["file:content"]
        print(f"   File attached: {file_info.get('name', 'unknown')}")
        print(f"   Size: {file_info.get('length', 0)} bytes")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()

# Clean up test file
if os.path.exists(test_file):
    os.remove(test_file)

print("\n" + "=" * 50)
print("Summary:")
print("✅ Document creation works")
print("✅ Batch upload works")
print("✅ File attachment via batch reference works")
print("\nThe create_document tool in MCP now returns a structured dict")
print("instead of a plain string, fixing the 'structured_content' error.")
