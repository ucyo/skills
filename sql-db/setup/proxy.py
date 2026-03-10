#!/usr/bin/env python3
"""
Read-only SQL proxy. Accepts SQL over HTTP, forwards to the configured database.
Only SELECT statements are allowed.

Environment variables:
  DB_TYPE         - One of: oracle, postgres, mysql, sqlite
  DB_USER         - Database username (not needed for sqlite)
  DB_PASSWORD     - Database password (not needed for sqlite)
  DB_HOST         - Database host (not needed for sqlite)
  DB_PORT         - Database port (optional, uses driver default)
  DB_NAME         - Database name / service name / file path (sqlite)
  MAX_ROWS        - Maximum rows per query (default: 10000)
  PORT            - Listen port (default: 8080)
"""

import os
import sys
import re
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("sql-proxy")

DB_TYPE     = os.environ.get("DB_TYPE", "").lower()
DB_USER     = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_HOST     = os.environ.get("DB_HOST", "")
DB_PORT     = os.environ.get("DB_PORT", "")
DB_NAME     = os.environ.get("DB_NAME", "")
MAX_ROWS    = int(os.environ.get("MAX_ROWS", "10000"))
PORT        = int(os.environ.get("PORT", "8080"))

SUPPORTED_DB_TYPES = ("oracle", "postgres", "mysql", "sqlite")

# ---------------------------------------------------------------------------
# Connection pool / factory
# ---------------------------------------------------------------------------

_pool = None   # used for oracle only
_sqlite_path = None


def _default_port(db_type):
    return {"oracle": "1521", "postgres": "5432", "mysql": "3306"}.get(db_type, "")


def get_connection():
    """Return a new (or pooled) database connection."""
    if DB_TYPE == "oracle":
        import oracledb
        global _pool
        if _pool is None:
            dsn = f"{DB_HOST}:{DB_PORT or _default_port('oracle')}/{DB_NAME}"
            _pool = oracledb.create_pool(
                user=DB_USER, password=DB_PASSWORD, dsn=dsn, min=1, max=4, increment=1
            )
        return _pool.acquire()

    elif DB_TYPE == "postgres":
        import psycopg2
        return psycopg2.connect(
            host=DB_HOST,
            port=int(DB_PORT or _default_port("postgres")),
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )

    elif DB_TYPE == "mysql":
        import pymysql
        return pymysql.connect(
            host=DB_HOST,
            port=int(DB_PORT or _default_port("mysql")),
            db=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            cursorclass=pymysql.cursors.Cursor,
            autocommit=True,
        )

    elif DB_TYPE == "sqlite":
        import sqlite3
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = None  # keep as tuples
        return conn

    else:
        raise RuntimeError(f"Unsupported DB_TYPE: {DB_TYPE!r}")


def release_connection(conn):
    """Return connection to pool (oracle) or close it (others)."""
    if DB_TYPE == "oracle":
        import oracledb
        _pool.release(conn)
    else:
        conn.close()


# ---------------------------------------------------------------------------
# SQL safety check
# ---------------------------------------------------------------------------

def is_select_only(sql):
    """Return True only for read-only SELECT / WITH statements."""
    cleaned = re.sub(r"--[^\n]*", "", sql)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip().rstrip(";").strip()

    if not cleaned:
        return False

    first_word = cleaned.split()[0].upper()
    if first_word not in ("SELECT", "WITH"):
        return False

    dangerous = (
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|"
        r"MERGE|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b"
    )
    if re.search(dangerous, cleaned, re.IGNORECASE):
        return False

    return True


# ---------------------------------------------------------------------------
# Row serialisation
# ---------------------------------------------------------------------------

def serialize_row(columns, row):
    result = {}
    for col, val in zip(columns, row):
        if isinstance(val, (bytes, bytearray)):
            result[col] = val.hex()
        elif hasattr(val, "isoformat"):
            result[col] = val.isoformat()
        else:
            # Oracle LOB
            try:
                import oracledb
                if isinstance(val, oracledb.LOB):
                    try:
                        result[col] = val.read()
                    except Exception:
                        result[col] = "<LOB>"
                    continue
            except ImportError:
                pass
            result[col] = val
    return result


# ---------------------------------------------------------------------------
# DB-specific introspection helpers
# ---------------------------------------------------------------------------

def _run(conn, sql, params=None):
    """Execute *sql* and return (columns, rows)."""
    cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    columns = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    cur.close()
    return columns, rows


def db_schemas(conn):
    if DB_TYPE == "oracle":
        _, rows = _run(conn, "SELECT username FROM all_users ORDER BY username")
        return [r[0] for r in rows]
    elif DB_TYPE == "postgres":
        _, rows = _run(
            conn,
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name NOT IN ('pg_catalog','information_schema','pg_toast') "
            "ORDER BY schema_name",
        )
        return [r[0] for r in rows]
    elif DB_TYPE == "mysql":
        _, rows = _run(conn, "SHOW DATABASES")
        return [r[0] for r in rows]
    elif DB_TYPE == "sqlite":
        # SQLite has no schemas; return a virtual "main"
        return ["main"]


