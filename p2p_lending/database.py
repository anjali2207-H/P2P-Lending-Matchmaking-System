"""Database helper functions (SQLite)."""
import os
import sqlite3
import config


def get_connection(db_path=None):
    db_path = db_path or config.DATABASE_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")   # must be enabled on every connection
    return conn


def init_db(db_path=None):
    """Create all tables from schema.sql (safe to run more than once)."""
    schema_file = os.path.join(config.BASE_DIR, "schema.sql")
    with open(schema_file, "r", encoding="utf-8") as f:
        script = f.read()
    conn = get_connection(db_path)
    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()


def list_tables(db_path=None):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Database created at:", config.DATABASE_PATH)
    print("Tables:", ", ".join(list_tables()))
