import pyodbc
from config.settings import MSSQL_SOURCE_CONN_STR, MSSQL_TARGET_CONN_STR

def get_mssql_connection(conn_str):
    return pyodbc.connect(conn_str)

def get_source_connection():
    return get_mssql_connection(MSSQL_SOURCE_CONN_STR)

def get_target_connection():
    return get_mssql_connection(MSSQL_TARGET_CONN_STR)

