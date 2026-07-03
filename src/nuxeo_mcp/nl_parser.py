"""
Natural Language to NXQL Parser

This module provides functionality to parse natural language queries and convert them
to NXQL (Nuxeo Query Language) syntax. It leverages the NXQL guide documentation
to understand query patterns and syntax.

Note: Since Nuxeo uses MongoDB (DBS), aggregates are not supported in NXQL.
"""

import os
import re
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class ParsedQuery:
    """Represents a parsed natural language query"""

    intent: str  # search, count
    doc_type: str  # Document type to search
    conditions: List[Dict[str, Any]]  # List of WHERE conditions
    order_by: Optional[str] = None
    order_direction: Optional[str] = None
    limit: Optional[int] = None
    explanation: Optional[str] = None


class NaturalLanguageParser:
    """Parses natural language queries into structured components"""

    def __init__(self):
        self.doc_type_patterns = {
            r"\b(invoice|invoices)\b": "Invoice",
            r"\b(file|files)\b": "File",
            r"\b(folder|folders|directory|directories)\b": "Folder",
            r"\b(note|notes)\b": "Note",
            r"\b(document|documents|doc|docs)\b": "Document",
            r"\b(workspace|workspaces)\b": "Workspace",
            r"\b(pdf|pdfs)\b": "File",  # PDFs are typically Files
            r"\b(image|images|picture|pictures|photo|photos)\b": "Picture",
            r"\b(video|videos)\b": "Video",
            r"\b(audio)\b": "Audio",
        }

        self.time_patterns = {
            # "in the last X" patterns should come first to match before "last X"
            r"\b(?:in|within)\s+(?:the\s+)?last\s+month\b": self._in_last_month,
            r"\b(?:in|within)\s+(?:the\s+)?last\s+year\b": self._in_last_year,
            r"\b(?:in|within)\s+(?:the\s+)?last\s+week\b": self._in_last_week,
            # Relative time patterns
            r"\b(today)\b": self._today,
            r"\b(yesterday)\b": self._yesterday,
            r"\b(this week)\b": self._this_week,
            r"\b(last week)\b": self._last_week,
            r"\b(this month)\b": self._this_month,
            r"\b(last month)\b": self._last_month,
            r"\b(this year)\b": self._this_year,
            r"\b(last year)\b": self._last_year,
            r"\b(last|past) (\d+) (day|days)\b": self._last_n_days,
            r"\b(last|past) (\d+) (week|weeks)\b": self._last_n_weeks,
            r"\b(last|past) (\d+) (month|months)\b": self._last_n_months,
            r"\b(last|past) (\d+) (year|years)\b": self._last_n_years,
            r"\b(since|after) (\d{4}-\d{2}-\d{2})\b": self._since_date,
            r"\b(before) (\d{4}-\d{2}-\d{2})\b": self._before_date,
            r"\b(between) (\d{4}-\d{2}-\d{2}) and (\d{4}-\d{2}-\d{2})\b": self._between_dates,
        }

        self.field_mappings = {
            "title": "dc:title",
            "name": "ecm:name",
            "description": "dc:description",
            "creator": "dc:creator",
            "created by": "dc:creator",
            "author": "dc:creator",
            "modified": "dc:modified",
            "created": "dc:created",
            "updated": "dc:modified",
            "subject": "dc:subjects",
            "subjects": "dc:subjects",
            "tag": "ecm:tag",
            "tags": "ecm:tag",
            "type": "ecm:primaryType",
            "state": "ecm:currentLifeCycleState",
            "lifecycle": "ecm:currentLifeCycleState",
            "path": "ecm:path",
            "in folder": "ecm:path",
            "under": "ecm:path",
            "size": "file:content/length",
            "file size": "file:content/length",
            "filename": "file:content/name",
            "file name": "file:content/name",
        }

        self.state_mappings = {
            "draft": "project",
            "published": "approved",
            "archived": "obsolete",
            "deleted": "deleted",
            "trashed": "deleted",
            "locked": "locked",
        }

    def parse(self, query: str) -> ParsedQuery:
        """Parse a natural language query into structured components"""
        query_lower = query.lower()

        # Detect intent (MongoDB doesn't support aggregates)
        intent = self._detect_intent(query_lower)

        # Extract document type
        doc_type = self._extract_doc_type(query_lower)

        # Extract conditions
        conditions = self._extract_conditions(query, query_lower)

        # Extract ordering
        order_by, order_direction = self._extract_ordering(query_lower)

        # Extract limit
        limit = self._extract_limit(query_lower)

        # Generate explanation
        explanation = self._generate_explanation(
            intent, doc_type, conditions, order_by, limit
        )

        return ParsedQuery(
            intent=intent,
            doc_type=doc_type,
            conditions=conditions,
            order_by=order_by,
            order_direction=order_direction,
            limit=limit,
            explanation=explanation,
        )

    def _detect_intent(self, query: str) -> str:
        """Detect the intent of the query"""
        # Since MongoDB doesn't support aggregates, we only support search and count
        if any(word in query for word in ["count", "how many", "number of"]):
            # Count is not directly supported in MongoDB NXQL, but we can indicate the intent
            return "search"  # Will need to count results client-side
        else:
            return "search"

    def _extract_doc_type(self, query: str) -> str:
        """Extract document type from query"""
        for pattern, doc_type in self.doc_type_patterns.items():
            if re.search(pattern, query, re.IGNORECASE):
                return doc_type
        return "Document"  # Default to Document

    def _extract_conditions(
        self, original_query: str, query_lower: str
    ) -> List[Dict[str, Any]]:
        """Extract WHERE conditions from the query"""
        conditions = []

        # Extract time conditions
        time_condition = self._extract_time_condition(query_lower)
        if time_condition:
            conditions.append(time_condition)

        # Extract user conditions
        user_condition = self._extract_user_condition(original_query, query_lower)
        if user_condition:
            conditions.append(user_condition)

        # Extract title/name conditions
        title_condition = self._extract_title_condition(original_query, query_lower)
        if title_condition:
            conditions.append(title_condition)

        # Extract fulltext search
        fulltext_condition = self._extract_fulltext_condition(
            original_query, query_lower
        )
        if fulltext_condition:
            conditions.append(fulltext_condition)

        # Extract path conditions
        path_condition = self._extract_path_condition(original_query, query_lower)
        if path_condition:
            conditions.append(path_condition)

        # Extract state conditions
        state_condition = self._extract_state_condition(query_lower)
        if state_condition:
            conditions.append(state_condition)

        # Extract special conditions (trash, versions, etc.)
        special_conditions = self._extract_special_conditions(query_lower)
        conditions.extend(special_conditions)
        
        # Fallback: If no conditions were found and the query doesn't just specify a document type,
        # treat it as a fulltext search
        if not conditions and original_query:
            # Check if the query is just a document type keyword
            doc_type_keywords = [
                "documents", "files", "folders", "pictures", "images", "videos", 
                "notes", "workspaces", "pdfs", "all"
            ]
            
            # Clean the query for comparison
            clean_query = original_query.strip().lower()
            
            # If it's not just a document type keyword, treat it as a search term
            if clean_query not in doc_type_keywords and not clean_query.startswith("all "):
                # Remove common prefixes that might be in the query
                search_term = original_query
                for prefix in ["find", "search", "get", "show", "list"]:
                    if search_term.lower().startswith(prefix + " "):
                        search_term = search_term[len(prefix)+1:].strip()
                        break
                
                # Add fulltext search condition for the remaining text
                if search_term and search_term not in doc_type_keywords:
                    conditions.append({
                        "field": "ecm:fulltext",
                        "operator": "=",
                        "value": f"'{search_term}'"
                    })

        return conditions

    def _extract_time_condition(self, query: str) -> Optional[Dict[str, Any]]:
        """Extract time-based conditions"""
        for pattern, handler in self.time_patterns.items():
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return handler(match)
        return None

    def _extract_user_condition(
        self, original_query: str, query_lower: str
    ) -> Optional[Dict[str, Any]]:
        """Extract user-based conditions"""
        # Skip if the word after 'from' is a time-related keyword
        time_keywords = ["last", "this", "today", "yesterday", "the"]

        patterns = [
            (r'(?:created by|by user|authored by)\s+["\']?(\w+)["\']?', "dc:creator"),
            (r'(?:modified by|updated by)\s+["\']?(\w+)["\']?', "dc:lastContributor"),
            (r"(\w+)'s\s+(?:documents?|files?)", "dc:creator"),
            (r'\bby\s+["\']?(\w+)["\']?', "dc:creator"),  # Simple "by USER" pattern
        ]

        for pattern, field in patterns:
            match = re.search(
                pattern,
                query_lower if field == "dc:creator" else original_query,
                re.IGNORECASE,
            )
            if match:
                username = re.search(pattern, original_query, re.IGNORECASE).group(1)
                # Don't treat time keywords as usernames
                if username.lower() not in time_keywords:
                    return {"field": field, "operator": "=", "value": f"'{username}'"}

        # Special handling for 'from' pattern - only if not followed by time keyword
        from_pattern = r'from\s+["\']?(\w+)["\']?'
        match = re.search(from_pattern, query_lower, re.IGNORECASE)
        if match:
            username = re.search(from_pattern, original_query, re.IGNORECASE).group(1)
            if username.lower() not in time_keywords:
                return {
                    "field": "dc:creator",
                    "operator": "=",
                    "value": f"'{username}'",
                }

        return None

    def _extract_title_condition(
        self, original_query: str, query_lower: str
    ) -> Optional[Dict[str, Any]]:
        """Extract title/name conditions"""
        patterns = [
            (r'(?:named|called|titled|with title)\s+["\']([^"\']+)["\']', "="),
            (r'(?:with title containing|title contains?|name contains?)\s+["\']([^"\']+)["\']', "LIKE"),
            (r'(?:title starts? with|name starts? with)\s+["\']([^"\']+)["\']', "LIKE"),
        ]

        for pattern, operator in patterns:
            match = re.search(pattern, original_query, re.IGNORECASE)
            if match:
                title = match.group(1)
                if operator == "LIKE":
                    if "starts with" in query_lower:
                        value = f"'{title}%'"
                    else:
                        value = f"'%{title}%'"
                else:
                    value = f"'{title}'"

                return {"field": "dc:title", "operator": operator, "value": value}
        return None

    def _extract_fulltext_condition(
        self, original_query: str, query_lower: str
    ) -> Optional[Dict[str, Any]]:
        """Extract fulltext search conditions"""
        # Skip if this is a title/name query
        if re.search(r'\b(?:title|name)\s+(?:containing|contains?|starts?)\b', query_lower):
            return None
            
        patterns = [
            r'(?:containing|with content|with text|search for)\s+["\']([^"\']+)["\']',
            r"(?:containing|with content|with text|search for)\s+(\w+(?:\s+\w+)*?)(?:\s+(?:and|or|from|by|created|modified|in|under|not)|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, original_query, re.IGNORECASE)
            if match:
                keywords = match.group(1).strip()
                # Don't create fulltext condition if keywords are time-related or user-related
                skip_words = [
                    "today",
                    "yesterday",
                    "week",
                    "month",
                    "year",
                    "created",
                    "modified",
                    "by",
                ]
                if not any(word in keywords.lower() for word in skip_words):
                    return {
                        "field": "ecm:fulltext",
                        "operator": "=",
                        "value": f"'{keywords}'",
                    }
        return None

    def _extract_path_condition(
        self, original_query: str, query_lower: str
    ) -> Optional[Dict[str, Any]]:
        """Extract path conditions"""
        patterns = [
            r'(?:in folder|under|in path|in)\s+["\']([^"\']+)["\']',
            r"(?:in folder|under|in path|in)\s+(/[\w\-/]+)",
            r'(?:from|within)\s+["\']([^"\']+)["\']',
            r"(?:from|within)\s+(/[\w\-/]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, original_query, re.IGNORECASE)
            if match:
                path = match.group(1)
                if not path.startswith("/"):
                    path = "/" + path
                return {
                    "field": "ecm:path",
                    "operator": "STARTSWITH",
                    "value": f"'{path}'",
                }
        return None

    def _extract_state_condition(self, query: str) -> Optional[Dict[str, Any]]:
        """Extract lifecycle state conditions"""
        # Check for "not deleted" or "not trashed" first to avoid conflicts
        if "not deleted" in query or "not trashed" in query:
            # This will be handled by _extract_special_conditions
            return None
            
        for state_keyword, state_value in self.state_mappings.items():
            if state_keyword in query:
                if state_keyword in ["deleted", "trashed"]:
                    return {"field": "ecm:isTrashed", "operator": "=", "value": "1"}
                else:
                    return {
                        "field": "ecm:currentLifeCycleState",
                        "operator": "=",
                        "value": f"'{state_value}'",
                    }
        return None

    def _extract_special_conditions(self, query: str) -> List[Dict[str, Any]]:
        """Extract special conditions like versions, proxies, etc."""
        conditions = []

        # Not in trash (when looking for active documents)
        if "not deleted" in query or "not trashed" in query or "active" in query:
            conditions.append({"field": "ecm:isTrashed", "operator": "=", "value": "0"})

        # Versions
        if "version" in query:
            if "latest version" in query:
                conditions.append(
                    {"field": "ecm:isLatestVersion", "operator": "=", "value": "1"}
                )
            elif "not version" in query or "no version" in query:
                conditions.append(
                    {"field": "ecm:isVersion", "operator": "=", "value": "0"}
                )
            else:
                conditions.append(
                    {"field": "ecm:isVersion", "operator": "=", "value": "1"}
                )

        # Proxies
        if "proxy" in query or "proxies" in query:
            if "not proxy" in query or "no proxy" in query:
                conditions.append(
                    {"field": "ecm:isProxy", "operator": "=", "value": "0"}
                )
            else:
                conditions.append(
                    {"field": "ecm:isProxy", "operator": "=", "value": "1"}
                )

        # Checked in/out
        if "checked in" in query:
            conditions.append(
                {"field": "ecm:isCheckedIn", "operator": "=", "value": "1"}
            )
        elif "checked out" in query:
            conditions.append(
                {"field": "ecm:isCheckedIn", "operator": "=", "value": "0"}
            )

        return conditions

    def _extract_ordering(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract ORDER BY clause"""
        order_patterns = [
            (
                r"(?:order by|sort by|sorted by)\s+(\w+)(?:\s+(asc|desc|ascending|descending))?",
                None,
            ),
            (r"(?:latest|newest|most recent)", ("dc:modified", "DESC")),
            (r"(?:oldest|earliest)", ("dc:modified", "ASC")),
            (r"(?:alphabetical|alphabetically)", ("dc:title", "ASC")),
            (r"(?:by name)", ("ecm:name", "ASC")),
            (r"(?:by size|largest)", ("file:content/length", "DESC")),
            (r"(?:smallest)", ("file:content/length", "ASC")),
        ]

        for pattern, default_order in order_patterns:
            if default_order:
                if re.search(pattern, query, re.IGNORECASE):
                    return default_order
            else:
                match = re.search(pattern, query, re.IGNORECASE)
                if match:
                    field = match.group(1).lower()
                    direction = (
                        match.group(2).upper()
                        if len(match.groups()) > 1 and match.group(2)
                        else "ASC"
                    )

                    # Map field names to NXQL fields
                    field_map = {
                        "title": "dc:title",
                        "name": "ecm:name",
                        "created": "dc:created",
                        "modified": "dc:modified",
                        "size": "file:content/length",
                        "path": "ecm:path",
                    }

                    nxql_field = field_map.get(field, f"dc:{field}")

                    if "desc" in direction.lower():
                        direction = "DESC"
                    else:
                        direction = "ASC"

                    return (nxql_field, direction)

        return (None, None)

    def _extract_limit(self, query: str) -> Optional[int]:
        """Extract LIMIT clause"""
        patterns = [
            r"(?:first|top|limit)\s+(\d+)",
            r"(\d+)\s+(?:results?|documents?|files?|items?)",
            r"(\d+)\s+(?:recent|latest|newest|oldest)",  # Handle "5 recent documents"
            r"show\s+(?:me\s+)?(\d+)",  # Handle "show me 5 ..."
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return None

    def _generate_explanation(
        self,
        intent: str,
        doc_type: str,
        conditions: List[Dict],
        order_by: Optional[str],
        limit: Optional[int],
    ) -> str:
        """Generate a human-readable explanation of the parsed query"""
        parts = []

        parts.append(f"Searching for {doc_type.lower()}s")

        if conditions:
            cond_strs = []
            for cond in conditions:
                field_name = self._humanize_field(cond["field"])
                value_str = cond["value"].strip('"').strip("'").strip("%")
                if cond["operator"] == "=":
                    cond_strs.append(f"{field_name} is {value_str}")
                elif cond["operator"] == "LIKE":
                    cond_strs.append(f"{field_name} contains {value_str}")
                elif cond["operator"] == "STARTSWITH":
                    cond_strs.append(f"under path {value_str}")
                elif cond["operator"] in [">", ">=", "<", "<="]:
                    cond_strs.append(f"{field_name} {cond['operator']} {value_str}")
                else:
                    cond_strs.append(f"{field_name} {cond['operator']} {value_str}")

            if cond_strs:
                parts.append("where " + " and ".join(cond_strs))

        if order_by:
            parts.append(f"ordered by {self._humanize_field(order_by)}")

        if limit:
            parts.append(f"limited to {limit} results")

        return " ".join(parts)

    def _humanize_field(self, field: str) -> str:
        """Convert NXQL field name to human-readable form"""
        field_names = {
            "dc:title": "title",
            "dc:description": "description",
            "dc:creator": "creator",
            "dc:created": "creation date",
            "dc:modified": "modification date",
            "dc:subjects": "subjects",
            "ecm:name": "name",
            "ecm:path": "path",
            "ecm:primaryType": "type",
            "ecm:currentLifeCycleState": "state",
            "ecm:fulltext": "content",
            "ecm:isTrashed": "trash status",
            "ecm:isVersion": "version status",
            "ecm:tag": "tags",
            "file:content/length": "file size",
            "file:content/name": "file name",
        }
        return field_names.get(field, field)

    # Time handler methods
    def _today(self, match) -> Dict[str, Any]:
        return {"field": "dc:modified", "operator": ">=", "value": "DATE 'TODAY'"}

    def _yesterday(self, match) -> Dict[str, Any]:
        return {
            "field": "dc:modified",
            "operator": "BETWEEN",
            "value": "DATE 'TODAY-1' AND DATE 'TODAY'",
        }

    def _this_week(self, match) -> Dict[str, Any]:
        return {"field": "dc:modified", "operator": ">=", "value": "NOW('-P7D')"}

    def _last_week(self, match) -> Dict[str, Any]:
        return {
            "field": "dc:modified",
            "operator": "BETWEEN",
            "value": "NOW('-P14D') AND NOW('-P7D')",
        }

    def _this_month(self, match) -> Dict[str, Any]:
        return {"field": "dc:modified", "operator": ">=", "value": "NOW('-P1M')"}

    def _last_month(self, match) -> Dict[str, Any]:
        return {
            "field": "dc:modified",
            "operator": "BETWEEN",
            "value": "NOW('-P2M') AND NOW('-P1M')",
        }

    def _this_year(self, match) -> Dict[str, Any]:
        return {"field": "dc:modified", "operator": ">=", "value": "NOW('-P1Y')"}

    def _last_year(self, match) -> Dict[str, Any]:
        return {
            "field": "dc:modified",
            "operator": "BETWEEN",
            "value": "NOW('-P2Y') AND NOW('-P1Y')",
        }

    def _in_last_month(self, match) -> Dict[str, Any]:
        """Handle 'in the last month' - documents from the last month up to now"""
        return {"field": "dc:modified", "operator": ">=", "value": "NOW('-P1M')"}

    def _in_last_year(self, match) -> Dict[str, Any]:
        """Handle 'in the last year' - documents from the last year up to now"""
        return {"field": "dc:modified", "operator": ">=", "value": "NOW('-P1Y')"}

    def _in_last_week(self, match) -> Dict[str, Any]:
        """Handle 'in the last week' - documents from the last week up to now"""
        return {"field": "dc:modified", "operator": ">=", "value": "NOW('-P7D')"}

    def _last_n_days(self, match) -> Dict[str, Any]:
        n = match.group(2)
        return {"field": "dc:modified", "operator": ">=", "value": f"NOW('-P{n}D')"}

    def _last_n_weeks(self, match) -> Dict[str, Any]:
        n = int(match.group(2))
        days = n * 7
        return {"field": "dc:modified", "operator": ">=", "value": f"NOW('-P{days}D')"}

    def _last_n_months(self, match) -> Dict[str, Any]:
        n = match.group(2)
        return {"field": "dc:modified", "operator": ">=", "value": f"NOW('-P{n}M')"}

    def _last_n_years(self, match) -> Dict[str, Any]:
        n = match.group(2)
        return {"field": "dc:modified", "operator": ">=", "value": f"NOW('-P{n}Y')"}

    def _since_date(self, match) -> Dict[str, Any]:
        date = match.group(2)
        return {"field": "dc:modified", "operator": ">=", "value": f"DATE '{date}'"}

    def _before_date(self, match) -> Dict[str, Any]:
        date = match.group(2)
        return {"field": "dc:modified", "operator": "<", "value": f"DATE '{date}'"}

    def _between_dates(self, match) -> Dict[str, Any]:
        date1 = match.group(2)
        date2 = match.group(3)
        return {
            "field": "dc:modified",
            "operator": "BETWEEN",
            "value": f"DATE '{date1}' AND DATE '{date2}'",
        }

    def detect_search_intent(self, query: str) -> str:
        """Detect whether query is for repository or audit index."""
        query_lower = query.lower()

        # Audit-specific keywords
        audit_keywords = [
            "audit",
            "log",
            "event",
            "activity",
            "deletion",
            "modification",
            "who deleted",
            "who modified",
            "who created",
            "what did",
        ]

        for keyword in audit_keywords:
            if keyword in query_lower:
                return "audit"

        # Default to repository search
        return "repository"

    def parse_to_elasticsearch(
        self,
        query: str,
        index: str = "repository",
        include_sort: bool = False,
        include_pagination: bool = False,
        include_highlight: bool = False,
        highlight_fragment_size: int = 150,
        highlight_number_of_fragments: int = 3,
        source_includes: Optional[List[str]] = None,
        source_excludes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Parse natural language query to Elasticsearch DSL."""
        from .es_query_builder import ElasticsearchQueryBuilder

        # Parse the natural language query
        parsed = self.parse(query)

        # Build Elasticsearch query
        es_builder = ElasticsearchQueryBuilder()
        es_query = self.build_elasticsearch_query(parsed, index)

        # Build complete search request
        size = parsed.limit if include_pagination and parsed.limit else 20
        from_ = 0  # Can be extended to support offset

        sort = None
        if include_sort and parsed.order_by:
            sort = [{parsed.order_by: {"order": parsed.order_direction or "ASC"}}]

        request = es_builder.build_search_request(
            query=es_query,
            size=size,
            from_=from_,
            sort=sort,
            source_includes=source_includes,
            source_excludes=source_excludes,
        )

        # Add highlighting if requested
        if include_highlight:
            request["highlight"] = {
                # require_field_match=false allows highlighting ecm:binarytext
                # even though the query targets all_field (a copy_to aggregate)
                "require_field_match": False,
                "fields": {
                    "dc:title": {},
                    "dc:description": {},
                    "ecm:binarytext": {
                        "fragment_size": highlight_fragment_size,
                        "number_of_fragments": highlight_number_of_fragments,
                    },
                }
            }

        return request

    def build_elasticsearch_query(
        self, parsed: ParsedQuery, index: str = "repository"
    ) -> Dict[str, Any]:
        """Build Elasticsearch query from parsed natural language."""
        from .es_query_builder import ElasticsearchQueryBuilder

        es_builder = ElasticsearchQueryBuilder()
        must_clauses = []
        filter_clauses = []

        # Handle document type
        if parsed.doc_type and parsed.doc_type != "Document":
            # Map common types to Nuxeo types (but NOT "Document" which means all types)
            type_mapping = {
                "pdf": "File",
                "image": "Picture",
                "picture": "Picture",
                "video": "Video",
                "file": "File",
                "folder": "Folder",
                "workspace": "Workspace",
                "note": "Note",
            }
            nuxeo_type = type_mapping.get(parsed.doc_type.lower(), parsed.doc_type)
            must_clauses.append(es_builder.term("ecm:primaryType", nuxeo_type))

        # Handle conditions
        for condition in parsed.conditions:
            field = condition["field"]
            operator = condition["operator"]
            value = condition["value"]
            original_value = value  # Keep original for pattern matching

            # Clean value - remove quotes
            if isinstance(value, str):
                value = value.strip("'").strip('"')

            # Map to appropriate Elasticsearch query
            if field in ["dc:created", "dc:modified"]:
                # Time-based queries - convert NXQL time formats to ES date math
                # Handle DATE format strings (check original value before cleaning)
                if "DATE '" in original_value:
                    # Handle special DATE values
                    if "DATE 'TODAY'" in original_value:
                        if operator == ">=":
                            filter_clauses.append(es_builder.range(field, gte="now/d"))
                        elif operator == "<":
                            filter_clauses.append(es_builder.range(field, lt="now/d"))
                        elif operator == "<=":
                            filter_clauses.append(es_builder.range(field, lte="now/d"))
                        else:
                            filter_clauses.append(es_builder.range(field, gte="now/d"))
                        continue
                    # Extract the date from DATE 'YYYY-MM-DD' format
                    import re
                    date_match = re.search(r"DATE '(\d{4}-\d{2}-\d{2})'", original_value)
                    if date_match:
                        date_str = date_match.group(1)
                        if operator == ">=":
                            filter_clauses.append(es_builder.range(field, gte=date_str))
                        elif operator == "<":
                            filter_clauses.append(es_builder.range(field, lt=date_str))
                        elif operator == "<=":
                            filter_clauses.append(es_builder.range(field, lte=date_str))
                        else:
                            filter_clauses.append(es_builder.range(field, gte=date_str))
                    continue
                elif "NOW('-P" in value:
                    # Extract the period from NOW('-PxD') format
                    import re

                    period_match = re.search(r"NOW\('-P(\d+)([DWMY])", value)
                    if period_match:
                        amount = period_match.group(1)
                        unit = period_match.group(2).lower()
                        filter_clauses.append(
                            es_builder.range(field, gte=f"now-{amount}{unit}")
                        )
                elif operator == ">=":
                    filter_clauses.append(es_builder.range(field, gte=value))
                elif operator == "<=":
                    filter_clauses.append(es_builder.range(field, lte=value))
                elif operator == ">":
                    filter_clauses.append(es_builder.range(field, gt=value))
                elif operator == "<":
                    filter_clauses.append(es_builder.range(field, lt=value))
                elif operator == "BETWEEN":
                    # Handle BETWEEN for NXQL format
                    if " AND " in value:
                        parts = value.split(" AND ")
                        if len(parts) == 2:
                            # First try to extract dates from DATE 'YYYY-MM-DD' format
                            import re
                            start_match = re.search(r"DATE '(\d{4}-\d{2}-\d{2})'", parts[0])
                            end_match = re.search(r"DATE '(\d{4}-\d{2}-\d{2})'", parts[1])
                            
                            if start_match and end_match:
                                start = start_match.group(1)
                                end = end_match.group(1)
                            else:
                                # Fallback to old logic for NOW() format
                                start = (
                                    parts[0]
                                    .replace("DATE '", "")
                                    .replace("'", "")
                                    .replace("NOW('-P", "now-")
                                    .replace("')", "")
                                )
                                end = (
                                    parts[1]
                                    .replace("DATE '", "")
                                    .replace("'", "")
                                    .replace("NOW('-P", "now-")
                                    .replace("')", "")
                                )
                            # Convert TODAY-1 format to now-1d
                            if "TODAY-" in start:
                                days = start.replace("TODAY-", "")
                                start = f"now-{days}d/d"
                            elif "TODAY" in start:
                                start = "now/d"
                            if "TODAY-" in end:
                                days = end.replace("TODAY-", "")
                                end = f"now-{days}d/d"
                            elif "TODAY" in end:
                                end = "now/d"
                            filter_clauses.append(
                                es_builder.range(field, gte=start, lte=end)
                            )
                    elif isinstance(value, (list, tuple)) and len(value) == 2:
                        filter_clauses.append(
                            es_builder.range(field, gte=value[0], lte=value[1])
                        )
            elif field in ["dc:creator", "dc:contributors", "dc:lastContributor"]:
                # User queries
                if index == "audit":
                    # For audit index, use principalName
                    filter_clauses.append(es_builder.term("principalName", value))
                else:
                    filter_clauses.append(es_builder.term(field, value))
            elif field == "dc:title":
                # Title queries - use match for better text matching
                if operator == "LIKE":
                    must_clauses.append(es_builder.match(field, value))
                else:
                    filter_clauses.append(es_builder.term(field, value))
            elif field == "ecm:fulltext":
                # Fulltext search
                must_clauses.append(es_builder.fulltext_query(value))
            elif field == "ecm:path":
                # Path queries
                if operator == "STARTSWITH":
                    filter_clauses.append(es_builder.path_query(value))
                else:
                    filter_clauses.append(es_builder.term(field, value))
            elif field == "ecm:currentLifeCycleState":
                # State queries
                filter_clauses.append(es_builder.term(field, value))
            elif field == "ecm:isTrashed":
                # Trash status
                filter_clauses.append(es_builder.term(field, value))
            elif field == "ecm:isVersion":
                # Version status
                filter_clauses.append(es_builder.term(field, value == "true"))
            else:
                # Generic field handling
                if operator in ["=", "=="]:
                    filter_clauses.append(es_builder.term(field, value))
                elif operator == "LIKE":
                    must_clauses.append(es_builder.match(field, value))

        # Handle audit-specific fields
        if index == "audit":
            # Map common audit queries
            for condition in parsed.conditions:
                field = condition["field"]
                if field == "eventId":
                    filter_clauses.append(
                        es_builder.term("eventId", condition["value"])
                    )
                elif field == "eventDate":
                    # Already handled above as dc:created/modified
                    pass

        # Build final query
        if not must_clauses and not filter_clauses:
            # No conditions - match all
            return {"match_all": {}}
        elif must_clauses and not filter_clauses:
            # Only must clauses
            if len(must_clauses) == 1:
                return must_clauses[0]
            else:
                return es_builder.bool_query(must=must_clauses)
        elif filter_clauses and not must_clauses:
            # Only filter clauses
            if len(filter_clauses) == 1:
                return filter_clauses[0]
            else:
                return es_builder.bool_query(filter=filter_clauses)
        else:
            # Both must and filter clauses
            return es_builder.bool_query(must=must_clauses, filter=filter_clauses)


class NXQLBuilder:
    """Builds NXQL queries from parsed components"""

    def __init__(self, parsed_query: ParsedQuery):
        self.parsed = parsed_query

    def build(self) -> str:
        """Build the NXQL query string"""
        # Build SELECT clause (MongoDB doesn't support aggregates)
        select_clause = "*"

        # Build FROM clause
        from_clause = self.parsed.doc_type

        # Build WHERE clause
        where_clauses = []
        for condition in self.parsed.conditions:
            if condition["operator"] == "BETWEEN":
                where_clauses.append(
                    f"{condition['field']} {condition['operator']} {condition['value']}"
                )
            else:
                where_clauses.append(
                    f"{condition['field']} {condition['operator']} {condition['value']}"
                )

        # Construct the query
        query_parts = [f"SELECT {select_clause}", f"FROM {from_clause}"]

        if where_clauses:
            query_parts.append(f"WHERE {' AND '.join(where_clauses)}")

        # Add ORDER BY clause
        if self.parsed.order_by:
            direction = self.parsed.order_direction or "ASC"
            query_parts.append(f"ORDER BY {self.parsed.order_by} {direction}")

        return " ".join(query_parts)
