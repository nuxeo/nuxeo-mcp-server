"""Tests for Elasticsearch Query Builder."""

import pytest
from datetime import datetime, timedelta
from nuxeo_mcp.es_query_builder import ElasticsearchQueryBuilder


class TestElasticsearchQueryBuilder:
    """Test Elasticsearch Query Builder functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.builder = ElasticsearchQueryBuilder()

    def test_match_query(self):
        """Test match query generation."""
        query = self.builder.match("title", "project report")
        expected = {
            "match": {
                "title": "project report"
            }
        }
        assert query == expected

    def test_term_query(self):
        """Test term query generation."""
        query = self.builder.term("dc:creator", "john.doe")
        expected = {
            "term": {
                "dc:creator": "john.doe"
            }
        }
        assert query == expected

    def test_terms_query(self):
        """Test terms query generation for multiple values."""
        query = self.builder.terms("ecm:primaryType", ["File", "Note", "Picture"])
        expected = {
            "terms": {
                "ecm:primaryType": ["File", "Note", "Picture"]
            }
        }
        assert query == expected

    def test_range_query(self):
        """Test range query generation."""
        query = self.builder.range("dc:created", gte="2024-01-01", lt="2024-02-01")
        expected = {
            "range": {
                "dc:created": {
                    "gte": "2024-01-01",
                    "lt": "2024-02-01"
                }
            }
        }
        assert query == expected

    def test_bool_query(self):
        """Test bool query generation."""
        must = [self.builder.match("title", "report")]
        filter = [self.builder.term("dc:creator", "john")]
        should = [self.builder.match("description", "quarterly")]
        must_not = [self.builder.term("ecm:currentLifeCycleState", "deleted")]
        
        query = self.builder.bool_query(
            must=must,
            filter=filter,
            should=should,
            must_not=must_not
        )
        
        expected = {
            "bool": {
                "must": [{"match": {"title": "report"}}],
                "filter": [{"term": {"dc:creator": "john"}}],
                "should": [{"match": {"description": "quarterly"}}],
                "must_not": [{"term": {"ecm:currentLifeCycleState": "deleted"}}]
            }
        }
        assert query == expected

    def test_wildcard_query(self):
        """Test wildcard query generation."""
        query = self.builder.wildcard("dc:title", "project*")
        expected = {
            "wildcard": {
                "dc:title": "project*"
            }
        }
        assert query == expected

    def test_prefix_query(self):
        """Test prefix query generation."""
        query = self.builder.prefix("ecm:path", "/default-domain/workspaces/")
        expected = {
            "prefix": {
                "ecm:path": "/default-domain/workspaces/"
            }
        }
        assert query == expected

    def test_exists_query(self):
        """Test exists query generation."""
        query = self.builder.exists("file:content")
        expected = {
            "exists": {
                "field": "file:content"
            }
        }
        assert query == expected

    def test_nested_bool_query(self):
        """Test nested bool query generation."""
        inner_bool = self.builder.bool_query(
            must=[self.builder.match("title", "report")]
        )
        query = self.builder.bool_query(
            must=[inner_bool],
            filter=[self.builder.term("dc:creator", "john")]
        )
        
        expected = {
            "bool": {
                "must": [
                    {
                        "bool": {
                            "must": [{"match": {"title": "report"}}]
                        }
                    }
                ],
                "filter": [{"term": {"dc:creator": "john"}}]
            }
        }
        assert query == expected

    def test_date_math_today(self):
        """Test date math for today."""
        start, end = self.builder.date_math_today()
        assert start == "now/d"
        assert end == "now/d+1d"

    def test_date_math_yesterday(self):
        """Test date math for yesterday."""
        start, end = self.builder.date_math_yesterday()
        assert start == "now-1d/d"
        assert end == "now/d"

    def test_date_math_this_week(self):
        """Test date math for this week."""
        start, end = self.builder.date_math_this_week()
        assert start == "now/w"
        assert end == "now/w+1w"

    def test_date_math_last_week(self):
        """Test date math for last week."""
        start, end = self.builder.date_math_last_week()
        assert start == "now-1w/w"
        assert end == "now/w"

    def test_date_math_this_month(self):
        """Test date math for this month."""
        start, end = self.builder.date_math_this_month()
        assert start == "now/M"
        assert end == "now/M+1M"

    def test_date_math_last_month(self):
        """Test date math for last month."""
        start, end = self.builder.date_math_last_month()
        assert start == "now-1M/M"
        assert end == "now/M"

    def test_date_math_last_n_days(self):
        """Test date math for last N days."""
        start = self.builder.date_math_last_n_days(7)
        assert start == "now-7d"

    def test_date_math_last_n_months(self):
        """Test date math for last N months."""
        start = self.builder.date_math_last_n_months(3)
        assert start == "now-3M"

    def test_apply_acl_filter(self):
        """Test applying ACL security filter."""
        base_query = self.builder.match("title", "report")
        user_principals = ["john.doe", "members", "Everyone"]
        
        filtered_query = self.builder.apply_acl_filter(base_query, user_principals)
        
        expected = {
            "bool": {
                "must": [{"match": {"title": "report"}}],
                "filter": [
                    {
                        "terms": {
                            "ecm:acl": ["john.doe", "members", "Everyone"]
                        }
                    }
                ]
            }
        }
        assert filtered_query == expected

    def test_apply_acl_filter_with_existing_bool(self):
        """Test applying ACL filter to existing bool query."""
        base_query = self.builder.bool_query(
            must=[self.builder.match("title", "report")],
            filter=[self.builder.term("dc:creator", "alice")]
        )
        user_principals = ["john.doe", "members"]
        
        filtered_query = self.builder.apply_acl_filter(base_query, user_principals)
        
        expected = {
            "bool": {
                "must": [{"match": {"title": "report"}}],
                "filter": [
                    {"term": {"dc:creator": "alice"}},
                    {"terms": {"ecm:acl": ["john.doe", "members"]}}
                ]
            }
        }
        assert filtered_query == expected

    def test_build_search_request(self):
        """Test building complete search request."""
        query = self.builder.match("title", "report")
        request = self.builder.build_search_request(
            query=query,
            size=10,
            from_=20,
            sort=[{"dc:modified": {"order": "desc"}}],
            source_includes=["dc:title", "dc:creator", "dc:modified"]
        )
        
        expected = {
            "query": {"match": {"title": "report"}},
            "size": 10,
            "from": 20,
            "sort": [{"dc:modified": {"order": "desc"}}],
            "_source": {
                "includes": ["dc:title", "dc:creator", "dc:modified"]
            }
        }
        assert request == expected

    def test_build_search_request_defaults(self):
        """Test building search request with defaults."""
        query = self.builder.match("title", "report")
        request = self.builder.build_search_request(query)
        
        expected = {
            "query": {"match": {"title": "report"}},
            "size": 20,
            "from": 0
        }
        assert request == expected

    def test_fulltext_query(self):
        """Test fulltext search query generation."""
        query = self.builder.fulltext_query("project management document")
        expected = {
            "simple_query_string": {
                "query": "project management document",
                "fields": ["ecm:fulltext", "ecm:fulltext.title^2"],
                "default_operator": "AND"
            }
        }
        assert query == expected

    def test_path_query(self):
        """Test path-based query generation."""
        query = self.builder.path_query("/default-domain/workspaces/project")
        expected = {
            "bool": {
                "should": [
                    {"term": {"ecm:path": "/default-domain/workspaces/project"}},
                    {"prefix": {"ecm:path": "/default-domain/workspaces/project/"}}
                ]
            }
        }
        assert query == expected