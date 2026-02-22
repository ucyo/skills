# Oracle DB Read-Only Proxy

A lightweight HTTP proxy that provides read-only SQL access to an Oracle database. Designed so that the pi agent can query the database without ever seeing the credentials.

## Architecture

```
┌──────────────────┐     ┌───────────────────┐     ┌──────────┐
│  Pi container    │────▶│  Proxy container   │────▶│  Oracle  │
│  (no creds)      │     │  (has creds)       │     │    DB    │
│                  │     │  port 8080         │     │          │
│  curl proxy:8080 │     │  SELECT only       │     │          │
└──────────────────┘     └───────────────────┘     └──────────┘
```

- **Pi container**: No database credentials. Queries via HTTP.
- **Proxy container**: Holds credentials. Only allows SELECT statements. Caps results at 10,000 rows.
- **Oracle DB**: Your existing database. No changes needed.

## Setup

### 1. Configure credentials

```bash
cp .env.example .env
# Edit .env with your Oracle credentials
```

### 2. Start the services

```bash
docker compose up -d
```

### 3. Verify

```bash
# From the host
curl http://localhost:8080/health

# List schemas
curl http://localhost:8080/schemas | jq

# Test a query
curl http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT 1 FROM dual"}' | jq
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/schemas` | List all schemas |
| GET | `/tables?schema=X` | List tables in a schema |
| GET | `/describe?table=T&schema=X` | Describe table columns and row count |
| GET | `/search?q=term` | Search tables by name |
| POST | `/query` | Execute a SELECT query |

### POST /query

```json
{"sql": "SELECT * FROM employees WHERE rownum <= 10"}
```

Response:
```json
{
  "columns": ["EMPLOYEE_ID", "FIRST_NAME"],
  "rows": [{"EMPLOYEE_ID": 100, "FIRST_NAME": "Steven"}],
  "row_count": 1,
  "truncated": false
}
```

## Security

- Only `SELECT` and `WITH` (CTE) statements are allowed
- `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `MERGE`, `GRANT`, `REVOKE`, `EXEC`, `EXECUTE`, and `CALL` are blocked
- Results capped at 10,000 rows (configurable via `MAX_ROWS`)
- Credentials exist only in the proxy container's environment
- `.env` is gitignored

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ORACLE_USER` | (required) | Database username |
| `ORACLE_PASSWORD` | (required) | Database password |
| `ORACLE_DSN` | (required) | Connection string (`host:port/service`) |
| `MAX_ROWS` | 10000 | Maximum rows returned per query |
| `PORT` | 8080 | Proxy listen port |

## Troubleshooting

- **Connection refused**: Check that the Oracle DB is reachable from the proxy container. You may need to add `network_mode: host` or configure Docker networking.
- **ORA-12541 TNS:no listener**: Verify the DSN host, port, and service name.
- **Thin mode limitations**: The proxy uses `python-oracledb` in thin mode (no Oracle Client needed). Some features like Advanced Queuing are not available, but standard SQL works fine.
