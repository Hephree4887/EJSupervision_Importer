import pytest
import sys, types

if "pyodbc" not in sys.modules:
    class _DummyError(Exception):
        pass
    sys.modules["pyodbc"] = types.SimpleNamespace(
        Error=_DummyError, connect=lambda *a, **k: None
    )

if "dotenv" not in sys.modules:
    mod = types.ModuleType("dotenv")
    mod.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = mod

from config import ETLConstants
from utils.etl_helpers import (
    run_sql_step,
    run_sql_script,
    run_sql_step_with_retry,
    SQLExecutionError,
)

class DummyCursor:
    def __init__(self, fail=False, fail_sql=None, conn=None):
        self.fail = fail
        self.fail_sql = fail_sql
        self.conn = conn
    def execute(self, sql, params=None):
        if 'SET LOCK_TIMEOUT' in sql:
            return
        if (
            self.fail
            or (self.fail_sql and sql.strip() == self.fail_sql)
            or (self.conn and self.conn.fail_times > 0)
        ):
            if self.conn and self.conn.fail_times > 0:
                self.conn.fail_times -= 1
            raise sys.modules["pyodbc"].Error("boom")
    def fetchall(self):
        return [('row',)]
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        pass

class DummyConn:
    def __init__(self, fail=False, fail_sql=None, fail_times=0):
        self.fail = fail
        self.fail_sql = fail_sql
        self.fail_times = fail_times

    def cursor(self):
        return DummyCursor(self.fail, self.fail_sql, conn=self)
    def commit(self):
        pass


def test_run_sql_step_success():
    conn = DummyConn()
    result = run_sql_step(conn, 'test', 'SELECT 1')
    assert result == [('row',)]


def test_run_sql_step_failure():
    conn = DummyConn(fail=True)
    with pytest.raises(SQLExecutionError) as exc:
        run_sql_step(conn, 'table', 'SELECT 1')
    assert exc.value.sql == 'SELECT 1'
    assert exc.value.table_name == 'table'


def test_run_sql_script_failure():
    sql = 'SELECT 1; FAIL; SELECT 2'
    conn = DummyConn(fail_sql='FAIL')
    with pytest.raises(SQLExecutionError) as exc:
        run_sql_script(conn, 'table', sql)
    assert exc.value.sql.strip() == 'FAIL'
    assert exc.value.table_name == 'table'


def test_run_sql_step_with_retry_success():
    conn = DummyConn()
    result = run_sql_step_with_retry(conn, 'test', 'SELECT 1')
    assert result == [('row',)]


def test_run_sql_step_with_retry_retries(monkeypatch):
    conn = DummyConn(fail_times=2)
    result = run_sql_step_with_retry(
        conn, 'test', 'SELECT 1', max_retries=ETLConstants.MAX_RETRY_ATTEMPTS
    )
    assert result == [('row',)]
