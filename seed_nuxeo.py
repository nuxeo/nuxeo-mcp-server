#!/usr/bin/env python3
# (C) Copyright 2026 Hyland (https://hyland.com/) and others.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Seed script for Nuxeo Repository.

This script initializes a Nuxeo repository with sample documents for testing:
- Creates a folder
- Creates a file document with a PDF attachment
- Creates a picture document with a PNG image
- Creates a note document with random text
"""

import os
import sys
import io
import random
import tempfile
import argparse
import logging
from typing import Dict, Any, Optional, Union, List, Tuple
from nuxeo.client import Nuxeo
from nuxeo.models import Document, FileBlob
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("nuxeo_seed")

# Sample text for generating random content
LOREM_IPSUM = """
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor 
incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud 
exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute 
irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla 
pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia 
deserunt mollit anim id est laborum.
"""

def generate_random_image(width: int = 400, height: int = 300) -> bytes:
    """
    Generate a PNG image with random shapes and return it as bytes.
    
    Args:
        width: Width of the image in pixels.
        height: Height of the image in pixels.
        
    Returns:
        Image data as bytes.
    """
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    for _ in range(20):  # draw 20 random shapes
        shape_type = random.choice(["line", "ellipse", "rectangle"])
        x0, y0 = random.randint(0, width), random.randint(0, height)
        x1, y1 = random.randint(0, width), random.randint(0, height)

        # Ensure (x0, y0) is top-left and (x1, y1) is bottom-right
        left, right = sorted([x0, x1])
        top, bottom = sorted([y0, y1])

        color = tuple(random.randint(0, 255) for _ in range(3))

        if shape_type == "line":
            draw.line((x0, y0, x1, y1), fill=color, width=2)
        elif shape_type == "ellipse":
            draw.ellipse((left, top, right, bottom), outline=color, width=2)
        elif shape_type == "rectangle":
            draw.rectangle((left, top, right, bottom), outline=color, width=2)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_random_pdf(num_lines: int = 25) -> bytes:
    """
    Generate a PDF with random text and return it as bytes.
    
    Args:
        num_lines: Number of lines of text to include in the PDF
        
    Returns:
        PDF data as bytes
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER

    for i in range(num_lines):
        x = 50
        y = height - 50 - i * 20
        text = " ".join(random.choices([
            "lorem", "ipsum", "dolor", "sit", "amet", "consectetur",
            "adipiscing", "elit", "sed", "do", "eiusmod", "tempor"
        ], k=random.randint(5, 10)))
        c.drawString(x, y, text)

    c.save()
    return buffer.getvalue()


def create_dummy_pdf(content: Optional[str] = None) -> Optional[str]:
    """
    Create a dummy PDF file with some content.
    
    Args:
        content: Optional content to include in the PDF. If None, default content is used.
        
    Returns:
        Path to the created PDF file, or None if creation failed.
    """
    # Create a temporary file
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, 'wb') as f:
            if content is None:
                # Use the new generate_random_pdf function
                f.write(generate_random_pdf())
            else:
                # Legacy support for text content
                f.write(f"%PDF-1.4\n{content}\n%%EOF".encode('utf-8'))
        return path
    except Exception as e:
        logger.error(f"Error creating dummy PDF: {e}")
        os.unlink(path)
        return None

def get_random_text(paragraphs: int = 3) -> str:
    """
    Generate random text from Lorem Ipsum.
    
    Args:
        paragraphs: Number of paragraphs to generate.
        
    Returns:
        Generated random text with the specified number of paragraphs.
    """
    words = LOREM_IPSUM.split()
    result: List[str] = []
    
    for _ in range(paragraphs):
        # Generate a paragraph with random length
        length = random.randint(20, 50)
        paragraph = " ".join(random.choices(words, k=length))
        result.append(paragraph)
    
    return "\n\n".join(result)

