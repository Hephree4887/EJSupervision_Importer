"""Convenience wrappers for establishing MSSQL connections."""

import pyodbc
from config.settings import MSSQL_SOURCE_CONN_STR, MSSQL_TARGET_CONN_STR

def get_mssql_connection(conn_str):
    """Return a raw ``pyodbc`` connection using the given connection string."""
    return pyodbc.connect(conn_str)

def get_source_connection():
    """Connect to the source MSSQL database configured in settings."""
    return get_mssql_connection(MSSQL_SOURCE_CONN_STR)

def get_target_connection():
    """Connect to the target MSSQL database configured in settings."""
    return get_mssql_connection(MSSQL_TARGET_CONN_STR)

