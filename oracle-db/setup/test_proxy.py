#!/usr/bin/env python3
"""
Integration test for proxy.py using SQLite (no external DB needed).

Creates a temp SQLite database, starts the proxy as a subprocess,
exercises every endpoint, then tears everything down.
"""

import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PROXY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.py")
PORT = 18080
BASE = f"http://localhost:{PORT}"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

results = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, condition))


def get(path):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=5) as r:
        return json.loads(r.read())


def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read())


def post_expect_error(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def wait_for_proxy(timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            get("/health")
            return True
        except Exception:
            time.sleep(0.2)
    return False


# ---------------------------------------------------------------------------
# Setup: create SQLite DB with test data
# ---------------------------------------------------------------------------

def create_test_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE employees (
            id      INTEGER PRIMARY KEY,
            name    TEXT NOT NULL,
            dept    TEXT,
            salary  REAL
        );
        INSERT INTO employees VALUES (1, 'Alice',   'Engineering', 95000);
        INSERT INTO employees VALUES (2, 'Bob',     'Marketing',   72000);
        INSERT INTO employees VALUES (3, 'Charlie', 'Engineering', 88000);

        CREATE TABLE departments (
            id   INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        INSERT INTO departments VALUES (1, 'Engineering');
        INSERT INTO departments VALUES (2, 'Marketing');
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health():
    print("\n=== /health ===")
    data = get("/health")
    check("status is ok",      data.get("status") == "ok")
    check("db_type is sqlite", data.get("db_type") == "sqlite")


def test_schemas():
    print("\n=== /schemas ===")
    data = get("/schemas")
    check("returns schemas list", isinstance(data.get("schemas"), list))
    check("contains 'main'",      "main" in data.get("schemas", []))


def test_tables():
    print("\n=== /tables ===")
    data = get("/tables")
    tables = data.get("tables", [])
    check("returns tables list",       isinstance(tables, list))
    check("employees table present",   "employees" in tables)
    check("departments table present", "departments" in tables)


def test_describe():
    print("\n=== /describe ===")
    data = get("/describe?table=employees")
    check("table name correct",   data.get("table") == "employees")
    check("row_count is 3",       data.get("row_count") == 3)
    cols = {c["name"]: c for c in data.get("columns", [])}
    check("has 'id' column",      "id" in cols)
    check("has 'name' column",    "name" in cols)
    check("has 'salary' column",  "salary" in cols)
    # SQLite PRAGMA table_info reports notnull=0 for INTEGER PRIMARY KEY
    # (it's implicitly not null but the pragma doesn't flag it), so nullable=True here
    check("name is not nullable", cols.get("name", {}).get("nullable") == False)
    check("salary is nullable",   cols.get("salary", {}).get("nullable") == True)

    print("\n=== /describe — missing table param ===")
    try:
        get("/describe")
        check("returns 400 for missing table", False, "expected error but got 200")
    except urllib.error.HTTPError as e:
        check("returns 400 for missing table", e.code == 400)


def test_search():
    print("\n=== /search ===")
    data = get("/search?q=emp")
    results_list = data.get("results", [])
    check("returns results list",    isinstance(results_list, list))
    check("finds employees table",   any(r["table"] == "employees" for r in results_list))
    check("no departments in 'emp'", not any(r["table"] == "departments" for r in results_list))

    data2 = get("/search?q=dep")
    check("finds departments table", any(r["table"] == "departments" for r in data2.get("results", [])))


def test_query():
    print("\n=== /query — basic SELECT ===")
    status, data = post("/query", {"sql": "SELECT * FROM employees ORDER BY id"})
    check("status 200",            status == 200)
    check("columns present",       "columns" in data)
    check("row_count is 3",        data.get("row_count") == 3)
    check("truncated is false",    data.get("truncated") == False)
    check("first row name=Alice",  data["rows"][0].get("name") == "Alice")

    print("\n=== /query — WHERE filter ===")
    status, data = post("/query", {"sql": "SELECT name, salary FROM employees WHERE dept='Engineering' ORDER BY id"})
    check("status 200",           status == 200)
    check("row_count is 2",       data.get("row_count") == 2)
    check("only Engineering rows", all(r["name"] in ("Alice", "Charlie") for r in data["rows"]))

    print("\n=== /query — aggregate ===")
    status, data = post("/query", {"sql": "SELECT dept, COUNT(*) as cnt FROM employees GROUP BY dept ORDER BY dept"})
    check("status 200",      status == 200)
    check("row_count is 2",  data.get("row_count") == 2)


def test_query_blocked():
    print("\n=== /query — blocked statements ===")
    for stmt in [
        "INSERT INTO employees VALUES (99, 'Eve', 'HR', 50000)",
        "UPDATE employees SET salary=1 WHERE id=1",
        "DELETE FROM employees WHERE id=1",
        "DROP TABLE employees",
        "CREATE TABLE x (id INTEGER)",
    ]:
        status, data = post_expect_error("/query", {"sql": stmt})
        check(f"blocked: {stmt.split()[0]}", status == 403, f"got {status}")

    print("\n=== /query — missing sql key ===")
    status, data = post_expect_error("/query", {"not_sql": "SELECT 1"})
    check("returns 400 for missing sql", status == 400)


def test_not_found():
    print("\n=== 404 for unknown paths ===")
    try:
        get("/nonexistent")
        check("returns 404", False)
    except urllib.error.HTTPError as e:
        check("returns 404", e.code == 404)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Create temp SQLite database
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    create_test_db(db_path)
    print(f"Test DB: {db_path}")

    # Start proxy
    env = {
        **os.environ,
        "DB_TYPE": "sqlite",
        "DB_NAME": db_path,
        "PORT": str(PORT),
    }
    proc = subprocess.Popen(
        [sys.executable, PROXY],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        print(f"Starting proxy on port {PORT}...")
        if not wait_for_proxy():
            out, err = proc.communicate(timeout=2)
            print("Proxy failed to start:")
            print(err.decode())
            sys.exit(1)
        print("Proxy is up.\n")

        test_health()
        test_schemas()
        test_tables()
        test_describe()
        test_search()
        test_query()
        test_query_blocked()
        test_not_found()

    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        os.unlink(db_path)

    # Summary
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        print("\nFailed tests:")
        for name, ok in results:
            if not ok:
                print(f"  - {name}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
