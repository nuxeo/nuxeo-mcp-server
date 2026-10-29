# NXQL guide for nuxeo_search_documents

NXQL is Nuxeo's document query language. `nuxeo_search_documents` with
`mode="nxql"` runs one statement and returns whole documents, a page at a time,
already filtered to what the current user may read.

## Start every query from the default filter

A repository holds more than the documents a user sees: system documents
(workflow models, administrative status), every version of a document, proxies
(published copies), and the trash. Without a filter they all come back, and the
same document appears several times.

```sql
SELECT * FROM Document
WHERE ecm:mixinType != 'HiddenInNavigation' AND ecm:isProxy = 0
  AND ecm:isVersion = 0 AND ecm:isTrashed = 0
```

Add your conditions to this. Drop a clause only on purpose: `ecm:isVersion = 1`
to list versions, `ecm:isTrashed = 1` to look in the trash.

## What this tool does not do

- **No aggregates or projections.** The `SELECT` clause is ignored: `SELECT
  COUNT(...)`, `SELECT dc:title`, `DISTINCT` and `GROUP BY` all return whole
  documents, not values. To count matches, read `totalCount` (use
  `page_size: 1`). For counts per value, sums, date histograms, or
  highlighting, use `nuxeo_search_documents_with_query_dsl`.
- **No paging past the result window.** Refine the query instead of walking
  many pages.

## Syntax

```sql
SELECT * FROM <types> [WHERE <conditions>] [ORDER BY <property> [ASC|DESC], ...]
```

- `<types>`: one or more document types, comma-separated. `Document` matches
  every type.
- Conditions combine with `AND`, `OR`, `NOT` and parentheses.
- Strings use single quotes. Escape a quote or a backslash with a backslash:
  `'Alice\'s report'`, `'C:\\temp'`. Never double the quote.
- Dates: `DATE '2026-01-31'`, `TIMESTAMP '2026-01-31T12:00:00'`, or relative
  with `NOW('-P30D')` (ISO 8601 period: `-P1D`, `-PT2H`, `-P1M`).
- Booleans (`ecm:is*`) compare to `1` or `0`.

| Operator | Use |
|---|---|
| `=`, `!=`, `<`, `<=`, `>`, `>=` | exact values, dates, numbers |
| `IN (...)`, `NOT IN (...)` | one of several values |
| `BETWEEN a AND b` | ranges |
| `LIKE 'prefix%'` | case-sensitive pattern; `%` any characters, `_` one |
| `STARTSWITH '/path'` | everything under a path (`ecm:path`) |
| `IS NULL`, `IS NOT NULL` | missing values |

Avoid `ILIKE` and leading wildcards (`LIKE '%word%'`): they are slow, and
`ILIKE` returns nothing on fields the search index does not map for it. Use
`ecm:fulltext` to find words.

## Full-text search

```sql
SELECT * FROM Document
WHERE ecm:fulltext = 'quarterly report'
  AND ecm:mixinType != 'HiddenInNavigation' AND ecm:isProxy = 0
  AND ecm:isVersion = 0 AND ecm:isTrashed = 0
ORDER BY ecm:fulltextScore DESC
```

- Searches the title, description, string properties and the text extracted
  from attached files.
- All words must match. `-word` excludes a word, `word*` matches a prefix.
- `ecm:fulltext.dc:title = 'word'` restricts the search to one property.
- `ORDER BY ecm:fulltextScore DESC` ranks by relevance; otherwise results are
  not ranked.

Full-text search is served by the search engine. If Nuxeo answers that
full-text search is disabled, report that to the user; do not emulate it with
`LIKE`.

## Useful properties

| Property | Meaning |
|---|---|
| `ecm:uuid` | document id |
| `ecm:name` | name in its parent (last path segment) |
| `ecm:path` | full path; use with `=` or `STARTSWITH` only |
| `ecm:parentId` | parent id: direct children |
| `ecm:ancestorId` | any ancestor id: a whole subtree by id |
| `ecm:primaryType` | document type, e.g. `File`, `Note`, `Folder` |
| `ecm:mixinType` | facets, e.g. `Folderish`, `Versionable`, `HiddenInNavigation` |
| `ecm:currentLifeCycleState` | lifecycle state, e.g. `project`, `approved` |
| `ecm:isVersion`, `ecm:isProxy`, `ecm:isTrashed` | see the default filter |
| `ecm:isLatestVersion`, `ecm:versionLabel` | version queries |
| `ecm:tag` | a tag |
| `dc:title`, `dc:description` | title, description |
| `dc:creator`, `dc:lastContributor`, `dc:contributors` | usernames |
| `dc:created`, `dc:modified` | dates |
| `file:content/name`, `file:content/mime-type`, `file:content/length` | main attached file |

Schema properties are written `prefix:name`; sub-properties of a complex
property use `/`, as in `file:content/name`. Use `nuxeo_get_metadata_schema`
for the properties of the deployed content model.

A list property such as `dc:contributors` matches if any value matches:
`dc:contributors = 'bob'`.

## Examples

All of them start from the default filter, written `<default filter>` here for
brevity: `ecm:mixinType != 'HiddenInNavigation' AND ecm:isProxy = 0 AND
ecm:isVersion = 0 AND ecm:isTrashed = 0`.

```sql
-- Files under a folder, newest first
SELECT * FROM File WHERE ecm:path STARTSWITH '/default-domain/workspaces/Finance'
  AND <default filter> ORDER BY dc:modified DESC

-- Direct children of a folder, by id
SELECT * FROM Document WHERE ecm:parentId = '5442fff5-06f1-47c9-ac59-1e10ef8e985b'
  AND <default filter>

-- Created by one of two users in the last 30 days
SELECT * FROM Document WHERE dc:creator IN ('alice', 'bob')
  AND dc:created >= NOW('-P30D') AND <default filter>

-- PDFs whose title starts with "Invoice"
SELECT * FROM File WHERE file:content/mime-type = 'application/pdf'
  AND dc:title LIKE 'Invoice%' AND <default filter>

-- Words in the content, best matches first
SELECT * FROM Document WHERE ecm:fulltext = 'contract renewal'
  AND <default filter> ORDER BY ecm:fulltextScore DESC

-- Folders only
SELECT * FROM Document WHERE ecm:mixinType = 'Folderish' AND <default filter>

-- Every version of one document
SELECT * FROM Document WHERE ecm:versionVersionableId = '<live document id>'
  AND ecm:isVersion = 1 ORDER BY ecm:versionLabel DESC

-- What is in the trash
SELECT * FROM Document WHERE ecm:isTrashed = 1 AND ecm:isVersion = 0
```
