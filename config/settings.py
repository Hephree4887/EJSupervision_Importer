import os
from dotenv import load_dotenv
from typing import Optional  # Add this import


# Load environment variables from a .env file if present. This only needs to
# happen once so we do it at import time before reading any variables.
load_dotenv()

MSSQL_SOURCE_CONN_STR = os.getenv("MSSQL_SOURCE_CONN_STR")
MSSQL_TARGET_CONN_STR = os.getenv("MSSQL_TARGET_CONN_STR")

# Utility to pull the database name out of a connection string like
# "DRIVER=...;SERVER=...;DATABASE=MyDB;UID=user;PWD=pass".
def _parse_database_name(conn_str: str) -> Optional[str]:
    if not conn_str:
        return None
    for part in conn_str.split(';'):
        if part.lower().startswith('database='):
            return part.split('=', 1)[1]
    return None

# Allow overriding the target database name explicitly or derive it from the
# connection string provided by the user.
MSSQL_TARGET_DB_NAME = os.getenv("MSSQL_TARGET_DB_NAME") or _parse_database_name(MSSQL_TARGET_CONN_STR)
MYSQL_CONN_DICT = {
    'host': os.getenv("MYSQL_HOST"),
    'user': os.getenv("MYSQL_USER"),
    'password': os.getenv("MYSQL_PASSWORD"),
    'database': os.getenv("MYSQL_DATABASE"),
}


class ETLConstants:
    """Default values used across the ETL pipeline."""

    #: Default timeout for SQL statements in seconds
    DEFAULT_SQL_TIMEOUT = 300

    #: Default number of rows to insert per batch when doing bulk inserts
    DEFAULT_BULK_INSERT_BATCH_SIZE = 100

    #: Maximum number of retry attempts for transient failures
    MAX_RETRY_ATTEMPTS = 3

    #: Default connection timeout when establishing database connections
    CONNECTION_TIMEOUT = 30

