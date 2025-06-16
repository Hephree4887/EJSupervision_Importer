"""Helper functions for executing SQL statements with logging and retries."""

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Generator, List, Optional

from utils.logging_helper import record_success, record_failure

from config import ETLConstants

class ETLError(Exception):
    """Base exception for ETL operations."""


class SQLExecutionError(ETLError):
    """Exception raised when SQL execution fails."""

    def __init__(self, sql: str, original_error: Exception, table_name: Optional[str] = None):
        self.sql = sql
        self.original_error = original_error
        self.table_name = table_name
        msg = f"SQL execution failed for {table_name or 'statement'}: {original_error}"
        super().__init__(msg)

logger = logging.getLogger(__name__)


def log_exception_to_file(error_details: str, log_path: str) -> None:
    """Append exception details to a log file."""
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {error_details}\n")
    except Exception as file_exc:
        logger.error(f"Failed to write to error log file: {file_exc}")


@contextmanager
def transaction_scope(conn: Any) -> Generator[Any, None, None]:
    """Context manager to run a series of statements in a transaction.

    It temporarily disables ``autocommit`` on the provided connection and
    ensures that the connection is committed if the block succeeds or
    rolled back if an exception is raised.  The original ``autocommit``
    setting is restored afterwards.
    """

    original_autocommit = getattr(conn, "autocommit", False)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = original_autocommit
def load_sql(filename: str, db_name: Optional[str] = None) -> str:
    """Load a SQL file from the sql_scripts directory.

    If ``db_name`` is provided, occurrences of the hard coded ``ELPaso_TX``
    database name are replaced with the supplied value so the scripts can run
    against any target database.
    
    Args:
        filename: Path to SQL file relative to sql_scripts directory
        db_name: Database name to replace ELPaso_TX with
        
    Returns:
        SQL content with database name replaced if provided
    """
    base_dir = os.path.dirname(os.path.dirname(__file__)) if '__file__' in globals() else os.getcwd()
    scripts_dir = os.path.join(base_dir, 'sql_scripts')
    # Normalize path to avoid path traversal outside sql_scripts
    sql_path = os.path.abspath(os.path.normpath(os.path.join(scripts_dir, filename)))

    # Ensure the final path is within the expected sql_scripts directory
    scripts_dir_abs = os.path.abspath(scripts_dir)
    if not sql_path.startswith(scripts_dir_abs + os.sep):
        logger.error(f"Attempted SQL path traversal: {filename}")
        raise ValueError(f"Invalid SQL file path: {filename}")

    if not os.path.exists(sql_path):
        logger.error(f"SQL file not found: {sql_path}")
        raise FileNotFoundError(f"SQL file not found: {sql_path}")
    
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    if db_name:
        # Replace both variations of the database name
        sql = sql.replace('ELPaso_TX', db_name)
        sql = sql.replace('ElPaso_TX', db_name)
        sql = sql.replace('ELPASO_TX', db_name)
        logger.debug(f"Replaced database name in {filename} with {db_name}")
    
    return sql
def run_sql_step(
    conn: Any, name: str, sql: str, timeout: int = ETLConstants.DEFAULT_SQL_TIMEOUT
) -> Optional[List[Any]]:
    """Execute a single SQL statement and fetch any results.
    
    Args:
        conn: Database connection
        name: Name of the step for logging
        sql: SQL statement to execute
        timeout: Query timeout in seconds
        
    Returns:
        Query results if any, None otherwise
    """
    logger.info(f"Starting step: {name}")
    start_time = time.time()
    try:
        with conn.cursor() as cursor:
            # Set the query timeout
            cursor.execute(f"SET LOCK_TIMEOUT {timeout * 1000}")  # Convert to milliseconds
            cursor.execute(sql)

            try:
                results = cursor.fetchall()
                logger.info(f"{name}: Retrieved {len(results)} rows")
            except Exception:
                results = None
                logger.info(f"{name}: Statement executed (no results to fetch)")

        elapsed = time.time() - start_time
        logger.info(f"Completed step: {name} in {elapsed:.2f} seconds")
        record_success()
        return results
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Error executing step {name}: {e}. SQL: {sql}")
        logger.info(f"Step {name} failed after {elapsed:.2f} seconds")
        record_failure()
        raise SQLExecutionError(sql, e, table_name=name)


