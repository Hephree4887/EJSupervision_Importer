import sys, types
if "mysql" not in sys.modules:
    dummy_mysql = types.ModuleType("mysql")
    dummy_mysql.connector = types.SimpleNamespace(connect=lambda **k: None)
    sys.modules["mysql"] = dummy_mysql
    sys.modules["mysql.connector"] = dummy_mysql.connector
if "dotenv" not in sys.modules:
    mod=types.ModuleType("dotenv")
    mod.load_dotenv=lambda *a, **k: None
    sys.modules["dotenv"] = mod
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = types.SimpleNamespace(connect=lambda *a, **k: None)
import db.mssql as mssql

class DummyConn:
    pass

def test_get_target_connection(monkeypatch):
    conn_str = 'DRIVER=SQL;SERVER=server;DATABASE=db;'

    def fake_connect(arg):
        assert arg == conn_str
        return DummyConn()

    monkeypatch.setattr(mssql, 'MSSQL_TARGET_CONN_STR', conn_str)
    monkeypatch.setattr(mssql.pyodbc, 'connect', fake_connect)

    conn = mssql.get_target_connection()
    assert isinstance(conn, DummyConn)
