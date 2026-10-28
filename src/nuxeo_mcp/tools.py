#!/usr/bin/env python3
"""
Nuxeo MCP Server tools.

This module defines the tools for the Nuxeo MCP Server.
"""

import json
import logging
import os
from typing import Annotated, Any, Callable, Dict, List, Optional

from fastmcp.exceptions import ToolError
from mcp.types import ImageContent as Image
from nuxeo.models import Document
from pydantic import BaseModel, Field, model_validator

from nuxeo_mcp import query_dsl
from nuxeo_mcp.annotations import TOOL_ANNOTATIONS
from nuxeo_mcp.query_dsl import QueryDslRejected, apply_guardrails
from nuxeo_mcp.search_models import (
    MODE_NXQL,
    MODE_SEMANTIC,
    SEARCH_MODES,
    SearchResult,
    to_search_result,
)
from nuxeo_mcp.utility import (
    format,
    format_doc,
    format_docs,
    is_uuid,
    return_blob,
)

# Configure logging
logger = logging.getLogger("nuxeo_mcp.tools")

# Type aliases
ToolFunction = Callable[[Dict[str, Any]], Dict[str, Any]]

# MODE_SEMANTIC stays in the contract but is not advertised until it is
# implemented: a listed mode invites a call that can only fail.
_IMPLEMENTED_MODES = (MODE_NXQL,)


class DocRef(BaseModel):
    path: Annotated[str | None, Field(description="Repository path")] = None
    uid: Annotated[str | None, Field(description="Nuxeo UID")] = None

    @model_validator(mode="after")
    def one_of_path_or_uid(self) -> "DocRef":
        if bool(self.path) == bool(self.uid):  # both or neither
            raise ValueError("Provide *exactly* one of 'path' or 'uid'")
        return self


from typing import Union

# Timeout in seconds for search engine connectivity probes
ES_PROBE_TIMEOUT = 10


