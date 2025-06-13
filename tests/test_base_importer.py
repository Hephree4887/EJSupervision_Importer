import os
import pytest
import sys, types

if "tqdm" not in sys.modules:
    dummy = types.ModuleType("tqdm")
    def _tqdm(iterable, **kwargs):
        for item in iterable:
            yield item
    dummy.tqdm = _tqdm
    sys.modules["tqdm"] = dummy

if "pandas" not in sys.modules:
    sys.modules["pandas"] = types.ModuleType("pandas")

if "sqlalchemy" not in sys.modules:
    sa_mod = types.ModuleType("sqlalchemy")
    types_mod = types.SimpleNamespace(Text=lambda *a, **k: None)
    sa_mod.types = types_mod
    sys.modules["sqlalchemy"] = sa_mod
    sys.modules["sqlalchemy.types"] = types_mod

if "pyodbc" not in sys.modules:
    class _DummyError(Exception):
        pass
    sys.modules["pyodbc"] = types.SimpleNamespace(
        Error=_DummyError, connect=lambda *a, **k: None
    )

if "mysql" not in sys.modules:
    dummy_mysql = types.ModuleType("mysql")
    dummy_mysql.connector = types.SimpleNamespace(connect=lambda **k: None)
    sys.modules["mysql"] = dummy_mysql
    sys.modules["mysql.connector"] = dummy_mysql.connector

if "dotenv" not in sys.modules:
    mod = types.ModuleType("dotenv")
    mod.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = mod

from etl.base_importer import BaseDBImporter


def test_validate_environment_missing_all(monkeypatch):
    monkeypatch.delenv('MSSQL_TARGET_CONN_STR', raising=False)
    monkeypatch.delenv('EJ_CSV_DIR', raising=False)
    with pytest.raises(EnvironmentError):
        BaseDBImporter().validate_environment()


def test_validate_environment_missing_csv_dir(monkeypatch):
    monkeypatch.setenv('MSSQL_TARGET_CONN_STR', 'Driver=SQL;Server=.;Database=db;')
    monkeypatch.delenv('EJ_CSV_DIR', raising=False)
    with pytest.raises(EnvironmentError):
        BaseDBImporter().validate_environment()
