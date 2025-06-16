import os
import pytest
import sys, types
import argparse

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


def test_load_config_env_and_args(monkeypatch, tmp_path):
    monkeypatch.setenv('MSSQL_TARGET_CONN_STR', 'Driver=SQL;Server=.;Database=db;')
    monkeypatch.setenv('EJ_CSV_DIR', str(tmp_path))
    monkeypatch.setenv('EJ_LOG_DIR', str(tmp_path))
    monkeypatch.setenv('SQL_TIMEOUT', '200')
    monkeypatch.setenv('INCLUDE_EMPTY_TABLES', '1')

    args = argparse.Namespace(
        log_file=None,
        csv_file=None,
        include_empty=False,
        skip_pk_creation=True,
        config_file=None,
        verbose=False,
    )

    importer = BaseDBImporter()
    importer.load_config(args)

    assert importer.config['include_empty_tables'] is True
    assert importer.config['skip_pk_creation'] is True
    assert importer.config['sql_timeout'] == 200
    assert importer.config['csv_file'].endswith(importer.DEFAULT_CSV_FILE)
    assert importer.config['log_file'].endswith(importer.DEFAULT_LOG_FILE)


def test_show_completion_message(monkeypatch):
    importer = BaseDBImporter()

    dummy_tk = types.SimpleNamespace(withdraw=lambda: None, destroy=lambda: None)
    monkeypatch.setattr('etl.base_importer.tk.Tk', lambda: dummy_tk)
    monkeypatch.setattr('etl.base_importer.messagebox.askyesno', lambda *a, **k: True)

    assert importer.show_completion_message('Next') is True

    info_called = {}
    monkeypatch.setattr('etl.base_importer.messagebox.showinfo', lambda *a, **k: info_called.setdefault('called', True))
    assert importer.show_completion_message(None) is False
    assert info_called.get('called')
