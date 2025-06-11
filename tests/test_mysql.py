import sys, types
if "dotenv" not in sys.modules:
    mod=types.ModuleType("dotenv")
    mod.load_dotenv=lambda *a, **k: None
    sys.modules["dotenv"] = mod
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = types.SimpleNamespace(connect=lambda *a, **k: None)
if "mysql" not in sys.modules:
    dummy_mysql = types.ModuleType("mysql")
    dummy_mysql.connector = types.SimpleNamespace(connect=lambda **k: None)
    sys.modules["mysql"] = dummy_mysql
    sys.modules["mysql.connector"] = dummy_mysql.connector

import pytest

import db.mysql as mysql

class DummyConn:
    pass

def test_get_mysql_connection_env(monkeypatch):
    monkeypatch.setenv('MYSQL_HOST', 'localhost')
    monkeypatch.setenv('MYSQL_USER', 'user')
    monkeypatch.setenv('MYSQL_PASSWORD', 'pass')
    monkeypatch.setenv('MYSQL_DATABASE', 'db')
    monkeypatch.setenv('MYSQL_PORT', '3307')

    called = {}
    def fake_connect(**kwargs):
        called['kwargs'] = kwargs
        return DummyConn()

    monkeypatch.setattr(mysql.mysql.connector, 'connect', fake_connect)

    conn = mysql.get_mysql_connection()
    assert isinstance(conn, DummyConn)
    assert called['kwargs'] == {
        'host': 'localhost',
        'user': 'user',
        'password': 'pass',
        'database': 'db',
        'port': 3307,
    }


def test_get_mysql_connection_missing(monkeypatch):
    monkeypatch.delenv('MYSQL_HOST', raising=False)
    monkeypatch.delenv('MYSQL_USER', raising=False)
    monkeypatch.delenv('MYSQL_PASSWORD', raising=False)
    monkeypatch.delenv('MYSQL_DATABASE', raising=False)

    with pytest.raises(ValueError):
        mysql.get_mysql_connection()
