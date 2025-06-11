"""Configuration settings for database connections."""

from .settings import (
    MSSQL_SOURCE_CONN_STR,
    MSSQL_TARGET_CONN_STR,
    MYSQL_CONN_DICT,
)

__all__ = [
    "MSSQL_SOURCE_CONN_STR",
    "MSSQL_TARGET_CONN_STR",
    "MYSQL_CONN_DICT",
]
