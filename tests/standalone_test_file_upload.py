#!/usr/bin/env python
"""
Test file upload functionality
"""

import os
import sys

# Common locations to check for test images
possible_paths = [
    "image.png",  # Current directory
    "/tmp/image.png",  # Temp directory
    "~/Desktop/image.png",  # Desktop
    "~/Downloads/image.png",  # Downloads
    "~/Documents/image.png",  # Documents
    "~/Pictures/image.png",  # Pictures
    "~/nuxeo/mcp/nx-mcp/image.png",  # Project directory
]

print("Checking for image.png in common locations...")
print("=" * 50)

found_files = []
for path in possible_paths:
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"✅ FOUND: {path} ({size} bytes)")
        found_files.append(path)
    else:
        print(f"❌ Not found: {path}")

print("\n" + "=" * 50)
if found_files:
    print(f"\nFound {len(found_files)} file(s). You can use any of these paths:")
    for path in found_files:
        print(f"  - {path}")
else:
    print("\n⚠️  No image.png file found in common locations.")
    print("\nTo test file upload, you need to:")
    print("1. Create or download an image file")
    print("2. Note its full path")
    print("3. Use that path in the create_document command")

print("\n" + "=" * 50)
print("Creating a test image for you...")

# Create a simple test image using PIL if available
try:
    from PIL import Image

    # Create a simple test image
    img = Image.new("RGB", (100, 100), color="red")
    test_path = "/tmp/test_image.png"
    img.save(test_path)
    print(f"✅ Created test image at: {test_path}")
    print(f"   Size: {os.path.getsize(test_path)} bytes")
    print(f"\nYou can now use this command in Claude:")
    print(
        f'Create a Picture document with the file {test_path} titled "Test Image" in /default-domain/workspaces'
    )

except ImportError:
    print("❌ PIL not installed. Creating a simple text file instead...")
    test_path = "/tmp/test_file.txt"
    with open(test_path, "w") as f:
        f.write("This is a test file for upload testing")
    print(f"✅ Created test file at: {test_path}")
    print(f"\nYou can use this command in Claude:")
    print(
        f'Create a File document with the file {test_path} titled "Test File" in /default-domain/workspaces'
    )
