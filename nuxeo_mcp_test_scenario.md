# Nuxeo MCP Server Test Scenario

This document provides step-by-step instructions to test the Nuxeo MCP Server. Follow these instructions to verify that the server is working correctly and to learn how to use its various tools and resources.

## Prerequisites

Before starting this test scenario, ensure that:
1. The Nuxeo MCP Server is installed and running
2. A Nuxeo server is accessible (either locally or remotely)
3. You have valid credentials for the Nuxeo server

## Step 1: Verify Connection to the Nuxeo Server

Let's start by checking if we can connect to the Nuxeo server and retrieve basic information.

```python
# Use the nuxeo_get_repository_info tool to check the connection
repository_info = use_tool("nuxeo", "nuxeo_get_repository_info", {})

# Print the repository information
print("Repository Information:")
print(f"Name: {repository_info.get('name', 'N/A')}")
print(f"Version: {repository_info.get('version', 'N/A')}")
print(f"Root ID: {repository_info.get('rootId', 'N/A')}")
```

Expected output: Information about the Nuxeo repository, including its name, version, and root ID.

**Please confirm that you can connect to the Nuxeo server before proceeding to the next step.**

## Step 2: Access Server Information via Resource

Now, let's try accessing the server information using a resource instead of a tool.

```python
# Access the nuxeo://info resource
server_info = access_resource("nuxeo", "nuxeo://info")

# Print the server information
print("Server Information:")
print(f"URL: {server_info.get('url', 'N/A')}")
print(f"Username: {server_info.get('username', 'N/A')}")
print(f"Connected: {server_info.get('connected', False)}")
```

Expected output: Information about the Nuxeo server, including the URL, username, and connection status.

**Please confirm that you can access the server information before proceeding to the next step.**

## Step 3: Browse the Repository Root

Let's explore the repository by getting the children of the root document.

```python
# Use the nuxeo_list_children tool to get the children of the root document
root_children = use_tool("nuxeo", "nuxeo_list_children", {"ref": "/"})

# Print the children
print("Root Children:")
for child in root_children:
    print(f"- {child.get('title', 'N/A')} ({child.get('type', 'N/A')}) at {child.get('path', 'N/A')}")
```

Expected output: A list of documents at the root of the repository, typically including "Domain" documents.

**Please confirm that you can browse the repository root before proceeding to the next step.**

## Step 4: Navigate to the Default Domain

Now, let's navigate to the default domain and explore its contents.

```python
# Use the nuxeo_list_children tool to get the children of the default domain
domain_children = use_tool("nuxeo", "nuxeo_list_children", {"ref": "/default-domain"})

# Print the children
print("Default Domain Children:")
for child in domain_children:
    print(f"- {child.get('title', 'N/A')} ({child.get('type', 'N/A')}) at {child.get('path', 'N/A')}")
```

Expected output: A list of documents in the default domain, typically including "Workspaces", "Templates", and "Sections".

**Please confirm that you can navigate to the default domain before proceeding to the next step.**

## Step 5: Navigate to the Workspaces

Let's navigate to the Workspaces section and explore its contents.

```python
# Use the nuxeo_list_children tool to get the children of the Workspaces section
workspaces_children = use_tool("nuxeo", "nuxeo_list_children", {"ref": "/default-domain/workspaces"})

# Print the children
print("Workspaces Children:")
for child in workspaces_children:
    print(f"- {child.get('title', 'N/A')} ({child.get('type', 'N/A')}) at {child.get('path', 'N/A')}")
```

Expected output: A list of workspaces in the Workspaces section.

**Please confirm that you can navigate to the Workspaces section before proceeding to the next step.**

## Step 6: Create a Test Workspace

Let's create a new workspace for our tests.

```python
import uuid

# Generate a unique name for the workspace
workspace_name = f"MCP Test Workspace {uuid.uuid4().hex[:8]}"

# Use the nuxeo_create_document tool to create a new workspace
workspace = use_tool("nuxeo", "nuxeo_create_document", {
    "parent_path": "/default-domain/workspaces",
    "name": workspace_name.replace(" ", "_").lower(),
    "type": "Workspace",
    "properties": {
        "dc:title": workspace_name,
        "dc:description": "A workspace created for testing the Nuxeo MCP Server"
    }
})

# Print the workspace information
print("Created Workspace:")
print(f"Title: {workspace.get('title', 'N/A')}")
print(f"Path: {workspace.get('path', 'N/A')}")
print(f"ID: {workspace.get('uid', 'N/A')}")

# Store the workspace path and uid for later use
workspace_path = workspace.get('path')
workspace_uid = workspace.get('uid')
```

