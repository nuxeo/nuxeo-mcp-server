"""
Test suite for the Natural Language to NXQL Parser.
"""

import pytest
from datetime import datetime, timedelta
from nuxeo_mcp.nl_parser import NaturalLanguageParser, NXQLBuilder, ParsedQuery


class TestNaturalLanguageParser:
    """Test the NaturalLanguageParser class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = NaturalLanguageParser()
    
    def test_simple_document_type_detection(self):
        """Test detection of document types from natural language."""
        test_cases = [
            ("show me all invoices", "Invoice"),
            ("find files", "File"),
            ("list folders", "Folder"),
            ("get notes", "Note"),
            ("search documents", "Document"),
            ("find all PDFs", "File"),
            ("show images", "Picture"),
            ("list videos", "Video"),
            ("find workspaces", "Workspace"),
        ]
        
        for query, expected_type in test_cases:
            result = self.parser.parse(query)
            assert result.doc_type == expected_type, f"Failed for query: {query}"
    
    def test_time_based_queries(self):
        """Test parsing of time-based natural language queries."""
        test_cases = [
            ("documents created today", "dc:modified", ">=", "DATE 'TODAY'"),
            ("files from yesterday", "dc:modified", "BETWEEN", "DATE 'TODAY-1' AND DATE 'TODAY'"),
            ("documents from this week", "dc:modified", ">=", "NOW('-P7D')"),
            ("files from last week", "dc:modified", "BETWEEN", "NOW('-P14D') AND NOW('-P7D')"),
            ("documents from this month", "dc:modified", ">=", "NOW('-P1M')"),
            ("files from last month", "dc:modified", "BETWEEN", "NOW('-P2M') AND NOW('-P1M')"),
            ("documents from this year", "dc:modified", ">=", "NOW('-P1Y')"),
            ("files from last year", "dc:modified", "BETWEEN", "NOW('-P2Y') AND NOW('-P1Y')"),
            ("documents from last 5 days", "dc:modified", ">=", "NOW('-P5D')"),
            ("files from last 3 weeks", "dc:modified", ">=", "NOW('-P21D')"),
            ("documents from last 2 months", "dc:modified", ">=", "NOW('-P2M')"),
            ("files since 2024-01-15", "dc:modified", ">=", "DATE '2024-01-15'"),
            ("documents before 2024-12-31", "dc:modified", "<", "DATE '2024-12-31'"),
        ]
        
        for query, expected_field, expected_op, expected_value in test_cases:
            result = self.parser.parse(query)
            assert len(result.conditions) > 0, f"No conditions found for: {query}"
            time_condition = result.conditions[0]
            assert time_condition['field'] == expected_field
            assert time_condition['operator'] == expected_op
            assert time_condition['value'] == expected_value
    
    def test_user_based_queries(self):
        """Test parsing of user-related queries."""
        test_cases = [
            ("documents created by john", "dc:creator", "=", "'john'"),
            ("files from alice", "dc:creator", "=", "'alice'"),
            ("bob's documents", "dc:creator", "=", "'bob'"),
            ("documents authored by sarah", "dc:creator", "=", "'sarah'"),
            ("files modified by admin", "dc:lastContributor", "=", "'admin'"),
        ]
        
        for query, expected_field, expected_op, expected_value in test_cases:
            result = self.parser.parse(query)
            user_condition = None
            for cond in result.conditions:
                if cond['field'] in ['dc:creator', 'dc:lastContributor']:
                    user_condition = cond
                    break
            assert user_condition is not None, f"No user condition found for: {query}"
            assert user_condition['field'] == expected_field
            assert user_condition['operator'] == expected_op
            assert user_condition['value'] == expected_value
    
    def test_title_queries(self):
        """Test parsing of title-based queries."""
        test_cases = [
            ("document named 'Project Report'", "dc:title", "=", "'Project Report'"),
            ("files titled 'Budget 2024'", "dc:title", "=", "'Budget 2024'"),
            ("documents with title containing 'proposal'", "dc:title", "LIKE", "'%proposal%'"),
            ("files where title starts with 'Draft'", "dc:title", "LIKE", "'Draft%'"),
        ]
        
        for query, expected_field, expected_op, expected_value in test_cases:
            result = self.parser.parse(query)
            title_condition = None
            for cond in result.conditions:
                if cond['field'] == 'dc:title':
                    title_condition = cond
                    break
            assert title_condition is not None, f"No title condition found for: {query}"
            assert title_condition['operator'] == expected_op
            assert title_condition['value'] == expected_value
    
    def test_fulltext_search(self):
        """Test parsing of fulltext search queries."""
        test_cases = [
            ("documents containing 'budget'", "ecm:fulltext", "=", "'budget'"),
            ("files with content 'quarterly report'", "ecm:fulltext", "=", "'quarterly report'"),
            ("search for 'innovation strategy'", "ecm:fulltext", "=", "'innovation strategy'"),
        ]
        
        for query, expected_field, expected_op, expected_value in test_cases:
            result = self.parser.parse(query)
            fulltext_condition = None
            for cond in result.conditions:
                if cond['field'] == 'ecm:fulltext':
                    fulltext_condition = cond
                    break
            assert fulltext_condition is not None, f"No fulltext condition found for: {query}"
            assert fulltext_condition['operator'] == expected_op
            assert fulltext_condition['value'] == expected_value
    
    def test_path_queries(self):
        """Test parsing of path-based queries."""
        test_cases = [
            ("documents in folder '/workspaces/project'", "ecm:path", "STARTSWITH", "'/workspaces/project'"),
            ("files under /default-domain", "ecm:path", "STARTSWITH", "'/default-domain'"),
            ("documents in path 'archives'", "ecm:path", "STARTSWITH", "'/archives'"),
        ]
        
        for query, expected_field, expected_op, expected_value in test_cases:
            result = self.parser.parse(query)
            path_condition = None
            for cond in result.conditions:
                if cond['field'] == 'ecm:path':
                    path_condition = cond
                    break
            assert path_condition is not None, f"No path condition found for: {query}"
            assert path_condition['operator'] == expected_op
            assert path_condition['value'] == expected_value
    
    def test_state_queries(self):
        """Test parsing of lifecycle state queries."""
        test_cases = [
            ("draft documents", "ecm:currentLifeCycleState", "=", "'project'"),
            ("published files", "ecm:currentLifeCycleState", "=", "'approved'"),
            ("archived documents", "ecm:currentLifeCycleState", "=", "'obsolete'"),
            ("deleted files", "ecm:isTrashed", "=", "1"),
            ("trashed documents", "ecm:isTrashed", "=", "1"),
        ]
        
        for query, expected_field, expected_op, expected_value in test_cases:
            result = self.parser.parse(query)
            state_condition = None
            for cond in result.conditions:
                if cond['field'] in ['ecm:currentLifeCycleState', 'ecm:isTrashed']:
                    state_condition = cond
                    break
            assert state_condition is not None, f"No state condition found for: {query}"
            assert state_condition['field'] == expected_field
            assert state_condition['operator'] == expected_op
            assert str(state_condition['value']) == str(expected_value)
    
    def test_special_conditions(self):
        """Test parsing of special conditions."""
        test_cases = [
            ("active documents", "ecm:isTrashed", "=", "0"),
            ("not deleted files", "ecm:isTrashed", "=", "0"),
            ("latest version documents", "ecm:isLatestVersion", "=", "1"),
            ("documents that are versions", "ecm:isVersion", "=", "1"),
            ("documents not versions", "ecm:isVersion", "=", "0"),
            ("proxy documents", "ecm:isProxy", "=", "1"),
            ("documents not proxy", "ecm:isProxy", "=", "0"),
            ("checked in documents", "ecm:isCheckedIn", "=", "1"),
            ("checked out files", "ecm:isCheckedIn", "=", "0"),
        ]
        
        for query, expected_field, expected_op, expected_value in test_cases:
            result = self.parser.parse(query)
            special_condition = None
            for cond in result.conditions:
                if cond['field'] == expected_field:
                    special_condition = cond
                    break
            assert special_condition is not None, f"No special condition found for: {query}"
            assert special_condition['operator'] == expected_op
            assert str(special_condition['value']) == str(expected_value)
    
    def test_ordering(self):
        """Test parsing of ORDER BY clauses."""
        test_cases = [
            ("documents sorted by title", "dc:title", "ASC"),
            ("files order by name desc", "ecm:name", "DESC"),
            ("latest documents", "dc:modified", "DESC"),
            ("oldest files", "dc:modified", "ASC"),
            ("documents alphabetically", "dc:title", "ASC"),
            ("files by size", "file:content/length", "DESC"),
            ("smallest documents", "file:content/length", "ASC"),
        ]
        
        for query, expected_field, expected_direction in test_cases:
            result = self.parser.parse(query)
            assert result.order_by == expected_field, f"Wrong order field for: {query}"
            assert result.order_direction == expected_direction, f"Wrong order direction for: {query}"
    
    def test_limit(self):
        """Test parsing of LIMIT clauses."""
        test_cases = [
            ("first 10 documents", 10),
            ("top 5 files", 5),
            ("limit 20 documents", 20),
            ("get 15 results", 15),
            ("show 100 documents", 100),
        ]
        
        for query, expected_limit in test_cases:
            result = self.parser.parse(query)
            assert result.limit == expected_limit, f"Wrong limit for: {query}"
    
    def test_complex_queries(self):
        """Test parsing of complex multi-condition queries."""
        query = "invoices created by john from last week sorted by title limit 10"
        result = self.parser.parse(query)
        
        assert result.doc_type == "Invoice"
        assert result.limit == 10
        assert result.order_by == "dc:title"
        assert result.order_direction == "ASC"
        
        # Check for user condition
        has_user_condition = any(
            cond['field'] == 'dc:creator' and cond['value'] == "'john'"
            for cond in result.conditions
        )
        assert has_user_condition
        
        # Check for time condition
        has_time_condition = any(
            cond['field'] == 'dc:modified'
            for cond in result.conditions
        )
        assert has_time_condition


class TestNXQLBuilder:
    """Test the NXQLBuilder class."""
    
    def test_simple_query_building(self):
        """Test building simple NXQL queries."""
        parsed = ParsedQuery(
            intent="search",
            doc_type="Document",
            conditions=[],
            order_by=None,
            order_direction=None,
            limit=None
        )
        builder = NXQLBuilder(parsed)
        nxql = builder.build()
        assert nxql == "SELECT * FROM Document"
    
    def test_query_with_conditions(self):
        """Test building NXQL queries with WHERE conditions."""
        parsed = ParsedQuery(
            intent="search",
            doc_type="File",
            conditions=[
                {"field": "dc:creator", "operator": "=", "value": "'john'"},
                {"field": "ecm:isTrashed", "operator": "=", "value": "0"}
            ],
            order_by=None,
            order_direction=None,
            limit=None
        )
        builder = NXQLBuilder(parsed)
        nxql = builder.build()
        assert "SELECT * FROM File" in nxql
        assert "WHERE" in nxql
        assert "dc:creator = 'john'" in nxql
        assert "ecm:isTrashed = 0" in nxql
    
    def test_query_with_ordering(self):
        """Test building NXQL queries with ORDER BY."""
        parsed = ParsedQuery(
            intent="search",
            doc_type="Document",
            conditions=[],
            order_by="dc:modified",
            order_direction="DESC",
            limit=None
        )
        builder = NXQLBuilder(parsed)
        nxql = builder.build()
        assert "ORDER BY dc:modified DESC" in nxql
    
    def test_query_with_between_operator(self):
        """Test building NXQL queries with BETWEEN operator."""
        parsed = ParsedQuery(
            intent="search",
            doc_type="Document",
            conditions=[
                {"field": "dc:modified", "operator": "BETWEEN", "value": "DATE '2024-01-01' AND DATE '2024-12-31'"}
            ],
            order_by=None,
            order_direction=None,
            limit=None
        )
        builder = NXQLBuilder(parsed)
        nxql = builder.build()
        assert "WHERE dc:modified BETWEEN DATE '2024-01-01' AND DATE '2024-12-31'" in nxql
    
    def test_full_complex_query(self):
        """Test building a complex NXQL query with all components."""
        parsed = ParsedQuery(
            intent="search",
            doc_type="Invoice",
            conditions=[
                {"field": "dc:creator", "operator": "=", "value": "'alice'"},
                {"field": "dc:modified", "operator": ">=", "value": "NOW('-P7D')"},
                {"field": "ecm:isTrashed", "operator": "=", "value": "0"},
                {"field": "ecm:fulltext", "operator": "=", "value": "'payment'"}
            ],
            order_by="dc:created",
            order_direction="DESC",
            limit=None
        )
        builder = NXQLBuilder(parsed)
        nxql = builder.build()
        
        assert "SELECT * FROM Invoice" in nxql
        assert "WHERE" in nxql
        assert "dc:creator = 'alice'" in nxql
        assert "dc:modified >= NOW('-P7D')" in nxql
        assert "ecm:isTrashed = 0" in nxql
        assert "ecm:fulltext = 'payment'" in nxql
        assert "ORDER BY dc:created DESC" in nxql


class TestEndToEnd:
    """Test end-to-end natural language to NXQL conversion."""
    
    def test_common_use_cases(self):
        """Test common real-world query patterns."""
        parser = NaturalLanguageParser()
        
        test_cases = [
            (
                "find all PDFs created by john in the last month",
                ["File", "dc:creator = 'john'", "dc:modified >= NOW('-P1M')"]
            ),
            (
                "show me draft invoices from this week sorted by date",
                ["Invoice", "ecm:currentLifeCycleState = 'project'", "dc:modified >= NOW('-P7D')", "ORDER BY"]
            ),
            (
                "active documents containing budget not in trash",
                ["Document", "ecm:fulltext = 'budget'", "ecm:isTrashed = 0"]
            ),
            (
                "latest version of files under /workspaces",
                ["File", "ecm:path STARTSWITH '/workspaces'", "ecm:isLatestVersion = 1"]
            ),
            (
                "first 5 notes created today by admin",
                ["Note", "dc:modified >= DATE 'TODAY'", "dc:creator = 'admin'", "SELECT *"]
            ),
        ]
        
        for nl_query, expected_parts in test_cases:
            parsed = parser.parse(nl_query)
            builder = NXQLBuilder(parsed)
            nxql = builder.build()
            
            # Check that all expected parts are in the generated NXQL
            for part in expected_parts:
                assert part in nxql, f"Expected '{part}' in NXQL for query: {nl_query}\nGot: {nxql}"
    
    def test_explanation_generation(self):
        """Test that explanations are generated correctly."""
        parser = NaturalLanguageParser()
        
        query = "find invoices created by john from last week sorted by title"
        parsed = parser.parse(query)
        
        assert parsed.explanation is not None
        assert "invoice" in parsed.explanation.lower()
        assert "creator" in parsed.explanation.lower() or "john" in parsed.explanation.lower()
        assert "ordered by" in parsed.explanation.lower() or "sorted" in parsed.explanation.lower()