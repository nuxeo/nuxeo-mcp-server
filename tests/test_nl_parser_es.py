"""Tests for Natural Language Parser Elasticsearch extension."""

import pytest
from nuxeo_mcp.nl_parser import NaturalLanguageParser


class TestNaturalLanguageParserElasticsearch:
    """Test Natural Language Parser Elasticsearch functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = NaturalLanguageParser()

    def test_parse_to_elasticsearch_simple(self):
        """Test parsing simple query to Elasticsearch DSL."""
        query = "find documents created today"
        result = self.parser.parse_to_elasticsearch(query)
        
        assert result is not None
        assert "query" in result
        
        # Should have a time condition for today - either as a direct range query or in a bool
        query_str = str(result["query"])
        assert "range" in query_str or "dc:modified" in query_str

    def test_parse_with_user_condition(self):
        """Test parsing query with user condition."""
        query = "documents created by John"
        result = self.parser.parse_to_elasticsearch(query)
        
        assert result is not None
        assert "query" in result
        # Should have term query for creator
        query_str = str(result)
        assert "dc:creator" in query_str or "dc:contributors" in query_str

    def test_parse_with_fulltext_search(self):
        """Test parsing fulltext search query."""
        query = "search for project management reports"
        result = self.parser.parse_to_elasticsearch(query)
        
        assert result is not None
        assert "query" in result
        # Should have fulltext query
        query_str = str(result)
        assert "simple_query_string" in query_str or "match" in query_str

    def test_parse_with_path_condition(self):
        """Test parsing query with path condition."""
        query = "files in /workspaces/project"
        result = self.parser.parse_to_elasticsearch(query)
        
        assert result is not None
        assert "query" in result
        # Should have path query
        query_str = str(result)
        assert "ecm:path" in query_str

    def test_parse_with_type_condition(self):
        """Test parsing query with document type."""
        query = "find all PDFs"
        result = self.parser.parse_to_elasticsearch(query)
        
        assert result is not None
        assert "query" in result
        # Should have type query
        query_str = str(result)
        assert "File" in query_str or "ecm:primaryType" in query_str

    def test_parse_with_state_condition(self):
        """Test parsing query with lifecycle state."""
        query = "show deleted documents"
        result = self.parser.parse_to_elasticsearch(query)
        
        assert result is not None
        assert "query" in result
        # Should have state query - deleted documents use ecm:isTrashed
        query_str = str(result)
        assert "ecm:isTrashed" in query_str or "ecm:currentLifeCycleState" in query_str

    def test_parse_with_time_range(self):
        """Test parsing query with time range."""
        query = "documents modified in the last week"
        result = self.parser.parse_to_elasticsearch(query)
        
        assert result is not None
        assert "query" in result
        # Should have range query
        query_str = str(result)
        assert "range" in query_str or "dc:modified" in query_str

    def test_parse_with_sorting(self):
        """Test parsing query with sorting."""
        query = "recent documents sorted by creation date"
        result = self.parser.parse_to_elasticsearch(query, include_sort=True)
        
        assert result is not None
        assert "query" in result
        assert "sort" in result
        assert isinstance(result["sort"], list)

    def test_parse_with_limit(self):
        """Test parsing query with result limit."""
        query = "show me 5 recent documents"
        result = self.parser.parse_to_elasticsearch(query, include_pagination=True)
        
        assert result is not None
        assert "query" in result
        assert "size" in result
        assert result["size"] == 5

    def test_parse_complex_query(self):
        """Test parsing complex query with multiple conditions."""
        query = "find PDFs created by John in the last month in /workspaces"
        result = self.parser.parse_to_elasticsearch(query)
        
        assert result is not None
        assert "query" in result
        assert "bool" in result["query"]
        
        # Should have multiple conditions
        query_str = str(result)
        assert "ecm:path" in query_str
        assert "dc:creator" in query_str or "dc:contributors" in query_str
        assert "range" in query_str

    def test_parse_audit_query(self):
        """Test parsing audit-specific query."""
        query = "show deletions by admin yesterday"
        result = self.parser.parse_to_elasticsearch(query, index="audit")
        
        assert result is not None
        assert "query" in result
        # Should have audit-specific fields
        query_str = str(result)
        assert "eventId" in query_str or "principalName" in query_str or "eventDate" in query_str

    def test_parse_with_highlighting(self):
        """Test parsing query with highlighting enabled."""
        query = "search for annual reports"
        result = self.parser.parse_to_elasticsearch(query, include_highlight=True)
        
        assert result is not None
        assert "query" in result
        assert "highlight" in result
        assert "fields" in result["highlight"]

    def test_detect_elasticsearch_intent(self):
        """Test detecting Elasticsearch-specific intent."""
        # Repository search intents
        assert self.parser.detect_search_intent("search for documents") == "repository"
        assert self.parser.detect_search_intent("find files") == "repository"
        assert self.parser.detect_search_intent("show me PDFs") == "repository"
        
        # Audit search intents
        assert self.parser.detect_search_intent("audit log for deletions") == "audit"
        assert self.parser.detect_search_intent("show audit events") == "audit"
        assert self.parser.detect_search_intent("what did admin delete") == "audit"

    def test_build_elasticsearch_query_empty(self):
        """Test building Elasticsearch query with no conditions."""
        parsed = self.parser.parse("all documents")
        es_query = self.parser.build_elasticsearch_query(parsed)
        
        assert es_query is not None
        assert "match_all" in str(es_query)

    def test_build_elasticsearch_query_with_conditions(self):
        """Test building Elasticsearch query with conditions."""
        parsed = self.parser.parse("PDFs created today by John")
        es_query = self.parser.build_elasticsearch_query(parsed)
        
        assert es_query is not None
        assert "bool" in es_query
        bool_query = es_query["bool"]
        assert "must" in bool_query or "filter" in bool_query

    def test_parse_to_elasticsearch_with_acl(self):
        """Test parsing with ACL filter application."""
        query = "my documents"
        user_principals = ["john.doe", "members", "Everyone"]
        result = self.parser.parse_to_elasticsearch(
            query, 
            apply_acl=True,
            user_principals=user_principals
        )
        
        assert result is not None
        assert "query" in result
        # Should have ACL filter
        query_str = str(result)
        assert "ecm:acl" in query_str

    def test_parse_special_my_documents(self):
        """Test parsing 'my documents' special case."""
        query = "my recent documents"
        result = self.parser.parse_to_elasticsearch(query, user_principal="john.doe")
        
        assert result is not None
        assert "query" in result
        # Should filter by user
        query_str = str(result)
        assert "john.doe" in query_str

    def test_parse_with_source_filtering(self):
        """Test parsing with source field filtering."""
        query = "find documents"
        result = self.parser.parse_to_elasticsearch(
            query,
            source_includes=["dc:title", "dc:creator", "dc:modified"]
        )
        
        assert result is not None
        assert "_source" in result
        assert "includes" in result["_source"]
        assert "dc:title" in result["_source"]["includes"]