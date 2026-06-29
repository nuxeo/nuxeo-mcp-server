"""Elasticsearch Passthrough Handler for Nuxeo MCP."""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests

from .nl_parser import NaturalLanguageParser
from .es_query_builder import ElasticsearchQueryBuilder

logger = logging.getLogger(__name__)


class ElasticsearchPassthrough:
    """Handle Elasticsearch passthrough requests via Nuxeo's /site/es endpoint.

    ACL enforcement is handled server-side by the Nuxeo passthrough — this class
    forwards queries as-is and does not inject any Python-side ACL filter.
    """

    def __init__(self, nuxeo_url: Optional[str] = None, auth: Optional[tuple] = None):
        """Initialize Elasticsearch passthrough.

        Args:
            nuxeo_url: Base URL for Nuxeo server
            auth: Authentication tuple (username, password)
        """
        if nuxeo_url:
            nuxeo_url = nuxeo_url.rstrip("/")
            self.base_url = f"{nuxeo_url}/site/es"
        else:
            self.base_url = os.getenv(
                "elasticsearch.httpReadOnly.baseUrl", "http://localhost:9200"
            )

        self.auth = auth
        self.nl_parser = NaturalLanguageParser()
        self.es_builder = ElasticsearchQueryBuilder()

    def search_repository(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        source_fields: Optional[List[str]] = None,
        highlight_fragment_size: int = 150,
        highlight_number_of_fragments: int = 3,
    ) -> Dict[str, Any]:
        """Search repository index using natural language.

        The Nuxeo passthrough at /site/es enforces ACLs server-side for the
        authenticated user; no client-side ACL filter is needed.

        Args:
            query: Natural language search query
            limit: Maximum number of results
            offset: Pagination offset
            source_fields: Fields to include in response
            highlight_fragment_size: Size in chars of each highlight fragment (default 150)
            highlight_number_of_fragments: Number of highlight fragments to return (default 3)

        Returns:
            Formatted search results

        Raises:
            Exception: For Elasticsearch errors
        """
        es_request = self.nl_parser.parse_to_elasticsearch(
            query,
            index="repository",
            include_sort=True,
            include_pagination=True,
            include_highlight=True,
            highlight_fragment_size=highlight_fragment_size,
            highlight_number_of_fragments=highlight_number_of_fragments,
            source_includes=source_fields,
        )

        es_request["size"] = max(0, limit)
        if offset:
            es_request["from"] = offset

        response = self.execute_query(index="nuxeo", query=es_request)

        return self._format_repository_results(
            response, json.dumps(es_request), source_fields=source_fields
        )

    def search_audit(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search audit index using natural language (admin only).

        The Nuxeo passthrough enforces admin-only access server-side and returns
        HTTP 403 for non-administrator users. If called directly without the
        tools-layer probe, a server-side 403 will propagate as an Exception.

        Args:
            query: Natural language search query
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            Formatted audit results

        Raises:
            Exception: For Elasticsearch errors
        """
        es_request = self.nl_parser.parse_to_elasticsearch(
            query, index="audit", include_sort=True, include_pagination=True
        )

        es_request["size"] = max(0, limit)
        if offset:
            es_request["from"] = offset

        response = self.execute_query(index="audit", query=es_request)

        return self._format_audit_results(response, json.dumps(es_request))

    def execute_query(
        self, index: str, query: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an Elasticsearch query via the Nuxeo passthrough endpoint.

        The query is forwarded as-is; ACL enforcement is handled server-side.

        Args:
            index: Target index name
            query: Elasticsearch query/request body

        Returns:
            Raw Elasticsearch response

        Raises:
            Exception: For connection or query errors
        """
        try:
            url = f"{self.base_url}/{index}/_search"
            headers = {"Content-Type": "application/json"}

            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(query),
                auth=self.auth,
                timeout=30,
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

    def _format_repository_results(
        self,
        es_response: Dict[str, Any],
        translated_query: str,
        source_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Format Elasticsearch results for repository search.

        Args:
            es_response: Raw Elasticsearch response
            translated_query: The translated ES query for debugging
            source_fields: Extra source fields requested by the caller

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

            if source_fields:
                for key in source_fields:
                    if key not in result and key in source:
                        result[key] = source[key]

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