def db_tables(conn, schema):
    if DB_TYPE == "oracle":
        if schema:
            _, rows = _run(
                conn,
                "SELECT table_name FROM all_tables WHERE owner = :o ORDER BY table_name",
                {"o": schema.upper()},
            )
        else:
            _, rows = _run(conn, "SELECT table_name FROM user_tables ORDER BY table_name")
        return [r[0] for r in rows]

    elif DB_TYPE == "postgres":
        s = schema or "public"
        _, rows = _run(
            conn,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s ORDER BY table_name",
            (s,),
        )
        return [r[0] for r in rows]

    elif DB_TYPE == "mysql":
        db = schema or DB_NAME
        _, rows = _run(
            conn,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s ORDER BY table_name",
            (db,),
        )
        return [r[0] for r in rows]

    elif DB_TYPE == "sqlite":
        _, rows = _run(
            conn,
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
        )
        return [r[0] for r in rows]


def db_describe(conn, table, schema):
    columns = []

    if DB_TYPE == "oracle":
        owner = schema.upper() if schema else None
        tbl = table.upper()
        if owner:
            _, rows = _run(
                conn,
                """SELECT column_name, data_type, data_length, data_precision,
                          data_scale, nullable
                   FROM all_tab_columns
                   WHERE owner = :o AND table_name = :t
                   ORDER BY column_id""",
                {"o": owner, "t": tbl},
            )
        else:
            _, rows = _run(
                conn,
                """SELECT column_name, data_type, data_length, data_precision,
                          data_scale, nullable
                   FROM user_tab_columns
                   WHERE table_name = :t
                   ORDER BY column_id""",
                {"t": tbl},
            )
        for col_name, dtype, dlen, prec, scale, nullable in rows:
            if prec is not None:
                type_str = f"{dtype}({prec},{scale})" if scale else f"{dtype}({prec})"
            elif dtype in ("VARCHAR2", "CHAR", "NVARCHAR2"):
                type_str = f"{dtype}({dlen})"
            else:
                type_str = dtype
            columns.append({"name": col_name, "type": type_str, "nullable": nullable == "Y"})

        count_ref = f"{owner}.{tbl}" if owner else tbl
        try:
            _, cnt = _run(conn, f"SELECT COUNT(*) FROM {count_ref}")
            row_count = cnt[0][0]
        except Exception:
            row_count = None

    elif DB_TYPE == "postgres":
        s = schema or "public"
        _, rows = _run(
            conn,
            """SELECT column_name,
                      CASE WHEN character_maximum_length IS NOT NULL
                           THEN data_type || '(' || character_maximum_length || ')'
                           ELSE data_type END,
                      is_nullable
               FROM information_schema.columns
               WHERE table_schema = %s AND table_name = %s
               ORDER BY ordinal_position""",
            (s, table),
        )
        columns = [{"name": r[0], "type": r[1], "nullable": r[2] == "YES"} for r in rows]
        try:
            _, cnt = _run(conn, f'SELECT COUNT(*) FROM "{s}"."{table}"')
            row_count = cnt[0][0]
        except Exception:
            row_count = None

    elif DB_TYPE == "mysql":
        db = schema or DB_NAME
        _, rows = _run(
            conn,
            """SELECT column_name, column_type, is_nullable
               FROM information_schema.columns
               WHERE table_schema = %s AND table_name = %s
               ORDER BY ordinal_position""",
            (db, table),
        )
        columns = [{"name": r[0], "type": r[1], "nullable": r[2] == "YES"} for r in rows]
        try:
            _, cnt = _run(conn, f"SELECT COUNT(*) FROM `{db}`.`{table}`")
            row_count = cnt[0][0]
        except Exception:
            row_count = None

    elif DB_TYPE == "sqlite":
        _, rows = _run(conn, f'PRAGMA table_info("{table}")')
        # cid, name, type, notnull, dflt_value, pk
        columns = [{"name": r[1], "type": r[2], "nullable": r[3] == 0} for r in rows]
        try:
            _, cnt = _run(conn, f'SELECT COUNT(*) FROM "{table}"')
            row_count = cnt[0][0]
        except Exception:
            row_count = None

    return columns, row_count


