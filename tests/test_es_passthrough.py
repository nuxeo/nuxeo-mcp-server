"""Tests for the OpenSearch/Elasticsearch passthrough client.

Error bodies mirror what a Nuxeo LTS 2025 passthrough actually returns, as
observed against a live server.
"""

import json
from typing import Any, Dict, Optional
from unittest.mock import Mock, patch

import pytest
import requests as requests_lib

from nuxeo_mcp.es_passthrough import (
    MAX_ERROR_DETAIL,
    ElasticsearchPassthrough,
    PassthroughError,
)


def _response(
    status: int,
    body: Any = None,
    text: Optional[str] = None,
    content_type: str = "application/json",
) -> Mock:
    response = Mock()
    response.status_code = status
    response.headers = {"Content-Type": content_type}
    if body is not None:
        response.json.return_value = body
        response.text = json.dumps(body)
    else:
        response.json.side_effect = ValueError("not json")
        response.text = text or ""
    return response


def _nuxeo_exception(status: int, message: str) -> Dict[str, Any]:
    return {"entity-type": "exception", "status": status, "message": message}


class TestElasticsearchPassthrough:
    """Test passthrough request and error mapping."""

    def setup_method(self):
        """Set up test fixtures."""
        self.nuxeo_url = "http://localhost:8080/nuxeo"
        self.auth = ("user", "pass")
        self.passthrough = ElasticsearchPassthrough(
            nuxeo_url=self.nuxeo_url, auth=self.auth
        )

    def _fail(self, mock_post: Mock, index: str = "nuxeo") -> PassthroughError:
        with pytest.raises(PassthroughError) as exc_info:
            self.passthrough.execute_query(index=index, query={"size": 1})
        return exc_info.value

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
        mock_post.return_value = _response(200, {"hits": {"hits": []}})

        es_query = {"query": {"match_all": {}}, "size": 5}
        result = self.passthrough.execute_query(index="nuxeo", query=es_query)

        assert result == {"hits": {"hits": []}}
        assert json.loads(mock_post.call_args[1]["data"]) == es_query

    @patch("requests.post")
    def test_execute_query_targets_the_requested_index(self, mock_post):
        mock_post.return_value = _response(200, {"hits": {"hits": []}})

        self.passthrough.execute_query(index="audit", query={"size": 1})

        assert mock_post.call_args[0][0].endswith("/audit/_search")

    @patch("requests.post")
    def test_passthrough_disabled(self, mock_post):
        mock_post.return_value = _response(
            400,
            _nuxeo_exception(
                400,
                "java.lang.IllegalArgumentException: "
                "ElasticSearch passthrough is disabled",
            ),
        )

        error = self._fail(mock_post)

        assert error.unavailable
        assert "Query DSL search is disabled" in str(error)
        assert "nuxeo_search_documents" in str(error)
        assert "java.lang" not in str(error)

    @patch("requests.post")
    def test_audit_passthrough_disabled(self, mock_post):
        mock_post.return_value = _response(
            400,
            _nuxeo_exception(
                400,
                "java.lang.IllegalArgumentException: "
                "Audit ElasticSearch passthrough is disabled",
            ),
        )

        error = self._fail(mock_post, "audit")

        assert error.unavailable
        assert "Audit search is disabled" in str(error)

    @pytest.mark.parametrize(
        "message",
        [
            "java.lang.IllegalArgumentException: OpenSearch audit backend not configured",
            "java.lang.IllegalArgumentException: Audit OpenSearch Backend is not installed",
        ],
    )
    @patch("requests.post")
    def test_audit_backend_not_searchable(self, mock_post, message):
        mock_post.return_value = _response(400, _nuxeo_exception(400, message))

        error = self._fail(mock_post, "audit")

        assert error.unavailable
        assert "MongoDB or SQL" in str(error)

    @patch("requests.post")
    def test_audit_non_admin(self, mock_post):
        mock_post.return_value = _response(
            403,
            _nuxeo_exception(
                403,
                "java.lang.SecurityException: "
                "Only administrators can access audit indices",
            ),
        )

        error = self._fail(mock_post, "audit")

        assert error.unavailable
        assert "restricted to administrators" in str(error)

    @patch("requests.post")
    def test_passthrough_not_installed(self, mock_post):
        mock_post.return_value = _response(
            404,
            _nuxeo_exception(
                404, "jakarta.ws.rs.NotFoundException: HTTP 404 Not Found"
            ),
        )

        error = self._fail(mock_post)

        assert error.unavailable
        assert "not installed" in str(error)

    @patch("requests.post")
    def test_engine_error_inside_http_200(self, mock_post):
        """Nuxeo relays engine errors with HTTP 200; they must not read as hits."""
        mock_post.return_value = _response(
            200,
            {
                "error": {
                    "root_cause": [
                        {"type": "parsing_exception", "reason": "unknown query [bogus]"}
                    ],
                    "type": "parsing_exception",
                    "reason": "unknown query [bogus]",
                    "caused_by": {
                        "type": "named_object_not_found_exception",
                        "reason": "[1:19] unknown field [bogus]",
                    },
                },
                "status": 400,
            },
        )

        error = self._fail(mock_post)

        assert not error.unavailable
        assert error.status == 400
        assert "unknown query [bogus]" in str(error)
        assert "unknown field [bogus]" in str(error)
        assert "Fix the query" in str(error)

    @patch("requests.post")
    def test_invalid_json_payload(self, mock_post):
        mock_post.return_value = _response(
            400,
            _nuxeo_exception(400, "Unable to parse the payload as valid JSON: ..."),
        )

        error = self._fail(mock_post)

        assert not error.unavailable
        assert "Unable to parse the payload" in str(error)

    @pytest.mark.parametrize("status", [302, 401])
    @patch("requests.post")
    def test_bad_credentials(self, mock_post, status):
        """Nuxeo redirects to its login page; following it would yield HTML."""
        mock_post.return_value = _response(status, text="")

        error = self._fail(mock_post)

        assert mock_post.call_args[1]["allow_redirects"] is False
        assert "credentials" in str(error)

    @patch("requests.post")
    def test_non_json_success_is_not_a_connection_error(self, mock_post):
        mock_post.return_value = _response(
            200, text="<html>login</html>", content_type="text/html"
        )

        error = self._fail(mock_post)

        assert "non-JSON response" in str(error)
        assert "connect" not in str(error).lower()

    @patch("requests.post")
    def test_unparseable_error_body_is_truncated(self, mock_post):
        mock_post.return_value = _response(
            502, text="<html>" + "x" * 10_000 + "</html>", content_type="text/html"
        )

        error = self._fail(mock_post)

        assert "HTTP 502" in str(error)
        assert len(str(error)) < MAX_ERROR_DETAIL + 200

    @patch("requests.post")
    def test_connection_error(self, mock_post):
        mock_post.side_effect = requests_lib.exceptions.ConnectionError("refused")

        error = self._fail(mock_post)

        assert "Could not reach Nuxeo" in str(error)

    @patch("requests.post")
    def test_messages_do_not_name_elasticsearch_alone(self, mock_post):
        """The engine is usually OpenSearch; property names are the exception."""
        mock_post.return_value = _response(
            404, _nuxeo_exception(404, "HTTP 404 Not Found")
        )

        message = str(self._fail(mock_post))

        assert "Elasticsearch" not in message.replace("OpenSearch/Elasticsearch", "")
