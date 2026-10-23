"""Elasticsearch Passthrough Handler for Nuxeo MCP."""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests


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