def db_search(conn, query):
    q = f"%{query.lower()}%"

    if DB_TYPE == "oracle":
        _, rows = _run(
            conn,
            """SELECT owner, table_name FROM all_tables
               WHERE LOWER(table_name) LIKE :q
               ORDER BY owner, table_name
               FETCH FIRST 50 ROWS ONLY""",
            {"q": q},
        )
        return [{"schema": r[0], "table": r[1]} for r in rows]

    elif DB_TYPE == "postgres":
        _, rows = _run(
            conn,
            """SELECT table_schema, table_name
               FROM information_schema.tables
               WHERE LOWER(table_name) LIKE %s
               ORDER BY table_schema, table_name
               LIMIT 50""",
            (q,),
        )
        return [{"schema": r[0], "table": r[1]} for r in rows]

    elif DB_TYPE == "mysql":
        _, rows = _run(
            conn,
            """SELECT table_schema, table_name
               FROM information_schema.tables
               WHERE LOWER(table_name) LIKE %s
               ORDER BY table_schema, table_name
               LIMIT 50""",
            (q,),
        )
        return [{"schema": r[0], "table": r[1]} for r in rows]

    elif DB_TYPE == "sqlite":
        _, rows = _run(
            conn,
            "SELECT name FROM sqlite_master WHERE type='table' AND LOWER(name) LIKE ? LIMIT 50",
            (q,),
        )
        return [{"schema": "main", "table": r[0]} for r in rows]


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info(format % args)

    def send_json(self, data, status=200):
        body = json.dumps(data, default=str, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json({"error": message}, status)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        try:
            if parsed.path == "/health":
                self.send_json({"status": "ok", "db_type": DB_TYPE})

            elif parsed.path == "/schemas":
                conn = get_connection()
                try:
                    schemas = db_schemas(conn)
                    self.send_json({"schemas": schemas})
                finally:
                    release_connection(conn)

            elif parsed.path == "/tables":
                schema = params.get("schema", [None])[0]
                conn = get_connection()
                try:
                    tables = db_tables(conn, schema)
                    self.send_json({"schema": schema, "tables": tables})
                finally:
                    release_connection(conn)

            elif parsed.path == "/describe":
                table = params.get("table", [None])[0]
                schema = params.get("schema", [None])[0]
                if not table:
                    self.send_error_json(400, "Missing 'table' parameter")
                    return
                conn = get_connection()
                try:
                    columns, row_count = db_describe(conn, table, schema)
                    self.send_json({
                        "table": table,
                        "schema": schema,
                        "columns": columns,
                        "row_count": row_count,
                    })
                finally:
                    release_connection(conn)

            elif parsed.path == "/search":
                q = params.get("q", [None])[0]
                if not q:
                    self.send_error_json(400, "Missing 'q' parameter")
                    return
                conn = get_connection()
                try:
                    results = db_search(conn, q)
                    self.send_json({"query": q, "results": results})
                finally:
                    release_connection(conn)

            else:
                self.send_error_json(404, "Not found")

        except Exception as e:
            log.exception("Error handling GET %s", self.path)
            self.send_error_json(500, str(e))

    def do_POST(self):
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/query":
                body = self.read_body()
                if not body or "sql" not in body:
                    self.send_error_json(400, "Missing 'sql' in request body")
                    return

                sql = body["sql"]
                if not is_select_only(sql):
                    self.send_error_json(403, "Only SELECT queries are allowed")
                    return

                conn = get_connection()
                try:
                    cur = conn.cursor()
                    cur.execute(sql)
                    col_names = [d[0] for d in cur.description]
                    rows_raw = cur.fetchmany(MAX_ROWS + 1)
                    cur.close()
                    truncated = len(rows_raw) > MAX_ROWS
                    if truncated:
                        rows_raw = rows_raw[:MAX_ROWS]
                    rows = [serialize_row(col_names, r) for r in rows_raw]
                    self.send_json({
                        "columns": col_names,
                        "rows": rows,
                        "row_count": len(rows),
                        "truncated": truncated,
                    })
                finally:
                    release_connection(conn)

            else:
                self.send_error_json(404, "Not found")

        except Exception as e:
            log.exception("Error handling POST %s", self.path)
            self.send_error_json(500, str(e))


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if DB_TYPE not in SUPPORTED_DB_TYPES:
        print(f"Error: DB_TYPE must be one of {SUPPORTED_DB_TYPES}. Got: {DB_TYPE!r}")
        sys.exit(1)

    if DB_TYPE == "sqlite":
        if not DB_NAME:
            print("Error: DB_NAME must be set to the SQLite file path")
            sys.exit(1)
    else:
        if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME]):
            print("Error: DB_USER, DB_PASSWORD, DB_HOST, and DB_NAME must all be set")
            sys.exit(1)

    log.info(
        "Starting SQL proxy on port %d (DB_TYPE=%s, DB_NAME=%s, max_rows=%d)",
        PORT, DB_TYPE, DB_NAME, MAX_ROWS,
    )

    # Test connection
    try:
        conn = get_connection()
        if DB_TYPE == "oracle":
            _run(conn, "SELECT 1 FROM dual")
        elif DB_TYPE in ("postgres", "mysql"):
            _run(conn, "SELECT 1")
        elif DB_TYPE == "sqlite":
            _run(conn, "SELECT 1")
        release_connection(conn)
        log.info("Database connection OK")
    except Exception as e:
        log.error("Failed to connect to database: %s", e)
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", PORT), ProxyHandler)
    log.info("Proxy ready")
    server.serve_forever()
