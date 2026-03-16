"""Tests for Elasticsearch Search Request Filters."""

import pytest
import json
from nuxeo_mcp.search_filters import (
    SearchRequestFilter,
    DefaultSearchRequestFilter, 
    AuditRequestFilter,
    FilterChain
)


class TestSearchRequestFilter:
    """Test base SearchRequestFilter functionality."""
    
    def test_abstract_base_class(self):
        """Test that SearchRequestFilter is abstract."""
        with pytest.raises(TypeError):
            SearchRequestFilter()
    
    def test_subclass_must_implement_apply(self):
        """Test that subclasses must implement apply method."""
        class BadFilter(SearchRequestFilter):
            pass
        
        with pytest.raises(TypeError):
            BadFilter()


class TestDefaultSearchRequestFilter:
    """Test DefaultSearchRequestFilter for repository index."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.filter = DefaultSearchRequestFilter()
    
    def test_apply_acl_filter_to_simple_query(self):
        """Test applying ACL filter to a simple query."""
        query = {"match_all": {}}
        principal = "john.doe"
        groups = ["members", "Everyone"]
        
        filtered = self.filter.apply(query, principal, groups)
        
        assert "bool" in filtered
        assert "must" in filtered["bool"]
        assert "filter" in filtered["bool"]
        
        # Check ACL filter is applied
        acl_filter = filtered["bool"]["filter"][0]
        assert "terms" in acl_filter
        assert "ecm:acl" in acl_filter["terms"]
        assert set(acl_filter["terms"]["ecm:acl"]) == {"john.doe", "members", "Everyone"}
    
    def test_apply_acl_filter_to_bool_query(self):
        """Test applying ACL filter to existing bool query."""
        query = {
            "bool": {
                "must": [{"match": {"title": "report"}}],
                "filter": [{"term": {"type": "File"}}]
            }
        }
        principal = "alice"
        groups = ["power-users"]
        
        filtered = self.filter.apply(query, principal, groups)
        
        # Original query should be preserved
        assert filtered["bool"]["must"][0] == {"match": {"title": "report"}}
        assert {"term": {"type": "File"}} in filtered["bool"]["filter"]
        
        # ACL filter should be added
        acl_filter = None
        for f in filtered["bool"]["filter"]:
            if "terms" in f and "ecm:acl" in f["terms"]:
                acl_filter = f
                break
        
        assert acl_filter is not None
        assert set(acl_filter["terms"]["ecm:acl"]) == {"alice", "power-users"}
    
    def test_get_index_name(self):
        """Test getting the target index name."""
        assert self.filter.get_index_name() == "nuxeo"
    
    def test_validate_principal(self):
        """Test principal validation."""
        # Should accept any non-empty principal
        assert self.filter.validate_principal("user") == True
        assert self.filter.validate_principal("") == False
        assert self.filter.validate_principal(None) == False


class TestAuditRequestFilter:
    """Test AuditRequestFilter for audit index."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.filter = AuditRequestFilter()
    
    def test_only_admins_allowed(self):
        """Test that only administrators can query audit."""
        query = {"match_all": {}}
        
        # Admin should be allowed
        filtered = self.filter.apply(query, "Administrator", ["Administrators"])
        assert filtered is not None
        
        # Non-admin should be rejected
        with pytest.raises(PermissionError):
            self.filter.apply(query, "regular_user", ["members"])
    
    def test_admin_group_check(self):
        """Test checking for admin group membership."""
        query = {"match_all": {}}
        
        # User in Administrators group
        filtered = self.filter.apply(query, "john", ["Administrators", "members"])
        assert filtered is not None
        
        # User not in Administrators group
        with pytest.raises(PermissionError):
            self.filter.apply(query, "john", ["members", "power-users"])
    
    def test_get_index_name(self):
        """Test getting the audit index name."""
        assert self.filter.get_index_name() == "audit"
    
    def test_validate_principal(self):
        """Test principal validation for audit."""
        # Only administrators should validate
        assert self.filter.validate_principal("Administrator") == True
        assert self.filter.validate_principal("regular_user") == False


class TestFilterChain:
    """Test filter chaining functionality."""
    
    def test_chain_multiple_filters(self):
        """Test chaining multiple filters."""
        class Filter1(SearchRequestFilter):
            def apply(self, query, principal, groups):
                query = query.copy()
                query["filter1"] = True
                return query
            
            def get_index_name(self):
                return "test"
            
            def validate_principal(self, principal):
                return True
        
        class Filter2(SearchRequestFilter):
            def apply(self, query, principal, groups):
                query = query.copy()
                query["filter2"] = True
                return query
            
            def get_index_name(self):
                return "test"
            
            def validate_principal(self, principal):
                return True
        
        chain = FilterChain([Filter1(), Filter2()])
        query = {"match_all": {}}
        
        result = chain.apply(query, "user", [])
        
        assert result["filter1"] == True
        assert result["filter2"] == True
    
    def test_empty_chain(self):
        """Test empty filter chain."""
        chain = FilterChain([])
        query = {"match_all": {}}
        
        result = chain.apply(query, "user", [])
        assert result == query
    
    def test_chain_validation(self):
        """Test validation through chain."""
        class ValidFilter(SearchRequestFilter):
            def apply(self, query, principal, groups):
                return query
            
            def get_index_name(self):
                return "test"
            
            def validate_principal(self, principal):
                return principal == "valid_user"
        
        class InvalidFilter(SearchRequestFilter):
            def apply(self, query, principal, groups):
                return query
            
            def get_index_name(self):
                return "test"
            
            def validate_principal(self, principal):
                return False
        
        # Chain with valid filter
        chain1 = FilterChain([ValidFilter()])
        assert chain1.validate_principal("valid_user") == True
        assert chain1.validate_principal("invalid_user") == False
        
        # Chain with invalid filter
        chain2 = FilterChain([ValidFilter(), InvalidFilter()])
        assert chain2.validate_principal("valid_user") == False