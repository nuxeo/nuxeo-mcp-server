"""Tests for Elasticsearch Passthrough Handler."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
from nuxeo_mcp.es_passthrough import ElasticsearchPassthrough


class TestElasticsearchPassthrough:
    """Test Elasticsearch Passthrough functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.nuxeo_url = "http://localhost:8080/nuxeo"
        self.auth = ("user", "pass")
        # ElasticsearchPassthrough now expects nuxeo_url instead of base_url
        self.passthrough = ElasticsearchPassthrough(nuxeo_url=self.nuxeo_url, auth=self.auth)
    
    def test_initialization(self):
        """Test passthrough initialization."""
        # The base_url is now constructed from nuxeo_url
        expected_base_url = f"{self.nuxeo_url}/site/es"
        assert self.passthrough.base_url == expected_base_url
        assert self.passthrough.filters is not None
        assert self.passthrough.auth == self.auth
    
    def test_initialization_with_embedded_es(self):
        """Test initialization without nuxeo_url (uses environment or default)."""
        # When no nuxeo_url is provided, it uses environment variable or default
        import os
        default_url = os.getenv("elasticsearch.httpReadOnly.baseUrl", "http://localhost:9200")
        passthrough = ElasticsearchPassthrough()
        assert passthrough.base_url == default_url
        assert passthrough.auth is None
    
    @patch('requests.post')
    def test_search_repository_with_nl_query(self, mock_post):
        """Test searching repository with natural language query."""
        # Mock ES response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hits": {
                "total": {"value": 1},
                "hits": [{
                    "_source": {
                        "uid": "doc-123",
                        "dc:title": "Test Document",
                        "dc:creator": "john",
                        "dc:modified": "2024-01-20T10:00:00Z"
                    }
                }]
            }
        }
        mock_post.return_value = mock_response
        
        result = self.passthrough.search_repository(
            query="documents created by john",
            principal="alice",
            groups=["members", "Everyone"]
        )
        
        assert result is not None
        assert "results" in result
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Test Document"
        
        # Verify ES was called with ACL filter
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        request_body = json.loads(call_args[1]["data"])
        assert "query" in request_body
        # Should have ACL filter applied
        assert "bool" in request_body["query"]
    
    @patch('requests.post')
    def test_search_audit_admin_only(self, mock_post):
        """Test audit search requires admin privileges."""
        # Non-admin should be rejected
        with pytest.raises(PermissionError):
            self.passthrough.search_audit(
                query="show all deletions",
                principal="regular_user",
                groups=["members"]
            )
        
        # Admin should be allowed
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hits": {
                "total": {"value": 0},
                "hits": []
            }
        }
        mock_post.return_value = mock_response
        
        result = self.passthrough.search_audit(
            query="show all deletions",
            principal="Administrator",
            groups=["Administrators"]
        )
        
        assert result is not None
        mock_post.assert_called_once()
    
    @patch('requests.post')
    def test_search_with_pagination(self, mock_post):
        """Test search with pagination parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hits": {
                "total": {"value": 100},
                "hits": []
            }
        }
        mock_post.return_value = mock_response
        
        result = self.passthrough.search_repository(
            query="all documents",
            principal="user",
            groups=["members"],
            limit=10,
            offset=20
        )
        
        # Check pagination was applied
        call_args = mock_post.call_args
        request_body = json.loads(call_args[1]["data"])
        assert request_body["size"] == 10
        assert request_body["from"] == 20
    
    @patch('requests.post')
    def test_execute_es_query_direct(self, mock_post):
        """Test executing direct Elasticsearch query."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"hits": {"hits": []}}
        mock_post.return_value = mock_response
        
        es_query = {
            "query": {"match_all": {}},
            "size": 5
        }
        
        result = self.passthrough.execute_query(
            index="nuxeo",
            query=es_query,
            principal="user",
            groups=["members"]
        )
        
        assert result is not None
        mock_post.assert_called_once()
        
        # Verify ACL filter was applied
        call_args = mock_post.call_args
        request_body = json.loads(call_args[1]["data"])
        assert "bool" in request_body["query"]
    
    @patch('requests.post')
    def test_error_handling(self, mock_post):
        """Test error handling for ES failures."""
        # Simulate ES error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        with pytest.raises(Exception) as exc_info:
            self.passthrough.search_repository(
                query="test",
                principal="user",
                groups=["members"]
            )
        
        assert "Elasticsearch error" in str(exc_info.value)
    
    @patch('requests.post')
    def test_connection_error_handling(self, mock_post):
        """Test handling of connection errors."""
        mock_post.side_effect = Exception("Connection refused")
        
        with pytest.raises(Exception) as exc_info:
            self.passthrough.search_repository(
                query="test",
                principal="user",
                groups=["members"]
            )
        
        assert "Connection" in str(exc_info.value)
    
    def test_format_repository_results(self):
        """Test formatting of repository search results."""
        es_response = {
            "hits": {
                "total": {"value": 2},
                "hits": [
                    {
                        "_source": {
                            "uid": "doc-1",
                            "dc:title": "Document 1",
                            "ecm:path": "/default/workspaces/doc1",
                            "ecm:primaryType": "File",
                            "dc:modified": "2024-01-20T10:00:00Z",
                            "dc:creator": "alice"
                        },
                        "highlight": {
                            "dc:title": ["<em>Document</em> 1"]
                        }
                    },
                    {
                        "_source": {
                            "uid": "doc-2",
                            "dc:title": "Document 2",
                            "ecm:path": "/default/workspaces/doc2",
                            "ecm:primaryType": "Note",
                            "dc:modified": "2024-01-21T11:00:00Z",
                            "dc:creator": "bob"
                        }
                    }
                ]
            },
            "took": 15
        }
        
        formatted = self.passthrough._format_repository_results(es_response, "test query")
        
        assert formatted["total"] == 2
        assert formatted["query_time_ms"] == 15
        assert formatted["translated_query"] == "test query"
        assert len(formatted["results"]) == 2
        
        # Check first result
        result1 = formatted["results"][0]
        assert result1["uid"] == "doc-1"
        assert result1["title"] == "Document 1"
        assert result1["path"] == "/default/workspaces/doc1"
        assert result1["type"] == "File"
        assert result1["creator"] == "alice"
        assert result1["highlights"] == ["<em>Document</em> 1"]
    
    def test_format_audit_results(self):
        """Test formatting of audit search results."""
        es_response = {
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_source": {
                            "id": "audit-1",
                            "eventId": "documentModified",
                            "eventDate": "2024-01-20T10:00:00Z",
                            "docUUID": "doc-123",
                            "docPath": "/default/workspaces/doc",
                            "principalName": "alice",
                            "category": "eventDocumentCategory",
                            "comment": "Document was modified"
                        }
                    }
                ]
            },
            "took": 10
        }
        
        formatted = self.passthrough._format_audit_results(es_response, "audit query")
        
        assert formatted["total"] == 1
        assert formatted["query_time_ms"] == 10
        assert len(formatted["results"]) == 1
        
        result = formatted["results"][0]
        assert result["id"] == "audit-1"
        assert result["eventId"] == "documentModified"
        assert result["principalName"] == "alice"
    
    def test_get_filter_for_index(self):
        """Test getting appropriate filter for index."""
        # Repository filter
        repo_filter = self.passthrough._get_filter_for_index("nuxeo")
        assert repo_filter.__class__.__name__ == "DefaultSearchRequestFilter"
        
        # Audit filter
        audit_filter = self.passthrough._get_filter_for_index("audit")
        assert audit_filter.__class__.__name__ == "AuditRequestFilter"
        
        # Unknown index should return default
        default_filter = self.passthrough._get_filter_for_index("unknown")
        assert default_filter.__class__.__name__ == "DefaultSearchRequestFilter"