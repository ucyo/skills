---
name: sql-db
description: "Query a SQL database via a read-only HTTP proxy. Use when the user asks to explore, query, or analyze data in a database. Supports PostgreSQL, MySQL/MariaDB, Oracle, and SQLite. Supports schema discovery, table descriptions, and SELECT queries."
---

# SQL DB (Read-Only Proxy)

Query a SQL database through a local HTTP proxy. The proxy runs in a separate container with the credentials — this agent never has access to them.

Supported databases: **PostgreSQL**, **MySQL / MariaDB**, **Oracle**, **SQLite**

## Setup

See [setup/README.md](setup/README.md) for Docker Compose configuration.

Once running, the proxy is available at `http://sql-proxy:8080` (from within the pi container) or `http://localhost:8080` (from the host).

## Endpoints

### Run a SELECT query

```bash
curl -s http://sql-proxy:8080/query \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM employees LIMIT 10"}' | jq
```

Response:
```json
{
  "columns": ["id", "first_name", "last_name", "salary"],
  "rows": [
    {"id": 1, "first_name": "Alice", "last_name": "Smith", "salary": 95000}
  ],
  "row_count": 1,
  "truncated": false
}
```

Only `SELECT` statements are allowed. Anything else returns `403`.

### List schemas

```bash
curl -s http://sql-proxy:8080/schemas | jq
```

### List tables in a schema

```bash
curl -s "http://sql-proxy:8080/tables?schema=public" | jq
```

### Describe a table

```bash
curl -s "http://sql-proxy:8080/describe?table=employees&schema=public" | jq
```

Response:
```json
{
  "table": "employees",
  "schema": "public",
  "columns": [
    {"name": "id", "type": "integer", "nullable": false},
    {"name": "first_name", "type": "character varying(50)", "nullable": true}
  ],
  "row_count": 107
}
```

### Search for tables by name

```bash
curl -s "http://sql-proxy:8080/search?q=emp" | jq
```

### Health check

```bash
curl -s http://sql-proxy:8080/health | jq
# {"status": "ok", "db_type": "postgres"}
```

## Query Tips

- Always limit results — use `LIMIT N` (PostgreSQL/MySQL/SQLite) or `FETCH FIRST N ROWS ONLY` / `WHERE rownum <= N` (Oracle). The proxy caps at 10,000 rows per request.
- Use `/schemas` and `/tables` to discover the data model before querying.
- Use `/describe` to check column names and types before writing queries.
- **PostgreSQL / SQLite**: identifiers are lowercase by default.
- **Oracle / MySQL**: identifiers may be uppercase. Oracle uses `UPPER()` / `LOWER()` for case-insensitive string comparisons.
- **Date literals**: PostgreSQL uses `'2026-01-01'::date`; MySQL uses `DATE('2026-01-01')`; Oracle uses `TO_DATE('2026-01-01', 'YYYY-MM-DD')`; SQLite stores dates as text.
- **NULL handling**: `COALESCE(col, default)` works on all databases. Oracle also supports `NVL(col, default)`.
- **SQLite**: has no schema concept — use `/tables` directly (schema parameter is ignored).

## Workflow

1. `/health` — confirm the proxy is up and check which database type is active
2. `/schemas` — see what schemas/databases are available
3. `/tables?schema=X` — browse tables in a schema
4. `/describe?table=T&schema=X` — understand structure and row counts
5. `/query` with `SELECT` — get data
6. Iterate and refine queries based on results