def seed_nuxeo_repository(url: str, username: str, password: str) -> bool:
    """
    Seed the Nuxeo repository with sample documents.
    
    Args:
        url: Nuxeo server URL
        username: Nuxeo username
        password: Nuxeo password
        
    Returns:
        True if seeding was successful, False otherwise.
    """
    logger.info(f"Connecting to Nuxeo server at {url}")
    nuxeo = Nuxeo(
        host=url,
        auth=(username, password),
    )
    
    # Check if connection is successful
    try:
        server_info = nuxeo.client.server_info()
        logger.info(f"Connected to Nuxeo server version: {server_info['productVersion']}")
    except Exception as e:
        logger.error(f"Failed to connect to Nuxeo server: {e}")
        return False
    
    # Create a folder in the root
    folder_name = f"MCP Test Folder {random.randint(1000, 9999)}"
    folder_path = f"/default-domain/workspaces/{folder_name}"
    
    logger.info(f"Creating folder: {folder_path}")
    try:
        folder = Document(
            name=folder_name,
            type="Folder",
            properties={
                "dc:title": folder_name,
                "dc:description": "Folder for MCP testing"
            }
        )
        
        # Create the folder in the workspaces
        folder = nuxeo.documents.create(folder, parent_path="/default-domain/workspaces")
        logger.info(f"Created folder with ID: {folder.uid}")
    except Exception as e:
        logger.error(f"Failed to create folder: {e}")
        return False
    
    # Create a file document with PDF attachment
    file_name = f"Sample File {random.randint(1000, 9999)}"
    logger.info(f"Creating file document: {file_name}")
    
    try:
        # Create a dummy PDF file
        pdf_path = create_dummy_pdf()
        if not pdf_path:
            logger.error("Failed to create dummy PDF file")
            return False
        
        # Create the file document
        file_doc = Document(
            name=file_name,
            type="File",
            properties={
                "dc:title": file_name,
                "dc:description": "Sample file for MCP testing"
            }
        )
        
        # Create the document in the folder
        file_doc = nuxeo.documents.create(file_doc, parent_path=folder_path)
        logger.info(f"Created file document with ID: {file_doc.uid}")
        
        # Attach the PDF file
        blob = FileBlob(pdf_path)
        

        # Create and upload a blob
        uploaded = nuxeo.uploads.batch().upload(blob, chunked=True)

        # Attach it to the file
        operation = nuxeo.operations.new('Blob.AttachOnDocument')
        operation.params = {'document': file_doc.uid}
        operation.input_obj = uploaded
        operation.execute()

        logger.info(f"Attached PDF to file document")
        
        # Clean up the temporary file
        os.unlink(pdf_path)
    except Exception as e:
        logger.error(f"Failed to create file document: {e}")
        if pdf_path and os.path.exists(pdf_path):
            os.unlink(pdf_path)
        return False
    
    # Create a note document with random text
    note_name = f"Sample Note {random.randint(1000, 9999)}"
    logger.info(f"Creating note document: {note_name}")
    
    try:
        note_content = get_random_text()
        note_doc = Document(
            name=note_name,
            type="Note",
            properties={
                "dc:title": note_name,
                "dc:description": "Sample note for MCP testing",
                "note:note": note_content,
                "note:mime_type": "text/plain"
            }
        )
        
        # Create the note in the folder
        note_doc = nuxeo.documents.create(note_doc, parent_path=folder_path)
        logger.info(f"Created note document with ID: {note_doc.uid}")
    except Exception as e:
        logger.error(f"Failed to create note document: {e}")
        return False
    
    # Create a picture document with a random image
    picture_name = f"Sample Picture {random.randint(1000, 9999)}"
    logger.info(f"Creating picture document: {picture_name}")
    
    try:
        # Create a temporary file for the image
        fd, image_path = tempfile.mkstemp(suffix=".png")
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(generate_random_image())
            
            # Create the picture document
            picture_doc = Document(
                name=picture_name,
                type="Picture",
                properties={
                    "dc:title": picture_name,
                    "dc:description": "Sample picture for MCP testing"
                }
            )
            
            # Create the document in the folder
            picture_doc = nuxeo.documents.create(picture_doc, parent_path=folder_path)
            logger.info(f"Created picture document with ID: {picture_doc.uid}")
            
            # Attach the image file
            blob = FileBlob(image_path)
            
            # Create and upload a blob
            uploaded = nuxeo.uploads.batch().upload(blob, chunked=True)
            
            # Attach it to the picture
            operation = nuxeo.operations.new('Blob.AttachOnDocument')
            operation.params = {'document': picture_doc.uid}
            operation.input_obj = uploaded
            operation.execute()
            
            logger.info(f"Attached PNG image to picture document")
            
        finally:
            # Clean up the temporary file
            if os.path.exists(image_path):
                os.unlink(image_path)
                
    except Exception as e:
        logger.error(f"Failed to create picture document: {e}")
        return False
    
    logger.info("Successfully seeded Nuxeo repository with sample documents")
    
    # Print summary
    print("\nSummary of created documents:")
    print(f"Folder: {folder_path} (ID: {folder.uid})")
    print(f"File: {folder_path}/{file_name} (ID: {file_doc.uid})")
    print(f"Note: {folder_path}/{note_name} (ID: {note_doc.uid})")
    print(f"Picture: {folder_path}/{picture_name} (ID: {picture_doc.uid})")
    
    return True

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Seed Nuxeo repository with sample documents")
    parser.add_argument("--url", default="http://localhost:8080/nuxeo", help="Nuxeo server URL")
    parser.add_argument("--username", default="Administrator", help="Nuxeo username")
    parser.add_argument("--password", default="Administrator", help="Nuxeo password")
    
    args = parser.parse_args()
    
    success = seed_nuxeo_repository(args.url, args.username, args.password)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
