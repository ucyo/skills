---
name: oracle-db
description: "Query an Oracle database via a read-only HTTP proxy. Use when the user asks to explore, query, or analyze data in an Oracle database. Supports schema discovery, table descriptions, and SELECT queries."
---

# Oracle DB (Read-Only Proxy)

Query an Oracle database through a local HTTP proxy. The proxy runs in a separate container with the credentials — this agent never has access to them.

## Setup

See [setup/README.md](setup/README.md) for Docker Compose configuration.

Once running, the proxy is available at `http://oracle-proxy:8080` (from within the pi container) or `http://localhost:8080` (from the host).

## Endpoints

### Run a SELECT query

```bash
curl -s http://oracle-proxy:8080/query \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM employees WHERE rownum <= 10"}' | jq
```

Response:
```json
{
  "columns": ["EMPLOYEE_ID", "FIRST_NAME", "LAST_NAME", "SALARY"],
  "rows": [
    {"EMPLOYEE_ID": 100, "FIRST_NAME": "Steven", "LAST_NAME": "King", "SALARY": 24000}
  ],
  "row_count": 1,
  "truncated": false
}
```

Only `SELECT` statements are allowed. Anything else returns `403`.

### List schemas

```bash
curl -s http://oracle-proxy:8080/schemas | jq
```

### List tables in a schema

```bash
curl -s "http://oracle-proxy:8080/tables?schema=HR" | jq
```

### Describe a table

```bash
curl -s "http://oracle-proxy:8080/describe?table=EMPLOYEES&schema=HR" | jq
```

Response:
```json
{
  "table": "EMPLOYEES",
  "schema": "HR",
  "columns": [
    {"name": "EMPLOYEE_ID", "type": "NUMBER", "nullable": false},
    {"name": "FIRST_NAME", "type": "VARCHAR2(20)", "nullable": true}
  ],
  "row_count": 107
}
```

### Search for tables by name

```bash
curl -s "http://oracle-proxy:8080/search?q=emp" | jq
```

## Query Tips

- Always use `WHERE rownum <= N` or `FETCH FIRST N ROWS ONLY` to limit results — the proxy caps at 10000 rows per request
- Use `/schemas` and `/tables` to discover the data model before querying
- Use `/describe` to check column names and types before writing queries
- Oracle uses uppercase identifiers by default — `EMPLOYEES` not `employees`
- String comparisons are case-sensitive unless you use `UPPER()` or `LOWER()`
- Use `TO_DATE('2026-01-01', 'YYYY-MM-DD')` for date comparisons
- `NVL(col, default)` for null handling (Oracle's `COALESCE` equivalent)

## Workflow

1. `/schemas` — see what's available
2. `/tables?schema=X` — browse tables
3. `/describe?table=T&schema=X` — understand structure
4. `/query` with `SELECT` — get data
5. Iterate and refine queries based on results
