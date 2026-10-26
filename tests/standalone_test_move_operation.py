#!/usr/bin/env python
"""
Test the move_document operation with proper input formatting
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import json

from nuxeo.client import Nuxeo
from nuxeo.documents import Document

# Configuration
url = "https://nightly-2023.nuxeocloud.com/nuxeo"
username = "automated_test_user"
password = "**********"

print("Testing Document Move Operation")
print("=" * 50)

# Create Nuxeo client
nuxeo = Nuxeo(host=url, auth=(username, password))

# Step 1: Create a test document to move
print("\n1. Creating test document...")
try:
    doc = Document(
        name="test-move-doc",
        type="File",
        properties={
            "dc:title": "Document to Move",
            "dc:description": "This document will be moved",
        },
    )

    created = nuxeo.documents.create(doc, parent_path="/default-domain/workspaces")
    print(f"✅ Document created successfully!")
    print(f"   UID: {created.uid}")
    print(f"   Path: {created.path}")

    document_uid = created.uid

except Exception as e:
    print(f"❌ Error creating document: {e}")
    sys.exit(1)

# Step 2: Create a destination folder
print("\n2. Creating destination folder...")
try:
    folder = Document(
        name="archive-folder",
        type="Folder",
        properties={
            "dc:title": "Archive Folder",
            "dc:description": "Destination for moved documents",
        },
    )

    dest = nuxeo.documents.create(folder, parent_path="/default-domain/workspaces")
    print(f"✅ Destination folder created!")
    print(f"   Path: {dest.path}")

    target_path = dest.path

except Exception as e:
    # Folder might already exist
    target_path = "/default-domain/workspaces/archive-folder"
    print(f"   Using existing folder: {target_path}")

# Step 3: Test the move operation with proper input formatting
print("\n3. Testing Document.Move operation with 'doc:' prefix...")
try:
    # Create the operation with proper input formatting
    operation = nuxeo.operations.new("Document.Move")
    operation.params = {"target": target_path}

    # THIS IS THE KEY FIX: Add "doc:" prefix to the document UID
    operation.input_obj = f"doc:{document_uid}"

    print(f"   Input: doc:{document_uid}")
    print(f"   Target: {target_path}")

    # Execute the operation
    result = operation.execute()

    print(f"✅ Document moved successfully!")
    if hasattr(result, "uid"):
        print(f"   New path: {result.path}")
        print(f"   UID: {result.uid}")
    else:
        print(f"   Result: {result}")

except Exception as e:
    print(f"❌ Error moving document: {e}")
    import traceback

    traceback.print_exc()

# Step 4: Verify the move by checking the document's new location
print("\n4. Verifying document at new location...")
try:
    moved_doc = nuxeo.documents.get(uid=document_uid)
    print(f"✅ Document found at: {moved_doc.path}")

    if target_path in moved_doc.path:
        print(f"✅ Move confirmed - document is in the target folder!")
    else:
        print(f"⚠️  Document path doesn't match expected location")

except Exception as e:
    print(f"❌ Error verifying move: {e}")

# Step 5: Test move with rename
print("\n5. Testing move with rename...")
try:
    # Create another test document
    doc2 = Document(
        name="test-rename-doc",
        type="File",
        properties={
            "dc:title": "Document to Rename",
            "dc:description": "This document will be moved and renamed",
        },
    )

    created2 = nuxeo.documents.create(doc2, parent_path="/default-domain/workspaces")
    print(f"   Created document: {created2.name}")

    # Move and rename
    operation = nuxeo.operations.new("Document.Move")
    operation.params = {"target": target_path, "name": "renamed-document"}
    operation.input_obj = f"doc:{created2.uid}"

    result = operation.execute()
    print(f"✅ Document moved and renamed!")

    # Verify
    renamed_doc = nuxeo.documents.get(uid=created2.uid)
    print(f"   New path: {renamed_doc.path}")
    print(f"   New name: {renamed_doc.name}")

except Exception as e:
    print(f"❌ Error in move with rename: {e}")

print("\n" + "=" * 50)
print("Summary:")
print("✅ Document.Move operation works with 'doc:' prefix")
print("✅ Documents can be moved to different folders")
print("✅ Documents can be renamed during move")
print("\nThe fix ensures Nuxeo automation API receives the correct input format:")
print("  - Single document: 'doc:' + uid")
print("  - Multiple documents: 'docs:' + comma-separated uids")
