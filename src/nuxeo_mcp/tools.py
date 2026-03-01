#!/usr/bin/env python3
"""
Nuxeo MCP Server tools.

This module defines the tools for the Nuxeo MCP Server.
"""

import logging
import json
import os
from typing import Any, Dict, Optional, Callable, List, Annotated
from nuxeo_mcp.utility import (
    format,
    format_docs,
    format_doc,
    return_blob,
    is_uuid,
)
from nuxeo.models import Document
from mcp.types import ImageContent as Image
from pydantic import BaseModel, Field, model_validator

# Configure logging
logger = logging.getLogger("nuxeo_mcp.tools")

# Type aliases
ToolFunction = Callable[[Dict[str, Any]], Dict[str, Any]]


class DocRef(BaseModel):
    path: Annotated[str | None, Field(description="Repository path")] = None
    uid: Annotated[str | None, Field(description="Nuxeo UID")] = None

    @model_validator(mode="after")
    def one_of_path_or_uid(cls, v):
        if bool(v.path) == bool(v.uid):  # both or neither
            raise ValueError("Provide *exactly* one of 'path' or 'uid'")
        return v


from typing import Union


def register_tools(mcp, nuxeo, auth_middleware=None, skip_server_selection: bool = False) -> None:
    """
    Register MCP tools with the FastMCP server.

    Args:
        mcp: The FastMCP server instance
        nuxeo: The Nuxeo client instance
        auth_middleware: Optional authentication middleware to wrap tools
        skip_server_selection: If True, skip automatic server selection (useful when server is pre-configured)
    """

    # Tool: Get repository info
    @mcp.tool(
        name="get_repository_info",
        description="Get information about the Nuxeo repository",
    )
    def get_repository_info() -> Dict[str, Any]:
        """
        Get information about the Nuxeo repository.

        Args: None

        Returns:
            Information about the Nuxeo repository
        """

        server_info = nuxeo.client.server_info()

        return server_info

    @mcp.tool(name="get_children", description="list children of a folder document ")
    def get_children(
        ref: Annotated[
            str, Field(description="reference can be either a uuid or a path ")
        ],
        as_resource: Annotated[
            bool, Field(description="Return Document as nuxeo:// resource")
        ] = False,
    ) -> Dict[str, Any]:
        """
        List children from a parent document about the Nuxeo repository.

        Args:
            ref: reference can be either a uuid or a path

        Returns:
            List of documents
        """

        if is_uuid(ref):
            docs = nuxeo.documents.get_children(uid=ref)
        else:
            docs = nuxeo.documents.get_children(path=ref)

        return format_docs(docs, as_resource=as_resource)

    @mcp.tool(name="search", description="search document using a NXQL query")
    def search(
        query: str,
        pageSize: int = 20,
        currentPageIndex: int = 0,
        content_type="application/json",
    ) -> dict[str, Any]:
        """
        Executes a Nuxeo Query Language (NXQL) statement and returns the matching documents.

        NXQL is a SQL-like language designed to query the Nuxeo content repository. This tool accepts
        a full NXQL query string, executes it, and returns the results.

        ## Query Syntax
        Basic NXQL syntax:
            SELECT (* | [DISTINCT] <select-clause>)
            FROM <doc-type>
            [WHERE <conditions>]
            [ORDER BY <sort-clause>]

        Example queries:
        - SELECT * FROM Document WHERE dc:title LIKE 'Invoice%'
        - SELECT ecm:uuid, dc:title FROM File WHERE ecm:fulltext = 'contract' ORDER BY dc:modified DESC
        - SELECT COUNT(ecm:uuid) FROM Document WHERE dc:created >= DATE '2024-01-01'

        ## Notes
        - You can query metadata, including standard fields like `dc:title`, `ecm:uuid`, `ecm:primaryType`, etc.
        - Use `NOW()` to compare against the current timestamp (e.g., `dc:modified < NOW('-P7D')`).
        - Full-text search is supported via `ecm:fulltext`.
        - List and complex properties can be addressed using `/` or wildcards (e.g., `dc:subjects/* = 'finance'`).
        - Aggregates like COUNT, MIN, MAX are supported (in VCS mode only).

        ## Limitations
        - NXQL execution depends on repository type (VCS, MongoDB, Elasticsearch).
        - Ensure query validity to avoid syntax errors or unsupported patterns.

        Parameters:
            query (str): A valid NXQL query string.
            pageSize (int) : Number of documents to list per page
            currentPageIndex (int) : index of the page to retrieve


        Returns:
            json object with 2 keys:
                "content" : the formatted list of documents,
                "content_type" : format used - for example "text/markdown"
        """

        return format(
            nuxeo.documents.query(
                {
                    "query": query,
                    "pageSize": pageSize,
                    "currentPageIndex": currentPageIndex,
                }
            ),
            content_type,
        )

    @mcp.tool(
        name="get_document_types",
        description="Get information about document types and schemas defined in the Nuxeo server",
    )
    def get_document_types() -> Dict[str, Any]:
        """
        Get information about document types and schemas defined in the Nuxeo server.

        This tool retrieves comprehensive information about all document types and their
        associated schemas defined in the Nuxeo server. The information includes:

        - Document type hierarchy (parent-child relationships)
        - Facets associated with each document type
        - Schemas associated with each document type

        Returns:
            Dictionary containing document types and their definitions with two main keys:
            - 'doctypes': Information about document types
            - 'schemas': Basic schema information
        """
        types_info = nuxeo.client.request("GET", "api/v1/config/types/")
        return types_info.json()

    @mcp.tool(
        name="get_schemas",
        description="Get detailed information about schemas defined in the Nuxeo server",
    )
    def get_schemas() -> List[Dict[str, Any]]:
        """
        Get detailed information about schemas defined in the Nuxeo server.

        This tool retrieves detailed information about all schemas defined in the Nuxeo server.
        For each schema, it provides:

        - Schema name and prefix
        - All fields defined in the schema with their types
        - Field constraints and default values

        Returns:
            List of schemas with their complete definitions
        """
        schemas = nuxeo.client.request("GET", "api/v1/config/schemas/")
        return schemas.json()

    @mcp.tool(
        name="get_operations",
        description="Get information about available Automation Operations in the Nuxeo server",
    )
    def get_operations() -> Dict[str, Any]:
        """
        Get information about available Automation Operations in the Nuxeo server.

        This tool retrieves comprehensive information about all Automation Operations
        available in the Nuxeo server. For each operation, it provides:

        - Operation ID and aliases
        - Category and label
        - Description and documentation
        - Input/output types (signature)
        - Parameters with their types, descriptions, and constraints

        Example usage:
            To get information about a specific operation:
            operations = get_operations()
            operation_info = operations["Document.AddACL"]

        Returns:
            Dictionary where each key is an Operation name and the value is its documentation
        """
        return nuxeo.operations.operations

    @mcp.tool(
        name="execute_operation",
        description="Execute a Nuxeo Operation with the specified parameters and input",
    )
    def execute_operation(
        operation_id: str,
        params: Dict[str, Any] = None,
        input_type: str = None,
        input_value: str = None,
        file_path: str = None,
    ) -> Any:
        """
        Execute a Nuxeo Operation with the specified parameters and input.

        This tool allows you to execute any Nuxeo Automation Operation with various
        input types and parameters. It supports:

        - Document path or UID as input
        - Multiple documents as input
        - File upload as input
        - Parameters for the operation
        - Automatic formatting of document results

        ## Input Types

        - 'document_path': Use a document path as input (e.g., '/default-domain/workspaces/my-doc')
        - 'document_uid': Use a document UID as input
        - 'documents': Use multiple document UIDs or paths (comma-separated)
        - 'file': Upload a file as input (requires file_path parameter)
        - None: No input (for operations that don't require input)

        ## Examples

        1. Set synchronization on a folder:
           ```
           execute_operation(
               operation_id="NuxeoDrive.SetSynchronization",
               params={"enable": True},
               input_type="document_path",
               input_value="/My Folder"
           )
           ```

        2. Attach a blob to a document:
           ```
           execute_operation(
               operation_id="Blob.AttachOnDocument",
               params={"document": "/foo"},
               input_type="file",
               file_path="/path/to/file.pdf"
           )
           ```

        3. Bulk operation on multiple documents:
           ```
           execute_operation(
               operation_id="Document.Update",
               params={"properties": {"dc:description": "Updated"}},
               input_type="documents",
               input_value="uid1,uid2,uid3"
           )
           ```

        Args:
            operation_id: The ID of the operation to execute
            params: Dictionary of parameters to pass to the operation
            input_type: Type of input ('document_path', 'document_uid', 'documents', 'file', 'none')
            input_value: Value of the input (document path, document UID, comma-separated list, or None)
            file_path: Path to a file to upload as input (only used when input_type is 'file')

        Returns:
            The result of the operation execution, formatted if it's a document or list of documents
        """
        # Create a new operation
        operation = nuxeo.operations.new(operation_id)

        # Set parameters if provided
        if params:
            operation.params = params

        # Set input based on input_type with proper Nuxeo formatting
        if input_type in ["document_path", "document_uid", "document"]:
            # Format the input with the required "doc:" prefix for Nuxeo automation API
            if input_value:
                # Check if it's already properly formatted
                if not input_value.startswith(("doc:", "docs:", "blob:", "blobs:")):
                    # Add the "doc:" prefix for single document input
                    operation.input_obj = f"doc:{input_value}"
                else:
                    operation.input_obj = input_value
        elif input_type == "documents":
            # Handle multiple documents with "docs:" prefix
            if input_value:
                # Split comma-separated values and clean them
                doc_refs = [ref.strip() for ref in input_value.split(",")]
                # Check if already formatted
                if not input_value.startswith("docs:"):
                    # Add the "docs:" prefix for multiple document input
                    operation.input_obj = f"docs:{','.join(doc_refs)}"
                else:
                    operation.input_obj = input_value
        elif input_type == "file" and file_path:
            # Check if file exists
            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")

            # Upload the file and use it as input
            from nuxeo.models import FileBlob
            blob = FileBlob(file_path)
            uploaded = nuxeo.uploads.batch().upload(blob, chunked=True)
            operation.input_obj = uploaded

        # Execute the operation
        result = operation.execute()

        # Format the result if it's a document or list of documents
        if hasattr(result, "is_document") and result.is_document:
            return format_doc(result)
        elif (
            isinstance(result, list)
            and len(result) > 0
            and hasattr(result[0], "is_document")
            and result[0].is_document
        ):
            return format_docs(result)

        # Return the raw result for other types
        return result

    @mcp.tool(
        name="create_document",
        description="Create a new document in the Nuxeo repository with optional file attachment",
    )
    def create_document(
        name: str,
        type: str,
        properties: Dict[str, Any],
        parent_path: str,
        file_path: str = None,
    ) -> Dict[str, Any]:
        """
        Create a new document in the Nuxeo repository with optional file attachment.

        This tool creates a new document with the specified properties in the Nuxeo repository.
        It supports creating any document type available in your Nuxeo instance, such as:

        - File: Standard document with attached content
        - Folder: Container for other documents
        - Note: Simple text document
        - Workspace: Collaborative space for documents
        - Picture: Image document with additional metadata
        - Video: Video document with additional metadata

        ## File Attachment

        You can attach a file to the document during creation by providing the file_path parameter.
        The file will be uploaded via the batch upload API and attached to the document's main blob.

        ## Example Usage

        Create a folder:
        ```
        create_document(
            name="my-folder",
            type="Folder",
            properties={"dc:title": "My Folder", "dc:description": "A test folder"},
            parent_path="/default-domain/workspaces"
        )
        ```

        Create a file with attachment:
        ```
        create_document(
            name="my-document",
            type="File",
            properties={
                "dc:title": "My Document",
                "dc:description": "A test document"
            },
            parent_path="/default-domain/workspaces/my-folder",
            file_path="/path/to/document.pdf"
        )
        ```

        Create a Picture with image:
        ```
        create_document(
            name="vacation-photo",
            type="Picture",
            properties={
                "dc:title": "Beach Photo",
                "dc:description": "Sunset at the beach"
            },
            parent_path="/default-domain/workspaces/photos",
            file_path="/path/to/photo.jpg"
        )
        ```

        Args:
            name: The name of the document (used in the document's path)
            type: The document type (e.g., 'File', 'Folder', 'Note', 'Picture')
            properties: Dictionary of document properties (e.g., {"dc:title": "My Document"})
            parent_path: Path of the parent document where this document will be created
            file_path: Optional path to a file to attach to the document

        Returns:
            The created document formatted as markdown
        """
        # Handle file upload if provided
        if file_path:
            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")

            # Upload file to batch
            from nuxeo.models import FileBlob
            blob = FileBlob(file_path)
            batch = nuxeo.uploads.batch().upload(blob, chunked=True)

            # Add batch reference to properties
            # The file:content property references the uploaded batch
            properties["file:content"] = {
                "upload-batch": batch.batchId,
                "upload-fileId": "0",  # First file in the batch
            }

            logger.info(f"Uploaded file to batch {batch.batchId}")

        # Create the document with the properties (including file:content if present)
        new_doc = Document(name=name, type=type, properties=properties)
        doc = nuxeo.documents.create(new_doc, parent_path=parent_path)

        # Return a structured response with document information
        # Get title from properties or use the name as fallback
        doc_title = doc.properties.get("dc:title", name) if hasattr(doc, 'properties') else name
        
        return {
            "status": "success",
            "message": f"Document '{name}' created successfully",
            "uid": doc.uid,
            "path": doc.path,
            "title": doc_title,
            "type": type,
            "url": f"{nuxeo.client.host}/ui/#!/browse{doc.path}",
            "details": format_doc(doc)  # Include full formatted details as a string
        }

    @mcp.tool(
        name="get_document", description="Get a document from the Nuxeo repository"
    )
    def get_document(
        ref: Annotated[
            str, Field(description="reference can be either a uuid or a path ")
        ],
        fetch_blob: Annotated[bool, Field(description="Return main blob")] = False,
        as_resource: Annotated[
            bool, Field(description="Return Document as nuxeo:// resource")
        ] = False,
        conversion_format: Annotated[
            str,
            Field(
                description="Convert the document to a different format 'pdf', 'html')"
            ),
        ] = "",
        rendition: Annotated[
            str,
            Field(
                description="Fetch a specific rendition of the document (e.g., 'thumbnail')"
            ),
        ] = "",
    ) -> str | bytes | Image:
        """
        Get a document from the Nuxeo repository.

        This tool retrieves a document from the Nuxeo repository by path or UID.
        It can also fetch the document's blob, convert it to a different format,
        or fetch a rendition of the document.

        ## Document Identification

        You must provide either a path or a UID to identify the document:
        - Path: The document's path in the repository (e.g., "/default-domain/workspaces/my-folder")
        - UID: The document's unique identifier (e.g., "12345678-1234-1234-1234-123456789012")

        ## Blob Operations

        - fetch_blob: Set to true to fetch the document's main blob (if it has one)
        - conversion_format: Convert the document to a different format (e.g., "pdf", "html")
        - rendition: Fetch a specific rendition of the document (e.g., "thumbnail")

        ## Other parameters

        - as_resource: Set to true to get a Nuxeo Resource.

        ## Example Usage

        Get a document by path:
        ```
        get_document(ref="/default-domain/workspaces/my-folder")
        ```

        Get a document by UID:
        ```
        get_document(ref="12345678-1234-1234-1234-123456789012")
        ```

        Get a document's thumbnail:
        ```
        get_document(
            ref="/default-domain/workspaces/my-document",
            rendition="thumbnail"
        )
        ```

        Args:
            ref: reference can be either a uuid or a path
            fetch_blob: Whether to fetch the document's blob
            as_resource: Whether to fetch the document as a nuxeo:// resource
            conversion_format: Format to convert the document to (e.g., 'pdf')
            rendition: Rendition to fetch (e.g., 'thumbnail')

        Returns:
            The document formatted as markdown or the blob
        """

        if is_uuid(ref):
            doc = nuxeo.documents.get(uid=ref)
        else:
            doc = nuxeo.documents.get(path=ref)

        if as_resource:
            return f"nuxeo://{doc.uid}"

        # Handle blob operations if requested
        blob_info = {}

        if fetch_blob:
            try:
                # built in method do not propagate headers
                # blob = doc.fetch_blob()

                r = nuxeo.client.request(
                    "GET", f"api/v1/repo/default/id/{doc.uid}/@blob/blobholder:0"
                )

                disposition = r.headers["content-disposition"]
                filename = disposition.split(";")[-1].split("=")[-1]
                mime = r.headers["content-type"]
                content_length = int(r.headers["content-length"])

                blob_info = {
                    "name": filename,
                    "mime_type": mime,
                    "size": content_length,
                    "content": r.content,
                }
                return return_blob(blob_info)
            except Exception as e:
                blob_info["blob_error"] = str(e)

        if conversion_format:
            try:
                # built in method do not propagate headers
                # conversion = doc.convert({'format': conversion_format})

                r = nuxeo.client.request(
                    "GET",
                    path=f"api/v1/repo/default/id/{doc.uid}",
                    adapter="blob/blobholder:0/@convert",
                    params={"format": conversion_format},
                )
                disposition = r.headers["content-disposition"]
                filename = disposition.split(";")[-1].split("=")[-1]
                mime = r.headers["content-type"]
                content_length = int(r.headers["content-length"])

                blob_info = {
                    "format": conversion_format,
                    "name": filename,
                    "mime_type": mime,
                    "size": content_length,
                    "content": r.content,
                }
                return return_blob(blob_info)
            except Exception as e:
                # Log the error for debugging
                logger.error(f"Conversion error: {e}")
                # Return error information instead of continuing
                return {"error": f"Conversion failed: {str(e)}"}

        if rendition:
            try:
                # built in method do not propagate headers
                # rendition_blob = doc.fetch_rendition(rendition)
                adapter = f"rendition/{rendition}"
                r = nuxeo.client.request(
                    "GET", path=f"api/v1/repo/default/id/{doc.uid}", adapter=adapter
                )
                disposition = r.headers["content-disposition"]
                filename = disposition.split(";")[-1].split("=")[-1]
                mime = r.headers["content-type"]
                content_length = int(r.headers["content-length"])

                blob_info = {
                    "name": filename,
                    "mime_type": mime,
                    "size": content_length,
                    "content": r.content,
                }

                return return_blob(blob_info)

            except Exception as e:
                return str(e)

        # Format the document
        result = format_doc(doc)

        return result

    @mcp.tool(
        name="update_document",
        description="Update an existing document in the Nuxeo repository",
    )
    def update_document(
        path: str = None, uid: str = None, properties: Union[Dict[str, Any], str] = None
    ) -> Dict[str, Any]:
        """
        Update an existing document in the Nuxeo repository.

        This tool updates an existing document in the Nuxeo repository with the specified properties.
        You can identify the document to update by either its path or UID.

        ## Document Identification

        You must provide either a path or a UID to identify the document:
        - Path: The document's path in the repository (e.g., "/default-domain/workspaces/my-folder")
        - UID: The document's unique identifier (e.g., "12345678-1234-1234-1234-123456789012")

        ## Properties

        The properties parameter should be a dictionary of document properties to update.
        Common properties include:

        - dc:title: Document title
        - dc:description: Document description
        - dc:creator: Document creator
        - dc:contributors: Document contributors
        - dc:created: Creation date
        - dc:modified: Modification date

        ## Example Usage

        Update a document's title:
        ```
        update_document(
            path="/default-domain/workspaces/my-folder",
            properties={"dc:title": "Updated Folder Title"}
        )
        ```

        Update multiple properties:
        ```
        update_document(
            uid="12345678-1234-1234-1234-123456789012",
            properties={
                "dc:title": "Updated Title",
                "dc:description": "Updated Description"
            }
        )
        ```

        Args:
            path: Path of the document (mutually exclusive with uid)
            uid: UID of the document (mutually exclusive with path)
            properties: Dictionary of document properties to update (can be dict or JSON string)

        Returns:
            The updated document formatted as markdown
        """
        if not path and not uid:
            raise ValueError("Either path or uid must be provided")

        if path and uid:
            raise ValueError("Only one of path or uid should be provided")

        # Handle properties as either dict or JSON string
        if properties:
            if isinstance(properties, str):
                try:
                    import json

                    properties = json.loads(properties)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in properties parameter: {e}")

        doc = nuxeo.documents.get(path=path, uid=uid)

        if properties:
            for key, value in properties.items():
                doc.properties[key] = value

        doc.save()
        return format_doc(doc)

    @mcp.tool(
        name="delete_document",
        description="Delete a document from the Nuxeo repository",
    )
    def delete_document(uid: str = None) -> Dict[str, Any]:
        """
        Delete a document from the Nuxeo repository.

        This tool deletes a document from the Nuxeo repository.
        You can identify the document to delete by either its path or UID.

        ## Document Identification

        You must provide a UID to identify the document:
        - UID: The document's unique identifier (e.g., "12345678-1234-1234-1234-123456789012")

        ## Example Usage

        Delete a document by UID:
        ```
        delete_document(uid="12345678-1234-1234-1234-123456789012")
        ```

        Args:
            uid: UID of the document (mutually exclusive with path)

        Returns:
            Status of the deletion operation
        """
        if not uid:
            raise ValueError("uid must be provided")

        result = nuxeo.documents.delete(uid)
        return {"status": "success", "message": f"Document deleted successfully"}

    @mcp.tool(
        name="move_document",
        description="Move a document to a different location in the Nuxeo repository",
    )
    def move_document(
        document_uid: str,
        target_path: str,
        new_name: str = None
    ) -> Dict[str, Any]:
        """
        Move a document to a different location in the Nuxeo repository.

        This tool moves a document from its current location to a new parent folder.
        You can also optionally rename the document during the move operation.

        ## Document Identification

        - document_uid: The UID of the document to move
        - target_path: The path of the destination folder

        ## Optional Rename

        - new_name: If provided, the document will be renamed during the move

        ## Example Usage

        Move a document to a different folder:
        ```
        move_document(
            document_uid="12345678-1234-1234-1234-123456789012",
            target_path="/default-domain/workspaces/archive"
        )
        ```

        Move and rename a document:
        ```
        move_document(
            document_uid="12345678-1234-1234-1234-123456789012",
            target_path="/default-domain/workspaces/archive",
            new_name="archived-document"
        )
        ```

        Args:
            document_uid: UID of the document to move
            target_path: Path of the destination folder
            new_name: Optional new name for the document

        Returns:
            The moved document information
        """
        # Build parameters for the move operation
        params = {"target": target_path}
        if new_name:
            params["name"] = new_name

        # Execute the Document.Move operation with proper input formatting
        # The document UID needs the "doc:" prefix for Nuxeo automation API
        operation = nuxeo.operations.new("Document.Move")
        operation.params = params
        operation.input_obj = f"doc:{document_uid}"
        
        # Execute the operation
        result = operation.execute()
        
        # Format and return the result
        if hasattr(result, "uid"):
            return {
                "status": "success",
                "message": f"Document moved successfully to {target_path}",
                "uid": result.uid,
                "path": result.path,
                "title": result.properties.get("dc:title", "") if hasattr(result, 'properties') else "",
                "url": f"{nuxeo.client.host}/ui/#!/browse{result.path}"
            }
        else:
            return {
                "status": "success",
                "message": f"Document moved to {target_path}",
                "details": str(result)
            }

    @mcp.tool(
        name="natural_search",
        description="Search for documents using natural language queries that get automatically converted to NXQL",
    )
    def natural_search(
        query: str,
        explain: bool = False,
        pageSize: int = 20,
        currentPageIndex: int = 0,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        """
        Search for documents using natural language that gets intelligently converted to NXQL.

        This tool allows users to search using natural language queries instead of writing NXQL directly.
        The natural language is parsed and converted to proper NXQL syntax automatically.

        Note: Since Nuxeo uses MongoDB (DBS), aggregates like COUNT, AVG, SUM, MIN, MAX are not supported.

        ## Supported Natural Language Patterns

        ### Document Types
        - "invoices", "files", "folders", "notes", "documents", "PDFs", "images", "videos"

        ### Time-based Queries
        - "documents from today/yesterday/this week/last month/last year"
        - "files created in the last 7 days"
        - "documents modified since 2024-01-01"
        - "files between 2024-01-01 and 2024-12-31"

        ### User-based Queries
        - "documents created by John"
        - "files from Alice"
        - "Bob's documents"

        ### Content Queries
        - "documents containing 'quarterly report'"
        - "files with content 'budget'"
        - "search for 'project proposal'"

        ### Title/Name Queries
        - "documents named 'Invoice 2024'"
        - "files with title containing 'report'"
        - "documents titled 'Meeting Notes'"

        ### Path/Location Queries
        - "documents in folder '/workspaces/project'"
        - "files under '/default-domain/workspaces'"

        ### State Queries
        - "draft documents"
        - "published files"
        - "deleted documents"
        - "locked files"

        ### Special Filters
        - "latest documents" (ordered by modification date)
        - "largest files" (ordered by size)
        - "first 10 documents"
        - "documents not in trash"
        - "latest versions only"

        ## Examples

        Simple queries:
        - "Find all invoices from last month"
        - "Show me documents created by John"
        - "List PDFs modified this week"
        - "Search for documents containing budget"

        Complex queries:
        - "Find invoices created by Alice in the last 30 days not in trash"
        - "Show me the 10 latest documents in folder '/workspaces/accounting'"
        - "List all PDF files created this year"

        Parameters:
            query (str): Natural language search query
            explain (bool): If True, returns the generated NXQL query and explanation
            pageSize (int): Number of documents per page
            currentPageIndex (int): Page number to retrieve
            content_type (str): Output format ("application/json" or "text/markdown")

        Returns:
            If explain=True: Returns explanation with generated NXQL
            If explain=False: Returns search results
        """
        try:
            from nuxeo_mcp.nl_parser import NaturalLanguageParser, NXQLBuilder

            # Parse the natural language query
            parser = NaturalLanguageParser()
            parsed = parser.parse(query)

            # Build the NXQL query
            builder = NXQLBuilder(parsed)
            nxql = builder.build()

            # If explain mode, return the generated query and explanation
            if explain:
                return {
                    "natural_query": query,
                    "generated_nxql": nxql,
                    "explanation": parsed.explanation,
                    "parsed_components": {
                        "intent": parsed.intent,
                        "document_type": parsed.doc_type,
                        "conditions": parsed.conditions,
                        "order_by": parsed.order_by,
                        "order_direction": parsed.order_direction,
                        "limit": parsed.limit,
                    },
                }

            # Execute the generated NXQL query directly using Nuxeo client
            # Note: We need to handle LIMIT separately as it's not part of NXQL
            effective_page_size = (
                parsed.limit
                if parsed.limit and parsed.limit < pageSize
                else pageSize
            )
            
            # Execute the NXQL query directly
            query_result = nuxeo.client.query(
                nxql,
                params={
                    "pageSize": effective_page_size,
                    "currentPageIndex": currentPageIndex
                }
            )
            
            # Format the result based on content_type
            if content_type == "text/markdown":
                result = format_query_results(query_result)
            else:
                # Return JSON format
                result = {
                    "resultsCount": query_result.get("resultsCount", 0),
                    "currentPageIndex": query_result.get("currentPageIndex", 0),
                    "pageSize": query_result.get("pageSize", effective_page_size),
                    "entries": query_result.get("entries", [])
                }

            # Add metadata about the natural language processing
            if isinstance(result, dict):
                result["_natural_query"] = query
                result["_generated_nxql"] = nxql

            return result

        except Exception as e:
            # Fall back to regular search if natural language parsing fails
            logger.warning(
                f"Natural language parsing failed: {e}. Falling back to fulltext search."
            )

            # Extract keywords for fulltext search
            # Remove common words that aren't useful for search
            stop_words = {
                "find",
                "show",
                "list",
                "get",
                "search",
                "for",
                "all",
                "the",
                "me",
                "with",
                "in",
                "from",
                "by",
            }
            keywords = [
                word for word in query.lower().split() if word not in stop_words
            ]

            if keywords:
                fallback_query = f"SELECT * FROM Document WHERE ecm:fulltext = '{' '.join(keywords)}'"
            else:
                fallback_query = "SELECT * FROM Document"

            result = search(
                query=fallback_query,
                pageSize=pageSize,
                currentPageIndex=currentPageIndex,
                content_type=content_type,
            )

            if isinstance(result, dict):
                result["_natural_query"] = query
                result["_fallback_mode"] = True
                result["_generated_nxql"] = fallback_query

            return result

    @mcp.tool()
    async def search_repository(query: str, limit: int = 20, offset: int = 0) -> str:
        """
        [REQUIRES ELASTICSEARCH] Search the Nuxeo repository using Elasticsearch passthrough.

        This tool provides direct Elasticsearch access for advanced search capabilities.
        It requires Elasticsearch to be configured and accessible on your Nuxeo server.
        
        ⚠️ For most use cases, use 'natural_search' or 'search' tools instead, which work
        without Elasticsearch and use Nuxeo's built-in query capabilities.

        Args:
            query: Natural language search query (e.g., "PDFs created last week by John")
            limit: Maximum number of results to return (default: 20, max: 100)
            offset: Pagination offset for results (default: 0)

        Returns:
            JSON string containing search results with document metadata and highlights

        Examples:
            - "documents created today"
            - "files modified by alice in /workspaces"
            - "PDFs containing annual report"
            - "images from last month"
        """
        try:
            # Import here to avoid circular dependency
            from .es_passthrough import ElasticsearchPassthrough
            import requests

            # Get current user context (in real implementation, this would come from auth)
            # For demo, using default admin credentials
            principal = "Administrator"
            groups = ["Administrators", "members", "Everyone"]

            # Limit max results
            if limit > 100:
                limit = 100

            # Initialize passthrough with Nuxeo URL and auth
            # Get the Nuxeo URL and auth from the global nuxeo client
            nuxeo_url = nuxeo.client.host
            auth = nuxeo.client.auth
            
            passthrough = ElasticsearchPassthrough(nuxeo_url=nuxeo_url, auth=auth)
            
            # Check if Elasticsearch is accessible through Nuxeo passthrough
            try:
                # Test with a simple match_all query
                test_url = f"{passthrough.base_url}/nuxeo/_search"
                test_query = {"query": {"match_all": {}}, "size": 0}
                response = requests.post(
                    test_url, 
                    json=test_query,
                    auth=auth,
                    timeout=2
                )
                response.raise_for_status()
            except (requests.RequestException, requests.ConnectionError) as e:
                logger.warning(f"Elasticsearch not accessible at {passthrough.base_url}: {e}")
                return json.dumps({
                    "success": False,
                    "error": "Elasticsearch not available",
                    "message": f"Elasticsearch passthrough is not accessible. Please use 'natural_search' or 'search' tools instead.",
                    "alternative_tools": ["natural_search", "search"]
                })

            # Execute search
            results = passthrough.search_repository(
                query=query,
                principal=principal,
                groups=groups,
                limit=limit,
                offset=offset,
            )

            # Format response
            response = {
                "success": True,
                "total": results["total"],
                "query_time_ms": results["query_time_ms"],
                "results": results["results"][:limit],
                "query": query,
                "translated_query": results.get("translated_query", ""),
            }

            return json.dumps(response, indent=2)

        except PermissionError as e:
            return json.dumps(
                {"success": False, "error": "Permission denied", "message": str(e)}
            )
        except Exception as e:
            logger.error(f"Repository search error: {e}")
            return json.dumps(
                {"success": False, "error": "Search failed", "message": str(e)}
            )

    @mcp.tool()
    async def search_audit(query: str, limit: int = 20, offset: int = 0) -> str:
        """
        [REQUIRES ELASTICSEARCH] Search the Nuxeo audit logs (Admin only).

        This tool provides search capabilities across audit logs for tracking
        system activity, document modifications, and user actions. Requires both
        administrator privileges and Elasticsearch to be configured and accessible.

        Args:
            query: Natural language audit query (e.g., "deletions by admin yesterday")
            limit: Maximum number of results to return (default: 20, max: 100)
            offset: Pagination offset for results (default: 0)

        Returns:
            JSON string containing audit entries with event details

        Examples:
            - "show all deletions from yesterday"
            - "what did alice modify this week"
            - "document creations in the last month"
            - "failed login attempts today"
        """
        try:
            # Import here to avoid circular dependency
            from .es_passthrough import ElasticsearchPassthrough
            import requests

            # For audit, must be administrator
            principal = "Administrator"
            groups = ["Administrators"]

            # Limit max results
            if limit > 100:
                limit = 100

            # Initialize passthrough with Nuxeo URL and auth
            # Get the Nuxeo URL and auth from the global nuxeo client
            nuxeo_url = nuxeo.client.host
            auth = nuxeo.client.auth
            
            passthrough = ElasticsearchPassthrough(nuxeo_url=nuxeo_url, auth=auth)
            
            # Check if Elasticsearch is accessible through Nuxeo passthrough
            try:
                # Test with a simple match_all query on audit index
                test_url = f"{passthrough.base_url}/audit/_search"
                test_query = {"query": {"match_all": {}}, "size": 0}
                response = requests.post(
                    test_url, 
                    json=test_query,
                    auth=auth,
                    timeout=2
                )
                response.raise_for_status()
            except (requests.RequestException, requests.ConnectionError) as e:
                logger.warning(f"Elasticsearch audit index not accessible at {passthrough.base_url}: {e}")
                return json.dumps({
                    "success": False,
                    "error": "Elasticsearch audit not available",
                    "message": f"Elasticsearch audit index is not accessible. Audit logs require Elasticsearch.",
                    "alternative": "Check your Nuxeo server's Elasticsearch configuration"
                })

            # Execute search
            results = passthrough.search_audit(
                query=query,
                principal=principal,
                groups=groups,
                limit=limit,
                offset=offset,
            )

            # Format response
            response = {
                "success": True,
                "total": results["total"],
                "query_time_ms": results["query_time_ms"],
                "results": results["results"][:limit],
                "query": query,
                "translated_query": results.get("translated_query", ""),
            }

            return json.dumps(response, indent=2)

        except PermissionError as e:
            return json.dumps(
                {
                    "success": False,
                    "error": "Permission denied",
                    "message": "Only administrators can access audit logs",
                }
            )
        except Exception as e:
            logger.error(f"Audit search error: {e}")
            return json.dumps(
                {"success": False, "error": "Audit search failed", "message": str(e)}
            )

    """
    Register MCP tools with the FastMCP server.

    Args:
        mcp: The FastMCP server instance
        nuxeo: The Nuxeo client instance
        auth_middleware: Optional authentication middleware to wrap tools
    """
    
    # Import server manager
    from nuxeo_mcp.server_manager import get_server_manager, ServerConfig
    from nuxeo.client import Nuxeo
    
    # Get the global server manager
    server_manager = get_server_manager()
    
    # Create a mutable container for the Nuxeo client
    # This allows us to switch servers dynamically
    class NuxeoClientContainer:
        def __init__(self, initial_client):
            self.client = initial_client
            self.current_server_name = None
            
        def switch_to_server(self, server_config: ServerConfig):
            """Switch to a different Nuxeo server."""
            try:
                new_client = Nuxeo(
                    host=server_config.url,
                    auth=(server_config.username, server_config.password)
                )
                # Test the connection
                new_client.client.server_info()
                self.client = new_client
                self.current_server_name = server_config.name
                logger.info(f"Switched to server: {server_config.name}")
                return True
            except Exception as e:
                logger.error(f"Failed to connect to server {server_config.name}: {e}")
                return False
    
    # Create the container with the initial client
    nuxeo_container = NuxeoClientContainer(nuxeo)
    
    # Override the nuxeo variable to use the container's client
    # This allows all tools to automatically use the current server
    nuxeo = nuxeo_container.client
    
    # Tool: List available servers
    @mcp.tool(
        name="list_servers",
        description="List all configured Nuxeo servers"
    )
    def list_servers() -> Dict[str, Any]:
        """
        List all configured Nuxeo servers.
        
        Returns:
            Dictionary containing all server configurations and their status
        """
        servers = server_manager.list_servers()
        active_server = server_manager.get_active_server()
        
        return {
            "servers": servers,
            "active_server": active_server.name if active_server else None,
            "message": f"Currently connected to: {active_server.name if active_server else 'None'}"
        }
    
    # Tool: Switch server
    @mcp.tool(
        name="switch_server",
        description="Switch to a different Nuxeo server"
    )
    def switch_server(server_name: str) -> Dict[str, Any]:
        """
        Switch to a different Nuxeo server.
        
        Args:
            server_name: Name of the server to switch to (e.g., 'demo', 'local')
            
        Returns:
            Status of the switch operation
        """
        server_config = server_manager.get_server(server_name)
        if not server_config:
            available = list(server_manager.servers.keys())
            return {
                "status": "error",
                "message": f"Server '{server_name}' not found",
                "available_servers": available
            }
        
        # Try to switch the client
        if nuxeo_container.switch_to_server(server_config):
            # Update the global nuxeo reference for all tools
            nonlocal nuxeo
            nuxeo = nuxeo_container.client
            
            # Save the active server
            server_manager.set_active_server(server_name)
            
            return {
                "status": "success",
                "message": f"Successfully switched to server: {server_name}",
                "server": {
                    "name": server_config.name,
                    "url": server_config.url,
                    "description": server_config.description
                }
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to connect to server: {server_name}",
                "error": "Connection failed - check server URL and credentials"
            }
    
    # Tool: Get current server
    @mcp.tool(
        name="get_current_server",
        description="Get information about the currently active Nuxeo server"
    )
    def get_current_server() -> Dict[str, Any]:
        """
        Get information about the currently active Nuxeo server.
        
        Returns:
            Information about the current server
        """
        active_server = server_manager.get_active_server()
        if active_server:
            # Try to get server info from Nuxeo
            try:
                server_info = nuxeo.client.server_info()
                return {
                    "status": "connected",
                    "server": {
                        "name": active_server.name,
                        "url": active_server.url,
                        "description": active_server.description
                    },
                    "nuxeo_info": server_info
                }
            except Exception as e:
                return {
                    "status": "configured",
                    "server": {
                        "name": active_server.name,
                        "url": active_server.url,
                        "description": active_server.description
                    },
                    "error": f"Cannot connect to server: {str(e)}"
                }
        else:
            return {
                "status": "not_configured",
                "message": "No server is currently active. Use 'switch_server' to select one.",
                "available_servers": list(server_manager.servers.keys())
            }
    
    # Tool: Add server configuration
    @mcp.tool(
        name="add_server",
        description="Add a new Nuxeo server configuration"
    )
    def add_server(
        name: str,
        url: str,
        username: str,
        password: str,
        description: str = "",
        set_as_active: bool = False
    ) -> Dict[str, Any]:
        """
        Add a new Nuxeo server configuration.
        
        Args:
            name: Unique name for the server (e.g., 'production', 'staging')
            url: URL of the Nuxeo server (e.g., 'https://nuxeo.example.com/nuxeo')
            username: Username for authentication
            password: Password for authentication
            description: Optional description of the server
            set_as_active: Whether to immediately switch to this server
            
        Returns:
            Status of the operation
        """
        # Check if server already exists
        if server_manager.get_server(name):
            return {
                "status": "error",
                "message": f"Server '{name}' already exists. Use a different name or remove the existing one first."
            }
        
        # Create new server config
        server_config = ServerConfig(
            name=name,
            url=url,
            username=username,
            password=password,
            description=description or f"Nuxeo server at {url}",
            is_default=False
        )
        
        # Test the connection
        try:
            test_client = Nuxeo(
                host=url,
                auth=(username, password)
            )
            test_client.client.server_info()
        except Exception as e:
            return {
                "status": "warning",
                "message": f"Server added but connection test failed: {str(e)}",
                "server": server_config.to_dict()
            }
        
        # Add the server
        server_manager.add_server(server_config)
        
        # Switch to it if requested
        if set_as_active:
            switch_result = switch_server(name)
            return {
                "status": "success",
                "message": f"Server '{name}' added and activated",
                "server": server_config.to_dict(),
                "switch_result": switch_result
            }
        
        return {
            "status": "success",
            "message": f"Server '{name}' added successfully",
            "server": server_config.to_dict()
        }
    
    # Tool: Remove server configuration
    @mcp.tool(
        name="remove_server",
        description="Remove a Nuxeo server configuration"
    )
    def remove_server(name: str) -> Dict[str, Any]:
        """
        Remove a Nuxeo server configuration.
        
        Args:
            name: Name of the server to remove
            
        Returns:
            Status of the operation
        """
        if not server_manager.get_server(name):
            return {
                "status": "error",
                "message": f"Server '{name}' not found"
            }
        
        # Check if it's the active server
        active_server = server_manager.get_active_server()
        is_active = active_server and active_server.name == name
        
        server_manager.remove_server(name)
        
        return {
            "status": "success",
            "message": f"Server '{name}' removed successfully",
            "was_active": is_active,
            "note": "You may need to switch to another server" if is_active else None
        }
    
    # Check if we need server selection on first use
    # Skip if server is pre-configured (e.g., from Docker environment variables)
    if not skip_server_selection and server_manager.needs_server_selection():
        # Set up with the default server
        active_server = server_manager.get_active_server()
        if active_server:
            nuxeo_container.switch_to_server(active_server)
            nuxeo = nuxeo_container.client
            server_manager.set_active_server(active_server.name)
