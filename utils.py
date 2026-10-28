"""Small helpers shared by the Flask routes."""
from contextlib import contextmanager
from database import get_connection


@contextmanager
def db_conn():
    """Open a database connection for one request and always close it."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
