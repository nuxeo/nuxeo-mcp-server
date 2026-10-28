"""OpenSearch/Elasticsearch passthrough client for Nuxeo MCP."""

import json
import logging
import os
import re
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Bounds an unparseable error body (an HTML page, a proxy error) so that it
# cannot flood the caller's context.
MAX_ERROR_DETAIL = 300

_JAVA_EXCEPTION_PREFIX = re.compile(r"^(?:[\w$]+\.)+[\w$]*(?:Exception|Error):\s*")


class PassthroughError(Exception):
    """A passthrough request failed; ``str()`` is a sentence meant for the model.

    ``unavailable`` separates "this server cannot do it" from "this request is
    wrong": a model must stop retrying on the former and fix its query on the
    latter, and the raw engine output does not make the difference obvious.
    """

    def __init__(
        self, message: str, status: Optional[int] = None, unavailable: bool = False
    ) -> None:
        super().__init__(message)
        self.status = status
        self.unavailable = unavailable


def _server_message(response: requests.Response) -> str:
    """Return the reason Nuxeo gave, without the Java exception class prefix."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return _JAVA_EXCEPTION_PREFIX.sub("", body["message"]).strip()
    text = (response.text or "").strip()
    return text[:MAX_ERROR_DETAIL] + ("..." if len(text) > MAX_ERROR_DETAIL else "")


def _explain(status: int, message: str, index: str) -> PassthroughError:
    """Map a Nuxeo passthrough failure to an actionable error."""
    lowered = message.lower()
    if "audit" in lowered and "passthrough is disabled" in lowered:
        return PassthroughError(
            "Audit search is disabled on this Nuxeo server "
            "(nuxeo.passthrough.elasticsearch.audit.enabled=false). "
            "Changing the query will not help.",
            status,
            unavailable=True,
        )
    if "passthrough is disabled" in lowered:
        return PassthroughError(
            "Query DSL search is disabled on this Nuxeo server "
            "(nuxeo.passthrough.elasticsearch.enabled=false). Changing the query "
            "will not help; use nuxeo_search_documents instead.",
            status,
            unavailable=True,
        )
    if "audit" in lowered and (
        "not configured" in lowered or "not installed" in lowered
    ):
        return PassthroughError(
            "The audit log of this Nuxeo server is not stored in "
            "OpenSearch/Elasticsearch (e.g. MongoDB or SQL audit backend), so it "
            "cannot be searched with Query DSL. Changing the query will not help.",
            status,
            unavailable=True,
        )
    if status == 403:
        if index == "audit":
            return PassthroughError(
                "Audit search is restricted to administrators, and the current "
                "Nuxeo user is not one.",
                status,
                unavailable=True,
            )
        return PassthroughError(f"Permission denied: {message}", status)
    if status == 404:
        return PassthroughError(
            "Query DSL search is not available on this Nuxeo server: the search "
            "passthrough (/site/es) is not installed, which happens when the "
            "repository is not indexed in OpenSearch/Elasticsearch. Changing the "
            "query will "
            "not help; use nuxeo_search_documents instead.",
            status,
            unavailable=True,
        )
    return PassthroughError(f"Nuxeo rejected the request (HTTP {status}): {message}")


def _engine_error(body: Dict[str, Any]) -> PassthroughError:
    """Map a search engine error, which Nuxeo relays inside an HTTP 200."""
    error = body.get("error")
    if isinstance(error, dict):
        reason = error.get("reason") or error.get("type") or json.dumps(error)
        causes = [
            c.get("reason")
            for c in (error.get("root_cause") or [])
            if isinstance(c, dict) and c.get("reason") and c.get("reason") != reason
        ]
        caused_by = error.get("caused_by")
        if isinstance(caused_by, dict) and caused_by.get("reason"):
            causes.append(caused_by["reason"])
        detail = "; ".join(dict.fromkeys([str(reason), *map(str, causes)]))
    else:
        detail = str(error)
    return PassthroughError(
        f"The search engine rejected the query: {detail}. Fix the query and retry.",
        body.get("status") if isinstance(body.get("status"), int) else None,
    )


class ElasticsearchPassthrough:
    """Send Query DSL requests through Nuxeo's /site/es passthrough.

    ACL enforcement is handled server-side by the Nuxeo passthrough — this class
    forwards queries as-is and does not inject any Python-side ACL filter.
    """

    def __init__(self, nuxeo_url: Optional[str] = None, auth: Optional[tuple] = None):
        """Initialize the passthrough client.

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

    def execute_query(self, index: str, query: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a search through the Nuxeo passthrough endpoint.

        Args:
            index: Target index name
            query: Query DSL request body

        Returns:
            Raw search engine response

        Raises:
            PassthroughError: with a message written for the model.
        """
        url = f"{self.base_url}/{index}/_search"
        try:
            # Nuxeo answers bad credentials with a redirect to its login page;
            # following it turns an auth failure into an unparseable HTML 200.
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(query),
                auth=self.auth,
                timeout=30,
                allow_redirects=False,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Passthrough connection error: {e}")
            raise PassthroughError(f"Could not reach Nuxeo at {url}: {e}")

        if response.status_code in (301, 302, 303, 307, 308, 401):
            raise PassthroughError(
                "Nuxeo did not accept the MCP server credentials "
                f"(HTTP {response.status_code}).",
                response.status_code,
                unavailable=True,
            )
        if response.status_code != 200:
            error = _explain(response.status_code, _server_message(response), index)
            logger.warning(f"Passthrough error on {url}: {error}")
            raise error

        try:
            body = response.json()
        except ValueError:
            raise PassthroughError(
                "Nuxeo returned a non-JSON response "
                f"({response.headers.get('Content-Type', 'unknown type')}): "
                f"{_server_message(response)}",
                response.status_code,
            )
        if isinstance(body, dict) and "error" in body:
            raise _engine_error(body)
        if not isinstance(body, dict):
            raise PassthroughError(
                f"Unexpected search response: {str(body)[:MAX_ERROR_DETAIL]}"
            )
        return body
