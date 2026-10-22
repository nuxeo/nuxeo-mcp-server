"""Tests for Elasticsearch Passthrough Handler."""

import json
from unittest.mock import Mock, patch

import pytest

from nuxeo_mcp.es_passthrough import ElasticsearchPassthrough


class TestElasticsearchPassthrough:
    """Test Elasticsearch Passthrough functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.nuxeo_url = "http://localhost:8080/nuxeo"
        self.auth = ("user", "pass")
        self.passthrough = ElasticsearchPassthrough(
            nuxeo_url=self.nuxeo_url, auth=self.auth
        )

    def test_initialization(self):
        """Test passthrough initialization."""
        expected_base_url = f"{self.nuxeo_url}/site/es"
        assert self.passthrough.base_url == expected_base_url
        assert self.passthrough.auth == self.auth

    def test_initialization_with_embedded_es(self):
        """Test initialization without nuxeo_url (uses environment or default)."""
        import os

        default_url = os.getenv(
            "elasticsearch.httpReadOnly.baseUrl", "http://localhost:9200"
        )
        passthrough = ElasticsearchPassthrough()
        assert passthrough.base_url == default_url
        assert passthrough.auth is None
    @patch("requests.post")
    def test_execute_query_forwards_body_verbatim(self, mock_post):
        """The body is forwarded as-is; ACLs are applied by Nuxeo server-side."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hits": {"hits": []}}
        mock_post.return_value = mock_response

        es_query = {"query": {"match_all": {}}, "size": 5}
        result = self.passthrough.execute_query(index="nuxeo", query=es_query)

        assert result is not None
        mock_post.assert_called_once()
        assert json.loads(mock_post.call_args[1]["data"]) == es_query

    @patch("requests.post")
    def test_execute_query_targets_the_requested_index(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hits": {"hits": []}}
        mock_post.return_value = mock_response

        self.passthrough.execute_query(index="audit", query={"size": 1})

        assert mock_post.call_args[0][0].endswith("/audit/_search")

    @patch("requests.post")
    def test_error_handling(self, mock_post):
        """A non-200 from the passthrough raises rather than returning empty."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            self.passthrough.execute_query(index="nuxeo", query={"size": 1})

        assert "Elasticsearch error" in str(exc_info.value)

    @patch("requests.post")
    def test_connection_error_handling(self, mock_post):
        import requests as requests_lib

        mock_post.side_effect = requests_lib.exceptions.ConnectionError("refused")

        with pytest.raises(Exception) as exc_info:
            self.passthrough.execute_query(index="nuxeo", query={"size": 1})

        assert "Failed to connect to Elasticsearch" in str(exc_info.value)
