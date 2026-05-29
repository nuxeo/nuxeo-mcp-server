"""Elasticsearch Passthrough Handler for Nuxeo MCP."""

import os
import json
import logging
from typing import Dict, List, Any, Optional
import requests

from .nl_parser import NaturalLanguageParser
from .es_query_builder import ElasticsearchQueryBuilder
from .search_filters import (
    SearchRequestFilter,
    DefaultSearchRequestFilter,
    AuditRequestFilter,
    WorkflowAuditRequestFilter,
)

logger = logging.getLogger(__name__)


class ElasticsearchPassthrough:
    """Handle Elasticsearch passthrough requests with security filtering."""

    def __init__(self, nuxeo_url: Optional[str] = None, auth: Optional[tuple] = None):
        """Initialize Elasticsearch passthrough.

        Args:
            nuxeo_url: Base URL for Nuxeo server
            auth: Authentication tuple (username, password)
        """
        # Use Nuxeo's ES passthrough endpoint
        if nuxeo_url:
            # Remove trailing slash if present
            nuxeo_url = nuxeo_url.rstrip('/')
            # Use the /site/es/ passthrough endpoint
            self.base_url = f"{nuxeo_url}/site/es"
        else:
            self.base_url = os.getenv(
                "elasticsearch.httpReadOnly.baseUrl", "http://localhost:9200"
            )
        
        self.auth = auth
        self.nl_parser = NaturalLanguageParser()
        self.es_builder = ElasticsearchQueryBuilder()

        # Initialize filters
        self.filters = {
            "nuxeo": DefaultSearchRequestFilter(),
            "repository": DefaultSearchRequestFilter(),
            "audit": AuditRequestFilter(),
            "audit_wf": WorkflowAuditRequestFilter(),
        }

    def search_repository(
        self,
        query: str,
        principal: str,
        groups: List[str],
        limit: int = 20,
        offset: int = 0,
        source_fields: Optional[List[str]] = None,
        highlight_fragment_size: int = 150,
        highlight_number_of_fragments: int = 3,
    ) -> Dict[str, Any]:
        """Search repository index using natural language.

        Args:
            query: Natural language search query
            principal: User principal making the request
            groups: Groups the user belongs to
            limit: Maximum number of results
            offset: Pagination offset
            source_fields: Fields to include in response
            highlight_fragment_size: Size in chars of each highlight fragment (default 150)
            highlight_number_of_fragments: Number of highlight fragments to return (default 3)

        Returns:
            Formatted search results

        Raises:
            PermissionError: If user lacks permission
            Exception: For Elasticsearch errors
        """
        # Parse natural language to Elasticsearch DSL
        es_request = self.nl_parser.parse_to_elasticsearch(
            query,
            index="repository",
            include_sort=True,
            include_pagination=True,
            include_highlight=True,
            highlight_fragment_size=highlight_fragment_size,
            highlight_number_of_fragments=highlight_number_of_fragments,
            apply_acl=True,
            user_principals=[principal] + groups,
            source_includes=source_fields,
        )

        # Override pagination if provided
        if limit:
            es_request["size"] = limit
        if offset:
            es_request["from"] = offset

        # Execute query
        response = self.execute_query(
            index="nuxeo", query=es_request, principal=principal, groups=groups
        )

        # Format results
        return self._format_repository_results(response, json.dumps(es_request), source_fields=source_fields)

    def search_audit(
        self,
        query: str,
        principal: str,
        groups: List[str],
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search audit index using natural language.

        Args:
            query: Natural language search query
            principal: User principal making the request
            groups: Groups the user belongs to
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            Formatted audit results

        Raises:
            PermissionError: If user is not administrator
            Exception: For Elasticsearch errors
        """
        # Check admin permission first
        audit_filter = self.filters["audit"]
        if not audit_filter._is_admin(principal, groups):
            raise PermissionError(
                f"User {principal} is not authorized to query audit logs"
            )

        # Parse natural language to Elasticsearch DSL
        es_request = self.nl_parser.parse_to_elasticsearch(
            query, index="audit", include_sort=True, include_pagination=True
        )

        # Override pagination if provided
        if limit:
            es_request["size"] = limit
        if offset:
            es_request["from"] = offset

        # Execute query (no ACL filter for audit)
        response = self.execute_query(
            index="audit", query=es_request, principal=principal, groups=groups
        )

        # Format results
        return self._format_audit_results(response, json.dumps(es_request))

    def execute_query(
        self, index: str, query: Dict[str, Any], principal: str, groups: List[str]
    ) -> Dict[str, Any]:
        """Execute Elasticsearch query with security filtering.

        Args:
            index: Target index name
            query: Elasticsearch query/request body
            principal: User principal
            groups: User groups

        Returns:
            Raw Elasticsearch response

        Raises:
            PermissionError: If user lacks permission
            Exception: For connection or query errors
        """
        # Get appropriate filter for index
        filter_instance = self._get_filter_for_index(index)

        # Extract just the query part if full request provided
        if "query" in query:
            filtered_query = filter_instance.apply(query["query"], principal, groups)
            final_request = query.copy()
            final_request["query"] = filtered_query
        else:
            # Assume the entire dict is the query
            filtered_query = filter_instance.apply(query, principal, groups)
            final_request = {"query": filtered_query}

        # Execute request against Elasticsearch
        try:
            url = f"{self.base_url}/{index}/_search"
            headers = {"Content-Type": "application/json"}

            response = requests.post(
                url, 
                headers=headers, 
                data=json.dumps(final_request), 
                auth=self.auth,  # Add authentication
                timeout=30
            )

            if response.status_code != 200:
                raise Exception(
                    f"Elasticsearch error: {response.status_code} - {response.text}"
                )

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Elasticsearch connection error: {e}")
            raise Exception(f"Failed to connect to Elasticsearch: {e}")
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            raise

    def _get_filter_for_index(self, index: str) -> SearchRequestFilter:
        """Get the appropriate filter for an index.

        Args:
            index: Index name

        Returns:
            SearchRequestFilter instance
        """
        return self.filters.get(index, self.filters["nuxeo"])

    def _format_repository_results(
        self, es_response: Dict[str, Any], translated_query: str, source_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Format Elasticsearch results for repository search.

        Args:
            es_response: Raw Elasticsearch response
            translated_query: The translated ES query for debugging

        Returns:
            Formatted results for MCP response
        """
        hits = es_response.get("hits", {})
        total = hits.get("total", {})
        if isinstance(total, dict):
            total_value = total.get("value", 0)
        else:
            total_value = total

        results = []
        for hit in hits.get("hits", []):
            source = hit.get("_source", {})
            result = {
                "uid": source.get("uid", source.get("ecm:uuid", "")),
                "title": source.get("dc:title", ""),
                "path": source.get("ecm:path", ""),
                "type": source.get("ecm:primaryType", ""),
                "modified": source.get("dc:modified", ""),
                "creator": source.get("dc:creator", ""),
            }

            # Add any explicitly requested extra source fields
            if source_fields:
                for key in source_fields:
                    if key not in result and key in source:
                        result[key] = source[key]

            # Add highlights if available
            if "highlight" in hit:
                highlights = []
                for field_highlights in hit["highlight"].values():
                    highlights.extend(field_highlights)
                result["highlights"] = highlights

            results.append(result)

        return {
            "results": results,
            "total": total_value,
            "query_time_ms": es_response.get("took", 0),
            "translated_query": translated_query,
        }

    def _format_audit_results(
        self, es_response: Dict[str, Any], translated_query: str
    ) -> Dict[str, Any]:
        """Format Elasticsearch results for audit search.

        Args:
            es_response: Raw Elasticsearch response
            translated_query: The translated ES query for debugging

        Returns:
            Formatted results for MCP response
        """
        hits = es_response.get("hits", {})
        total = hits.get("total", {})
        if isinstance(total, dict):
            total_value = total.get("value", 0)
        else:
            total_value = total

        results = []
        for hit in hits.get("hits", []):
            source = hit.get("_source", {})
            result = {
                "id": source.get("id", ""),
                "eventId": source.get("eventId", ""),
                "eventDate": source.get("eventDate", ""),
                "docUUID": source.get("docUUID", ""),
                "docPath": source.get("docPath", ""),
                "principalName": source.get("principalName", ""),
                "category": source.get("category", ""),
                "comment": source.get("comment", ""),
            }
            results.append(result)

        return {
            "results": results,
            "total": total_value,
            "query_time_ms": es_response.get("took", 0),
            "translated_query": translated_query,
        }
