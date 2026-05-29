"""Elasticsearch Query Builder for Nuxeo MCP."""

from typing import Any, Dict, List, Optional, Union


class ElasticsearchQueryBuilder:
    """Build Elasticsearch DSL queries for Nuxeo."""

    def match(self, field: str, value: str) -> Dict[str, Any]:
        """Build a match query."""
        return {"match": {field: value}}

    def term(self, field: str, value: Union[str, int, bool]) -> Dict[str, Any]:
        """Build a term query for exact matching."""
        return {"term": {field: value}}

    def terms(self, field: str, values: List[Union[str, int]]) -> Dict[str, Any]:
        """Build a terms query for matching multiple values."""
        return {"terms": {field: values}}

    def range(
        self,
        field: str,
        gte: Optional[Union[str, int]] = None,
        gt: Optional[Union[str, int]] = None,
        lte: Optional[Union[str, int]] = None,
        lt: Optional[Union[str, int]] = None,
    ) -> Dict[str, Any]:
        """Build a range query."""
        range_clause = {}
        if gte is not None:
            range_clause["gte"] = gte
        if gt is not None:
            range_clause["gt"] = gt
        if lte is not None:
            range_clause["lte"] = lte
        if lt is not None:
            range_clause["lt"] = lt

        return {"range": {field: range_clause}}

    def bool_query(
        self,
        must: Optional[List[Dict[str, Any]]] = None,
        filter: Optional[List[Dict[str, Any]]] = None,
        should: Optional[List[Dict[str, Any]]] = None,
        must_not: Optional[List[Dict[str, Any]]] = None,
        minimum_should_match: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Build a bool query."""
        bool_clause = {}

        if must:
            bool_clause["must"] = must
        if filter:
            bool_clause["filter"] = filter
        if should:
            bool_clause["should"] = should
        if must_not:
            bool_clause["must_not"] = must_not
        if minimum_should_match is not None:
            bool_clause["minimum_should_match"] = minimum_should_match

        return {"bool": bool_clause}

    def wildcard(self, field: str, value: str) -> Dict[str, Any]:
        """Build a wildcard query."""
        return {"wildcard": {field: value}}

    def prefix(self, field: str, value: str) -> Dict[str, Any]:
        """Build a prefix query."""
        return {"prefix": {field: value}}

    def exists(self, field: str) -> Dict[str, Any]:
        """Build an exists query."""
        return {"exists": {"field": field}}

    def fulltext_query(
        self, text: str, fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Build a fulltext search query."""
        if fields is None:
            fields = ["all_field"]

        return {
            "simple_query_string": {
                "query": text,
                "fields": fields,
                "default_operator": "AND",
            }
        }

    def path_query(self, path: str) -> Dict[str, Any]:
        """Build a query for documents in a specific path."""
        return self.bool_query(
            should=[self.term("ecm:path", path), self.prefix("ecm:path", f"{path}/")]
        )

    # Date math helper methods
    def date_math_today(self) -> tuple[str, str]:
        """Get date math expressions for today."""
        return "now/d", "now/d+1d"

    def date_math_yesterday(self) -> tuple[str, str]:
        """Get date math expressions for yesterday."""
        return "now-1d/d", "now/d"

    def date_math_this_week(self) -> tuple[str, str]:
        """Get date math expressions for this week."""
        return "now/w", "now/w+1w"

    def date_math_last_week(self) -> tuple[str, str]:
        """Get date math expressions for last week."""
        return "now-1w/w", "now/w"

    def date_math_this_month(self) -> tuple[str, str]:
        """Get date math expressions for this month."""
        return "now/M", "now/M+1M"

    def date_math_last_month(self) -> tuple[str, str]:
        """Get date math expressions for last month."""
        return "now-1M/M", "now/M"

    def date_math_last_n_days(self, days: int) -> str:
        """Get date math expression for last N days."""
        return f"now-{days}d"

    def date_math_last_n_weeks(self, weeks: int) -> str:
        """Get date math expression for last N weeks."""
        return f"now-{weeks}w"

    def date_math_last_n_months(self, months: int) -> str:
        """Get date math expression for last N months."""
        return f"now-{months}M"

    def date_math_last_n_years(self, years: int) -> str:
        """Get date math expression for last N years."""
        return f"now-{years}y"

    def apply_acl_filter(
        self, query: Dict[str, Any], user_principals: List[str]
    ) -> Dict[str, Any]:
        """Apply ACL security filter to a query."""
        acl_filter = self.terms("ecm:acl", user_principals)

        # If query is already a bool query, add to its filter clause
        if "bool" in query:
            bool_query = query["bool"]
            if "filter" in bool_query:
                if isinstance(bool_query["filter"], list):
                    bool_query["filter"].append(acl_filter)
                else:
                    bool_query["filter"] = [bool_query["filter"], acl_filter]
            else:
                bool_query["filter"] = [acl_filter]
            return query
        else:
            # Wrap in bool query with filter
            return self.bool_query(must=[query], filter=[acl_filter])

    def build_search_request(
        self,
        query: Dict[str, Any],
        size: int = 20,
        from_: int = 0,
        sort: Optional[List[Dict[str, Any]]] = None,
        source_includes: Optional[List[str]] = None,
        source_excludes: Optional[List[str]] = None,
        highlight: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a complete search request."""
        request = {"query": query, "size": size, "from": from_}

        if sort:
            request["sort"] = sort

        if source_includes or source_excludes:
            source = {}
            if source_includes:
                source["includes"] = source_includes
            if source_excludes:
                source["excludes"] = source_excludes
            request["_source"] = source

        if highlight:
            request["highlight"] = highlight

        return request
