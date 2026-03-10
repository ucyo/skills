# SQL DB Read-Only Proxy

A lightweight HTTP proxy that provides read-only SQL access to a database. Designed so that the pi agent can query the database without ever seeing the credentials.

Supported databases: **PostgreSQL**, **MySQL / MariaDB**, **Oracle**, **SQLite**

## Architecture

```
┌──────────────────┐     ┌───────────────────┐     ┌──────────┐
│  Pi container    │────▶│  Proxy container   │────▶│    DB    │
│  (no creds)      │     │  (has creds)       │     │          │
│                  │     │  port 8080         │     │          │
│  curl proxy:8080 │     │  SELECT only       │     │          │
└──────────────────┘     └───────────────────┘     └──────────┘
```

- **Pi container**: No database credentials. Queries via HTTP.
- **Proxy container**: Holds credentials. Only allows SELECT statements. Caps results at 10,000 rows.
- **DB**: Your existing database. No changes needed.

## Setup

### 1. Configure credentials

```bash
cp .env.example .env
# Edit .env — set DB_TYPE and connection details
```

### 2. Start the services

```bash
docker compose up -d
```

For **SQLite**, also mount the database file (see the volume comment in `docker-compose.yml`).

### 3. Verify

```bash
# Health check (also shows which DB_TYPE is active)
curl http://localhost:8080/health

# List schemas
curl http://localhost:8080/schemas | jq

# Test a query
curl http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT 1"}' | jq
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (includes `db_type`) |
| GET | `/schemas` | List schemas / databases |
| GET | `/tables?schema=X` | List tables in a schema |
| GET | `/describe?table=T&schema=X` | Describe table columns and row count |
| GET | `/search?q=term` | Search tables by name |
| POST | `/query` | Execute a SELECT query |

### POST /query

```json
{"sql": "SELECT * FROM employees LIMIT 10"}
```

Response:
```json
{
  "columns": ["id", "first_name", "last_name"],
  "rows": [{"id": 1, "first_name": "Alice", "last_name": "Smith"}],
  "row_count": 1,
  "truncated": false
}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_TYPE` | (required) | `oracle`, `postgres`, `mysql`, or `sqlite` |
| `DB_USER` | (required*) | Database username (*not needed for sqlite) |
| `DB_PASSWORD` | (required*) | Database password (*not needed for sqlite) |
| `DB_HOST` | (required*) | Database host (*not needed for sqlite) |
| `DB_PORT` | driver default | Database port (optional) |
| `DB_NAME` | (required) | Database/schema name, or SQLite file path |
| `MAX_ROWS` | 10000 | Maximum rows returned per query |
| `PORT` | 8080 | Proxy listen port |

## Security

- Only `SELECT` and `WITH` (CTE) statements are allowed
- Dangerous keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `MERGE`, `GRANT`, `REVOKE`, `EXEC`, `EXECUTE`, `CALL`) are blocked
- Results capped at `MAX_ROWS` rows
- Credentials exist only in the proxy container's environment
- `.env` is gitignored

## Troubleshooting

- **Connection refused**: Verify the database is reachable from the proxy container. You may need `network_mode: host` or Docker network configuration.
- **PostgreSQL**: Check `DB_HOST`, `DB_PORT`, `DB_NAME`, and that the user has `CONNECT` and `SELECT` privileges.
- **MySQL**: Ensure the user has `SELECT` on the target database.
- **Oracle — ORA-12541 TNS:no listener**: Verify `DB_HOST`, `DB_PORT`, and `DB_NAME` (service name). The proxy uses `python-oracledb` in thin mode (no Oracle Client needed).
- **SQLite**: Make sure the `.db` file is mounted into the container and `DB_NAME` points to the correct path inside it.
