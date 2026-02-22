#!/usr/bin/env python3
"""
Read-only Oracle DB proxy. Accepts SQL over HTTP, forwards to Oracle.
Only SELECT statements are allowed.

Environment variables:
  ORACLE_USER     - Database username
  ORACLE_PASSWORD - Database password
  ORACLE_DSN      - Connection string (host:port/service_name)
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

import oracledb

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("oracle-proxy")

ORACLE_USER = os.environ.get("ORACLE_USER", "")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD", "")
ORACLE_DSN = os.environ.get("ORACLE_DSN", "")
MAX_ROWS = int(os.environ.get("MAX_ROWS", "10000"))
PORT = int(os.environ.get("PORT", "8080"))

pool = None


def get_pool():
    global pool
    if pool is None:
        pool = oracledb.create_pool(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=ORACLE_DSN,
            min=1,
            max=4,
            increment=1,
        )
    return pool


def is_select_only(sql):
    """Check that the SQL is a read-only SELECT statement."""
    cleaned = re.sub(r"--[^\n]*", "", sql)  # remove line comments
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)  # remove block comments
    cleaned = cleaned.strip().rstrip(";").strip()

    if not cleaned:
        return False

    first_word = cleaned.split()[0].upper()
    if first_word not in ("SELECT", "WITH"):
        return False

    # Block dangerous keywords at statement level
    dangerous = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|MERGE|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b"
    if re.search(dangerous, cleaned, re.IGNORECASE):
        return False

    return True


def serialize_row(columns, row):
    """Convert a row to a JSON-serializable dict."""
    result = {}
    for col, val in zip(columns, row):
        if isinstance(val, (bytes, bytearray)):
            result[col] = val.hex()
        elif hasattr(val, "isoformat"):
            result[col] = val.isoformat()
        elif isinstance(val, oracledb.LOB):
            try:
                result[col] = val.read()
            except Exception:
                result[col] = "<LOB>"
        else:
            result[col] = val
    return result


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
                self.send_json({"status": "ok"})

            elif parsed.path == "/schemas":
                self.handle_schemas()

            elif parsed.path == "/tables":
                schema = params.get("schema", [None])[0]
                self.handle_tables(schema)

            elif parsed.path == "/describe":
                table = params.get("table", [None])[0]
                schema = params.get("schema", [None])[0]
                if not table:
                    self.send_error_json(400, "Missing 'table' parameter")
                else:
                    self.handle_describe(table, schema)

            elif parsed.path == "/search":
                q = params.get("q", [None])[0]
                if not q:
                    self.send_error_json(400, "Missing 'q' parameter")
                else:
                    self.handle_search(q)

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
                self.handle_query(body["sql"])
            else:
                self.send_error_json(404, "Not found")

        except Exception as e:
            log.exception("Error handling POST %s", self.path)
            self.send_error_json(500, str(e))

    def handle_query(self, sql):
        if not is_select_only(sql):
            self.send_error_json(403, "Only SELECT queries are allowed")
            return

        with get_pool().acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                columns = [col[0] for col in cur.description]
                rows_raw = cur.fetchmany(MAX_ROWS + 1)
                truncated = len(rows_raw) > MAX_ROWS
                if truncated:
                    rows_raw = rows_raw[:MAX_ROWS]
                rows = [serialize_row(columns, r) for r in rows_raw]
                self.send_json({
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "truncated": truncated,
                })

    def handle_schemas(self):
        sql = "SELECT username FROM all_users ORDER BY username"
        with get_pool().acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                schemas = [row[0] for row in cur.fetchall()]
                self.send_json({"schemas": schemas})

    def handle_tables(self, schema):
        with get_pool().acquire() as conn:
            with conn.cursor() as cur:
                if schema:
                    cur.execute(
                        "SELECT table_name FROM all_tables WHERE owner = :owner ORDER BY table_name",
                        {"owner": schema.upper()},
                    )
                else:
                    cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
                tables = [row[0] for row in cur.fetchall()]
                self.send_json({"schema": schema, "tables": tables})

    def handle_describe(self, table, schema):
        with get_pool().acquire() as conn:
            with conn.cursor() as cur:
                if schema:
                    cur.execute(
                        """SELECT column_name, data_type, data_length, data_precision,
                                  data_scale, nullable
                           FROM all_tab_columns
                           WHERE owner = :owner AND table_name = :tbl
                           ORDER BY column_id""",
                        {"owner": schema.upper(), "tbl": table.upper()},
                    )
                else:
                    cur.execute(
                        """SELECT column_name, data_type, data_length, data_precision,
                                  data_scale, nullable
                           FROM user_tab_columns
                           WHERE table_name = :tbl
                           ORDER BY column_id""",
                        {"tbl": table.upper()},
                    )
                columns = []
                for row in cur.fetchall():
                    col_name, dtype, dlen, prec, scale, nullable = row
                    if prec is not None:
                        type_str = f"{dtype}({prec},{scale})" if scale else f"{dtype}({prec})"
                    elif dtype in ("VARCHAR2", "CHAR", "NVARCHAR2"):
                        type_str = f"{dtype}({dlen})"
                    else:
                        type_str = dtype
                    columns.append({
                        "name": col_name,
                        "type": type_str,
                        "nullable": nullable == "Y",
                    })

                # Get row count estimate
                count_table = f"{schema.upper()}.{table.upper()}" if schema else table.upper()
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {count_table}")
                    row_count = cur.fetchone()[0]
                except Exception:
                    row_count = None

                self.send_json({
                    "table": table.upper(),
                    "schema": schema.upper() if schema else None,
                    "columns": columns,
                    "row_count": row_count,
                })

    def handle_search(self, query):
        with get_pool().acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT owner, table_name
                       FROM all_tables
                       WHERE LOWER(table_name) LIKE :q
                       ORDER BY owner, table_name
                       FETCH FIRST 50 ROWS ONLY""",
                    {"q": f"%{query.lower()}%"},
                )
                results = [{"schema": row[0], "table": row[1]} for row in cur.fetchall()]
                self.send_json({"query": query, "results": results})


if __name__ == "__main__":
    if not all([ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN]):
        print("Error: Set ORACLE_USER, ORACLE_PASSWORD, and ORACLE_DSN environment variables")
        sys.exit(1)

    log.info("Starting Oracle proxy on port %d (DSN: %s, user: %s, max rows: %d)",
             PORT, ORACLE_DSN, ORACLE_USER, MAX_ROWS)

    # Test connection
    try:
        with get_pool().acquire() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM dual")
                log.info("Database connection OK")
    except Exception as e:
        log.error("Failed to connect to database: %s", e)
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", PORT), ProxyHandler)
    log.info("Proxy ready")
    server.serve_forever()