Expected output: Information about the newly created workspace, including its title, path, and ID.

**Please confirm that you can create a test workspace before proceeding to the next step.**

## Step 7: Create a File Document with Attachment

Now, let's create a file document in our test workspace and attach a file to it.

```python
# First, create a simple text file to attach
with open("test_attachment.txt", "w") as f:
    f.write("This is a test file for the Nuxeo MCP Server.")

# Use the nuxeo_create_document tool to create a new file document
file_doc = use_tool("nuxeo", "nuxeo_create_document", {
    "parent_path": workspace_path,
    "name": "test_file",
    "type": "File",
    "properties": {
        "dc:title": "Test File",
        "dc:description": "A file created for testing the Nuxeo MCP Server"
    }
})

# Print the file document information
print("Created File Document:")
print(f"Title: {file_doc.get('title', 'N/A')}")
print(f"Path: {file_doc.get('path', 'N/A')}")
print(f"ID: {file_doc.get('uid', 'N/A')}")

# Store the file document path and uid for later use
file_doc_path = file_doc.get('path')
file_doc_uid = file_doc.get('uid')

# Now attach the file to the document using the Blob.AttachOnDocument operation
attachment_result = use_tool("nuxeo", "nuxeo_execute_operation", {
    "operation_id": "Blob.AttachOnDocument",
    "params": {
        "document": file_doc_path,
        "xpath": "file:content"
    },
    "input_type": "file",
    "file_path": "test_attachment.txt"
})

print("Attachment Result:")
print(attachment_result)
```

Expected output: Information about the newly created file document, including its title, path, and ID, followed by the result of attaching a file to it.

**Please confirm that you can create a file document with an attachment before proceeding to the next step.**

## Step 8: Create a Note Document with Rich Text Content

Let's also create a note document in our test workspace with rich text content.

```python
# Use the nuxeo_create_document tool to create a new note document
note_doc = use_tool("nuxeo", "nuxeo_create_document", {
    "parent_path": workspace_path,
    "name": "test_note",
    "type": "Note",
    "properties": {
        "dc:title": "Test Note",
        "dc:description": "A note created for testing the Nuxeo MCP Server",
        "note:note": "<h1>Test Note Content</h1><p>This is a <strong>rich text</strong> note with <em>formatting</em>.</p><ul><li>Item 1</li><li>Item 2</li><li>Item 3</li></ul><p>It contains various HTML elements to test full-text search capabilities.</p>"
    }
})

# Print the note document information
print("Created Note Document:")
print(f"Title: {note_doc.get('title', 'N/A')}")
print(f"Path: {note_doc.get('path', 'N/A')}")
print(f"ID: {note_doc.get('uid', 'N/A')}")

# Store the note document path and uid for later use
note_doc_path = note_doc.get('path')
note_doc_uid = note_doc.get('uid')
```

Expected output: Information about the newly created note document, including its title, path, and ID.

**Please confirm that you can create a note document with rich text content before proceeding to the next step.**

## Step 9: Search for Documents by Type

Now that we have created some content, let's search for documents in the repository using a NXQL query.

```python
# Use the search tool to search for documents by type
search_results = use_tool("nuxeo", "nuxeo_search_documents", {
    "query": "SELECT * FROM Document WHERE ecm:primaryType = 'File'",
    "mode": "nxql",
    "page_size": 10,
    "page_index": 0
})

# Print the search results
print("Search Results by Type:")
print(f"Total Results: {search_results['totalCount']}")
print("Documents:")
for doc in search_results['documents']:
    print(f"- {doc['title']} ({doc['documentType']}) at {doc['path']}")
```

Expected output: A list of File documents in the repository, including our newly created file document.

**Please confirm that you can search for documents by type before proceeding to the next step.**

## Step 10: Search for Documents with Full-Text Search

Let's search for documents using full-text search capabilities.

```python
# Use the search tool to search for documents using full-text search
fulltext_search_results = use_tool("nuxeo", "nuxeo_search_documents", {
    "query": "SELECT * FROM Document WHERE ecm:fulltext = 'rich text formatting'",
    "mode": "nxql",
    "page_size": 10,
    "page_index": 0
})

# Print the search results
print("Full-Text Search Results:")
print(f"Total Results: {fulltext_search_results['totalCount']}")
print("Documents:")
for doc in fulltext_search_results['documents']:
    print(f"- {doc['title']} ({doc['documentType']}) at {doc['path']}")
```

