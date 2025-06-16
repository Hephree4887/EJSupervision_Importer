"""Basic end-to-end integration test for a database importer."""

import sqlite3
import argparse
import sys
import types

# Stub heavy optional dependencies if they are missing.  This mirrors the
# approach used in the unit tests for the other modules.
if "pandas" not in sys.modules:
    sys.modules["pandas"] = types.ModuleType("pandas")
if "sqlalchemy" not in sys.modules:
    sa_mod = types.ModuleType("sqlalchemy")
    sa_mod.types = types.SimpleNamespace(Text=lambda *a, **k: None)
    sys.modules["sqlalchemy"] = sa_mod
    sys.modules["sqlalchemy.types"] = sa_mod.types
if "tqdm" not in sys.modules:
    dummy = types.ModuleType("tqdm")
    dummy.tqdm = lambda it, **kw: it
    sys.modules["tqdm"] = dummy
if "pyodbc" not in sys.modules:
    class _DummyError(Exception):
        pass
    sys.modules["pyodbc"] = types.SimpleNamespace(Error=_DummyError)
if "dotenv" not in sys.modules:
    mod = types.ModuleType("dotenv")
    mod.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = mod
if "mysql" not in sys.modules:
    dummy_mysql = types.ModuleType("mysql")
    dummy_mysql.connector = types.SimpleNamespace(connect=lambda **k: None)
    sys.modules["mysql"] = dummy_mysql
    sys.modules["mysql.connector"] = dummy_mysql.connector

from etl.base_importer import BaseDBImporter
import db.mssql as mssql


class MiniImporter(BaseDBImporter):
    """Very small importer used for testing the run() workflow."""

    DB_TYPE = "Mini"
    DEFAULT_LOG_FILE = "mini.log"

    def parse_args(self):
        """Return a dummy args namespace expected by ``BaseDBImporter``."""
        return argparse.Namespace(
            log_file=None,
            csv_file=None,
            include_empty=False,
            skip_pk_creation=False,
            config_file=None,
            verbose=False,
        )

    # The following hooks implement a trivial workflow that simply creates
    # and populates a table in the temporary database.  All other optional
    # steps are skipped by overriding with no-op implementations.
    def execute_preprocessing(self, conn):
        conn.execute("CREATE TABLE numbers (id INTEGER PRIMARY KEY, num INTEGER)")

    def prepare_drop_and_select(self, conn):
        pass

    def update_joins_in_tables(self, conn):
        pass

    def execute_table_operations(self, conn):
        conn.executemany(
            "INSERT INTO numbers(num) VALUES (?)",
            [(1,), (2,)],
        )

    def import_joins(self):  # pragma: no cover - not needed for this test
        pass

    def create_primary_keys(self, conn):  # pragma: no cover - PK already set
        pass

    def get_next_step_name(self):
        return None

    def show_completion_message(self, next_step_name=None):  # pragma: no cover
        return False


def test_end_to_end_mini_importer(monkeypatch, tmp_path):
    """Run the ``MiniImporter`` using an in-memory SQLite database."""

    # Provide required environment variables for ``validate_environment``.
    monkeypatch.setenv("MSSQL_TARGET_CONN_STR", "Driver=SQLite;Database=:memory:")
    monkeypatch.setenv("EJ_CSV_DIR", str(tmp_path))
    monkeypatch.setenv("EJ_LOG_DIR", str(tmp_path))

    # Use an in-memory SQLite database instead of MSSQL.
    conn = sqlite3.connect(":memory:")

    # Patch the connection retrieval used inside BaseDBImporter
    monkeypatch.setattr(mssql, "get_target_connection", lambda: conn)
    monkeypatch.setattr("etl.base_importer.get_target_connection", lambda: conn)

    importer = MiniImporter()

    # ``run`` should complete successfully and return ``False`` since our
    # ``show_completion_message`` always opts not to continue.
    assert importer.run() is False

    # Verify the table was created and populated.
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM numbers")
    count = cur.fetchone()[0]
    cur.close()
    assert count == 2

    # Explicitly close the connection to release resources.
    conn.close()