def run_sql_step_with_retry(
    conn: Any,
    name: str,
    sql: str,
    timeout: int = ETLConstants.DEFAULT_SQL_TIMEOUT,
    max_retries: int = ETLConstants.MAX_RETRY_ATTEMPTS,
) -> Optional[List[Any]]:
    """Execute a SQL step with retry logic for transient ``pyodbc.Error`` failures."""

    for attempt in range(max_retries):
        try:
            return run_sql_step(conn, name, sql, timeout)
        except SQLExecutionError as exc:
            import pyodbc  # Imported lazily for tests that stub this module

            if not isinstance(exc.original_error, pyodbc.Error):
                raise

            if attempt == max_retries - 1:
                raise

            if "timeout" in str(exc.original_error).lower():
                logger.warning(
                    f"Timeout on attempt {attempt + 1} for {name}, retrying..."
                )

            time.sleep(2**attempt)
def run_sql_script(
    conn: Any, name: str, sql: str, timeout: int = ETLConstants.DEFAULT_SQL_TIMEOUT
) -> None:
    """Execute a multi-statement SQL script.
    
    Args:
        conn: Database connection
        name: Name of the script for logging
        sql: SQL script containing multiple statements
        timeout: Query timeout in seconds for each statement
    """
    logger.info(f"Starting script: {name}")
    start_time = time.time()
    try:
        with conn.cursor() as cursor:
            # Set the query timeout
            cursor.execute(f"SET LOCK_TIMEOUT {timeout * 1000}")  # Convert to milliseconds

            # Split by GO statements as well as semicolons for SQL Server
            # This handles scripts that use GO as a batch separator
            sql_batches = sql.split('\nGO\n') if '\nGO\n' in sql else [sql]

            total_statements = 0
            for batch in sql_batches:
                statements = [stmt.strip() for stmt in batch.split(';') if stmt.strip()]
                for stmt in statements:
                    # Skip comments and empty statements
                    if stmt and not stmt.strip().startswith('--'):
                        try:
                            cursor.execute(stmt)
                            conn.commit()
                            total_statements += 1
                        except Exception as e:
                            logger.error(f"Error executing script {name}: {e}. SQL: {stmt}")
                            raise SQLExecutionError(stmt, e, table_name=name)

        elapsed = time.time() - start_time
        logger.info(
            f"Completed script: {name} - executed {total_statements} statements in {elapsed:.2f} seconds"
        )
        record_success()
    except SQLExecutionError:
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Error in script {name}: {e}")
        logger.info(f"Script {name} failed after {elapsed:.2f} seconds")
        record_failure()
        raise SQLExecutionError(sql, e, table_name=name)
def execute_sql_with_timeout(
    conn: Any,
    sql: str,
    params: Optional[tuple[Any, ...]] = None,
    timeout: int = ETLConstants.DEFAULT_SQL_TIMEOUT,
) -> Any:
    """Execute SQL with parameters and timeout.
    
    Args:
        conn: Database connection
        sql: SQL statement to execute
        params: Optional tuple of parameters for parameterized query
        timeout: Query timeout in seconds
        
    Returns:
        Cursor after execution
    """
    start_time = time.time()
    with conn.cursor() as cursor:
        try:
            # Set the query timeout
            cursor.execute(f"SET LOCK_TIMEOUT {timeout * 1000}")  # Convert to milliseconds

            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            record_success()
            return cursor
        except Exception as e:
            logger.error(f"Error executing SQL: {e}. SQL: {sql}")
            record_failure()
            raise SQLExecutionError(sql, e)
        finally:
            elapsed = time.time() - start_time
            logger.debug(f"SQL executed in {elapsed:.2f} seconds")