Expected output: A list of documents containing the text "rich text formatting", which should include our note document.

**Please confirm that you can search for documents using full-text search before proceeding to the next step.**

## Step 11: Get Document Details

Let's retrieve detailed information about the file document we created.

```python
# Use the nuxeo_get_document tool to get the file document details
file_doc_details = use_tool("nuxeo", "nuxeo_get_document", {
    "ref": file_doc_path
})

# Print the file document details
print("File Document Details:")
print(f"Title: {file_doc_details.get('title', 'N/A')}")
print(f"Type: {file_doc_details.get('type', 'N/A')}")
print(f"State: {file_doc_details.get('state', 'N/A')}")
print(f"Last Modified: {file_doc_details.get('lastModified', 'N/A')}")
print(f"Creator: {file_doc_details.get('properties', {}).get('dc:creator', 'N/A')}")

# Get the file content
file_content = use_tool("nuxeo", "nuxeo_get_document", {
    "ref": file_doc_path,
    "fetch_blob": True
})

print("File Content Available:", file_content is not None)
```

Expected output: Detailed information about the file document, including its title, type, state, last modified date, and creator, followed by confirmation that the file content is available.

**Please confirm that you can get document details and content before proceeding to the next step.**

## Step 12: Update the File Document

Let's update the file document by changing its title and description.

```python
# Use the nuxeo_update_metadata tool to update the file document
updated_file_doc = use_tool("nuxeo", "nuxeo_update_metadata", {
    "path": file_doc_path,
    "properties": {
        "dc:title": "Updated Test File",
        "dc:description": "This file has been updated"
    }
})

# Print the updated file document information
print("Updated File Document:")
print(f"Title: {updated_file_doc.get('title', 'N/A')}")
print(f"Description: {updated_file_doc.get('properties', {}).get('dc:description', 'N/A')}")
```

Expected output: Information about the updated file document, including its new title and description.

**Please confirm that you can update a document before proceeding to the next step.**

## Step 13: Get Document via Resource

Let's try accessing the note document using a resource instead of a tool.

```python
# Access the document resource
note_doc_resource = access_resource("nuxeo", f"nuxeo:/{note_doc_path}")

# The resource is the document rendered as markdown
print("Note Document from Resource:")
print(note_doc_resource)
```

Expected output: Information about the note document, including its title, type, and note content.

**Please confirm that you can access a document via resource before proceeding to the next step.**

## Step 14: Delete the File Document

Now, let's delete the file document using its UID.

```python
# Use the nuxeo_delete_document tool to delete the file document
delete_result = use_tool("nuxeo", "nuxeo_delete_document", {
    "uid": file_doc_uid
})

# Print the delete result
print("Delete Result:")
print(delete_result)

# Try to get the deleted document to verify it's gone
try:
    deleted_doc = use_tool("nuxeo", "nuxeo_get_document", {
        "ref": file_doc_path
    })
    print("Document still exists!")
except Exception as e:
    print(f"Document was successfully deleted: {e}")
```

Expected output: Confirmation that the document was deleted, and an error when trying to retrieve it.

**Please confirm that you can delete a document before proceeding to the next step.**

## Step 15: Delete the Note Document

Let's also delete the note document using its UID.

```python
# Use the nuxeo_delete_document tool to delete the note document
delete_result = use_tool("nuxeo", "nuxeo_delete_document", {
    "uid": note_doc_uid
})

# Print the delete result
print("Delete Result:")
print(delete_result)
```

Expected output: Confirmation that the document was deleted.

**Please confirm that you can delete the note document before proceeding to the next step.**

## Step 16: Delete the Test Workspace

Finally, let's clean up by deleting the test workspace using its UID.

```python
# Use the nuxeo_delete_document tool to delete the test workspace
delete_result = use_tool("nuxeo", "nuxeo_delete_document", {
    "uid": workspace_uid
})

# Print the delete result
print("Delete Result:")
print(delete_result)
```

Expected output: Confirmation that the workspace was deleted.

**Please confirm that you can delete the test workspace.**

## Conclusion

Congratulations! You have successfully completed the Nuxeo MCP Server test scenario. This scenario has demonstrated the following capabilities:

1. Connecting to the Nuxeo server
2. Retrieving repository and server information
3. Browsing the repository structure
4. Creating documents (workspace, file with attachment, note with rich text)
5. Searching for documents by type and using full-text search
6. Retrieving document details and content
7. Updating documents
8. Accessing documents via resources
9. Deleting documents

If all steps were completed successfully, the Nuxeo MCP Server is working correctly.