def register_tools(mcp, nuxeo) -> None:
    """
    Register MCP tools with the FastMCP server.

    Args:
        mcp: The FastMCP server instance
        nuxeo: The Nuxeo client instance
    """

    def tool(**kwargs):
        """Register a tool, attaching its declared safety annotations by name.

        Going through here rather than @mcp.tool directly keeps the annotations
        in one readable table and makes an unannotated tool a startup failure
        rather than something a client only notices at call time.
        """
        name = kwargs.get("name")
        annotations = TOOL_ANNOTATIONS.get(name)
        if annotations is None:
            raise RuntimeError(
                f"Tool {name!r} has no entry in TOOL_ANNOTATIONS. Declare its "
                "safety hints in nuxeo_mcp.annotations before registering it."
            )
        kwargs.setdefault("annotations", annotations)
        return mcp.tool(**kwargs)

    # Tool: Get repository info
    @tool(
        name="nuxeo_get_repository_info",
        description="Get information about the Nuxeo repository",
    )
    def nuxeo_get_repository_info() -> Dict[str, Any]:
        """
        Get information about the Nuxeo repository.

        Args: None

        Returns:
            Information about the Nuxeo repository
        """

        server_info = nuxeo.client.server_info()

        return server_info

    @tool(name="nuxeo_list_children", description="list children of a folder document ")
    def nuxeo_list_children(
        ref: Annotated[
            str, Field(description="reference can be either a uuid or a path ")
        ],
        as_resource: Annotated[
            bool, Field(description="Return Document as nuxeo:// resource")
        ] = False,
    ) -> str:
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

    @tool(
        name="nuxeo_list_document_types",
        description="Get information about document types and schemas defined in the Nuxeo server",
    )
    def nuxeo_list_document_types() -> Dict[str, Any]:
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

    @tool(
        name="nuxeo_get_metadata_schema",
        description="Get detailed information about schemas defined in the Nuxeo server",
    )
    def nuxeo_get_metadata_schema() -> List[Dict[str, Any]]:
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

    @tool(
        name="nuxeo_list_operations",
        description="Get information about available Automation Operations in the Nuxeo server",
    )
    def nuxeo_list_operations() -> Dict[str, Any]:
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

    @tool(
        name="nuxeo_execute_operation",
        description="Execute a Nuxeo Operation with the specified parameters and input",
    )
    def nuxeo_execute_operation(
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

    @tool(
        name="nuxeo_create_document",
        description=(
            "Create a new document in the Nuxeo repository with optional file "
            "attachment. To confirm the result, read it back with "
            "nuxeo_get_document; search may not see it yet."
        ),
    )
    def nuxeo_create_document(
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
        doc_title = (
            doc.properties.get("dc:title", name) if hasattr(doc, "properties") else name
        )

        return {
            "status": "success",
            "message": f"Document '{name}' created successfully",
            "uid": doc.uid,
            "path": doc.path,
            "title": doc_title,
            "type": type,
            "url": f"{nuxeo.client.host}/ui/#!/browse{doc.path}",
            "details": format_doc(doc),  # Include full formatted details as a string
        }

    @tool(
        name="nuxeo_get_document",
        description="Get a document from the Nuxeo repository",
    )
    def nuxeo_get_document(
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
                # Surface as a tool error: an error dict would be reported to the
                # client as a successful call and violates the return type.
                raise ToolError(f"Conversion failed: {e}")

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

    @tool(
        name="nuxeo_update_metadata",
        description="Update an existing document in the Nuxeo repository",
    )
    def nuxeo_update_metadata(
        path: str = None, uid: str = None, properties: Union[Dict[str, Any], str] = None
    ) -> Dict[str, str] | str:
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

    @tool(
        name="nuxeo_delete_document",
        description=(
            "Delete a document from the Nuxeo repository, by UID. To delete by "
            "path, read the UID with nuxeo_get_document first."
        ),
    )
    def nuxeo_delete_document(uid: str = None) -> Dict[str, Any]:
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

    @tool(
        name="nuxeo_move_document",
        description=(
            "Move a document, identified by UID, under the folder at target_path. "
            "Not idempotent: repeating the call renames the document. To move by "
            "path, read the UID with nuxeo_get_document first."
        ),
    )
    def nuxeo_move_document(
        document_uid: str, target_path: str, new_name: str = None
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
                "title": (
                    result.properties.get("dc:title", "")
                    if hasattr(result, "properties")
                    else ""
                ),
                "url": f"{nuxeo.client.host}/ui/#!/browse{result.path}",
            }
        else:
            return {
                "status": "success",
                "message": f"Document moved to {target_path}",
                "details": str(result),
            }

    # --- Search -------------------------------------------------------------
    #
    # One tool for repository search, one escape hatch for the search engine.
    #
    # nuxeo_search_documents keeps a single envelope across every mode: a mode
    # changes how the caller expresses the query, never the shape that comes
    # back, so a model never has to branch on the result before reading it.
    #
    # nuxeo_search_documents_with_query_dsl is deliberately separate rather than
    # a fourth mode: its input is an arbitrary engine query, which makes it
    # open-world where the other modes are closed, and its value is fidelity to
    # the engine response -- the opposite of the normalized envelope.

    _SEARCH_USAGE = (
        "nuxeo_search_documents needs a NXQL statement. Start from the default\n"
        "filter, or versions and system documents come back:\n"
        "  SELECT * FROM Document WHERE ecm:fulltext = 'contract'\n"
        "    AND ecm:mixinType != 'HiddenInNavigation' AND ecm:isProxy = 0\n"
        "    AND ecm:isVersion = 0 AND ecm:isTrashed = 0\n"
        "\n"
        "See the nuxeo://nxql-guide resource for the full NXQL syntax, and "
        "nuxeo_search_documents_with_query_dsl for aggregations and highlighting."
    )

    @tool(
        name="nuxeo_search_documents",
        description=(
            "Search documents in the Nuxeo repository with a NXQL statement. Read "
            "nuxeo://nxql-guide first: it gives the default filter that keeps "
            "versions and system documents out. Returns a normalized result "
            "envelope. For counts, groupings or aggregations, use "
            "nuxeo_search_documents_with_query_dsl instead. "
            "Recently created or modified documents may take a few seconds to "
            "appear; read them by uid or path with nuxeo_get_document instead."
        ),
    )
    def nuxeo_search_documents(
        query: str = "",
        mode: str = MODE_NXQL,
        page_size: int = 20,
        page_index: int = 0,
    ) -> SearchResult:
        """Search the repository and return the normalized envelope.

        Args:
            query: A NXQL statement.
            mode: "nxql". Kept as a parameter so other query modes can be added
                without changing the contract.
            page_size: Documents per page.
            page_index: Zero-based page to retrieve.

        Returns:
            SearchResult. ``interpretedQuery`` reports the NXQL executed.

        Raises:
            ToolError: on an empty query, an unknown mode, or a mode that is not
                implemented yet.
        """
        if not query or not query.strip():
            raise ToolError(_SEARCH_USAGE)

        if mode == MODE_SEMANTIC:
            raise ToolError(
                "mode='semantic' is not implemented yet in this MCP server. Use "
                "mode='nxql'."
            )

        if mode not in SEARCH_MODES:
            raise ToolError(
                f"Unknown mode {mode!r}. Supported modes: "
                f"{', '.join(_IMPLEMENTED_MODES)}."
            )

        page_size = max(1, min(page_size, 100))
        page_index = max(0, page_index)

        try:
            query_result = nuxeo.client.query(
                query, params={"pageSize": page_size, "currentPageIndex": page_index}
            )
        except Exception as e:
            raise ToolError(f"Search failed for query {query!r}: {e}")

        return to_search_result(
            query_result,
            mode=mode,
            interpreted_query=query,
            page_size=page_size,
            page_index=page_index,
        )

    def _run_query_dsl(
        index: str,
        query: Optional[Dict[str, Any]],
        default_source: Optional[List[str]] = None,
        guide: str = "nuxeo://query-dsl-guide",
    ) -> Dict[str, Any]:
        """Execute a guarded Query DSL request against one Nuxeo search index.

        Nuxeo's passthrough applies the caller's ACLs and, for the audit index,
        rejects non-administrators with HTTP 403. What it does not bound is cost:
        an unqualified match_all with size 10000 returns megabytes, and Painless
        executes. Those bounds are applied here.
        """
        if not query:
            raise ToolError(query_dsl.USAGE)

        try:
            guarded = apply_guardrails(query, default_source=default_source)
        except QueryDslRejected as e:
            raise ToolError(str(e))

        from .es_passthrough import ElasticsearchPassthrough, PassthroughError

        passthrough = ElasticsearchPassthrough(
            nuxeo_url=os.environ.get("NUXEO_URL", nuxeo.client.host),
            auth=nuxeo.client.auth,
        )

        try:
            response = passthrough.execute_query(index=index, query=guarded)
        except PassthroughError as e:
            raise ToolError(str(e))
        except Exception as e:
            raise ToolError(f"Query DSL search failed on index {index!r}: {e}")

        total = response.get("hits", {}).get("total")
        matched = total.get("value") if isinstance(total, dict) else total
        if matched == 0:
            # Silently empty results are the main failure mode here: a hallucinated
            # field name returns 200 with no hits, which reads as "nothing matches".
            # Keyed on the match count, not the hit list: size 0 asks for no hits.
            response["_nuxeo_hint"] = (
                f"No hits. Verify field names against the {guide} resource -- "
                "unknown fields match nothing rather than erroring."
            )
        response["_nuxeo_executed_query"] = guarded

        # Measured on the assembled payload, not on the engine response: the echoed
        # query is part of what reaches the context window, and a large terms or ids
        # clause can dwarf a response that carries no hits at all.
        size = len(json.dumps(response))
        if size > query_dsl.MAX_RESPONSE_BYTES:
            raise ToolError(
                f"Response is {size} bytes, over the {query_dsl.MAX_RESPONSE_BYTES} "
                "byte limit. Narrow it with a smaller 'size', a '_source' include "
                "list, or an aggregation with 'size': 0."
            )

        return response

    @tool(
        name="nuxeo_search_documents_with_query_dsl",
        description=(
            "Run a raw OpenSearch/Elasticsearch Query DSL request against the Nuxeo "
            "repository index and return the engine response, plus two server-added "
            "keys: _nuxeo_executed_query (the guarded request) and _nuxeo_hint (set "
            "on empty results). Use this for aggregations, highlighting, sorting and "
            "any query the normalized search cannot express. Read "
            "nuxeo://query-dsl-guide first for the field names. "
            "Recently created or modified documents may take a few seconds to "
            "appear; read them by uid or path with nuxeo_get_document instead."
        ),
    )
    def nuxeo_search_documents_with_query_dsl(
        query: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Search the repository index with a Query DSL body.

        Args:
            query: An OpenSearch/Elasticsearch request body.

        Returns:
            The engine response for the guarded request, with the server-added
            ``_nuxeo_executed_query`` and, on empty results, ``_nuxeo_hint``.

        Raises:
            ToolError: on a missing body, a scripted query, an engine error, or a
                response over the size limit.
        """
        return _run_query_dsl(
            "nuxeo", query, default_source=query_dsl.DEFAULT_SOURCE_FIELDS
        )

    @tool(
        name="nuxeo_search_audit_with_query_dsl",
        description=(
            "Run a raw OpenSearch/Elasticsearch Query DSL request against the Nuxeo "
            "audit log index and return the engine response, plus two server-added "
            "keys: _nuxeo_executed_query (the guarded request) and _nuxeo_hint (set "
            "on empty results). Administrators only. Read "
            "nuxeo://audit-query-dsl-guide first for the field names."
        ),
    )
    def nuxeo_search_audit_with_query_dsl(
        query: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Search the audit index with a Query DSL body.

        Audit entries are events, not documents, so they are returned in the engine
        shape rather than the normalized document envelope.

        Args:
            query: An OpenSearch/Elasticsearch request body.

        Returns:
            The engine response for the guarded request, with the server-added
            ``_nuxeo_executed_query`` and, on empty results, ``_nuxeo_hint``.

        Raises:
            ToolError: on a missing body, a scripted query, an engine error
                (including HTTP 403 for non-administrators), or a response over
                the size limit.
        """
        if not query:
            raise ToolError(query_dsl.AUDIT_USAGE)
        # No _source default: audit entries are small and share no field names
        # with the repository index.
        return _run_query_dsl("audit", query, guide="nuxeo://audit-query-dsl-guide")

    # Server resolution is deliberately not exposed as tools, and is not mutable at
    # runtime. Streamable HTTP is stateless and shared between agents, so a tool that
    # switched the active server would leak one caller's repository into another
    # caller's next call, and a tool that registered a server URL would let a model
    # drive outbound requests. Which Nuxeo this process talks to is deployment
    # configuration: NUXEO_URL and the credentials, read once at startup.
