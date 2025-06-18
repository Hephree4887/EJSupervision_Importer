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

def load_sql(script_path: str, db_name: str = None) -> str:
    """
    Load a SQL script and replace placeholders with dynamic values.
    
    Args:
        script_path: Path to SQL script relative to sql_scripts directory
        db_name: Database name to use for placeholder replacement
    
    Returns:
        SQL content with placeholders replaced
    """
    # Locate the SQL script
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql_dir = os.path.join(base_dir, "sql_scripts")
    full_path = os.path.join(sql_dir, script_path)
    
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"SQL script not found: {full_path}")
    
    # Read the SQL content
    with open(full_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # Replace placeholders if db_name is provided
    if db_name:
        sql_content = sql_content.replace('${DB_NAME}', db_name)
    
    return sql_content

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

            # For SQL Server scripts, handle GO as batch separator
            # Split by GO statements first, then handle individual statements within each batch
            if '\nGO\n' in sql or '\nGO\r\n' in sql or sql.strip().endswith('\nGO') or sql.strip().endswith('\rGO'):
                # Split on GO batch separators
                batches = []
                # Handle different line endings and GO variations
                for sep in ['\nGO\n', '\nGO\r\n', '\rGO\r', '\nGO', '\rGO']:
                    if sep in sql:
                        batches = sql.split(sep)
                        break
                if not batches:
                    batches = [sql]
            else:
                # No GO separators, treat as single batch but split on semicolons
                batches = [sql]

            total_statements = 0
            for batch_idx, batch in enumerate(batches):
                batch = batch.strip()
                if not batch:
                    continue
                    
                logger.debug(f"Executing batch {batch_idx + 1}/{len(batches)}")
                
                # For batches with GO separators, execute the entire batch as one
                if len(batches) > 1 and batch:
                    try:
                        cursor.execute(batch)
                        total_statements += 1
                        logger.debug(f"Executed batch {batch_idx + 1} successfully")
                    except Exception as e:
                        logger.error(f"Error executing batch {batch_idx + 1} in script {name}: {e}")
                        logger.error(f"Batch content: {batch[:200]}...")
                        raise SQLExecutionError(batch, e, table_name=name)
                else:
                    # Split batch on semicolons for individual statements
                    statements = [stmt.strip() for stmt in batch.split(';') if stmt.strip()]
                    for stmt in statements:
                        # Skip comments and empty statements
                        if stmt and not stmt.strip().startswith('--') and not stmt.strip().startswith('/*'):
                            try:
                                cursor.execute(stmt)
                                total_statements += 1
                                logger.debug(f"Executed statement: {stmt[:100]}...")
                            except Exception as e:
                                logger.error(f"Error executing statement in script {name}: {e}")
                                logger.error(f"Statement: {stmt}")
                                raise SQLExecutionError(stmt, e, table_name=name)
            
            # Commit once at the end of the entire script
            conn.commit()

        elapsed = time.time() - start_time
        logger.info(
            f"Completed script: {name} - executed {total_statements} statements in {elapsed:.2f} seconds"
        )
        record_success()
    except SQLExecutionError:
        conn.rollback()  # Rollback on error
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Error in script {name}: {e}")
        logger.info(f"Script {name} failed after {elapsed:.2f} seconds")
        conn.rollback()  # Rollback on error
        record_failure()
        raise SQLExecutionError(sql, e, table_name=name)

def run_sql_script_with_go(
    conn: Any, 
    script_name: str, 
    script: str, 
    timeout: int = ETLConstants.DEFAULT_SQL_TIMEOUT
) -> None:
    """Execute SQL script that contains GO batch separators with proper semicolon handling.
    
    Args:
        conn: Database connection
        script_name: Name of the script for logging
        script: SQL script text with GO separators
        timeout: Query timeout in seconds
    """
    logger.info(f"Starting script: {script_name}")
    start_time = time.time()
    
    try:
        with conn.cursor() as cursor:
            # Set the query timeout
            cursor.execute(f"SET LOCK_TIMEOUT {timeout * 1000}")  # Convert to milliseconds
            
            # Split the script by GO statements (respecting line boundaries)
            import re
            batches = re.split(r'^\s*GO\s*$', script, flags=re.MULTILINE)
            
            batch_count = 0
            for i, batch in enumerate(batches):
                batch = batch.strip()
                if not batch:  # Skip empty batches
                    continue
                
                batch_count += 1
                try:
                    cursor.execute(batch)
                    logger.info(f"Executed batch {i+1}/{len(batches)} in script {script_name}")
                except Exception as e:
                    logger.error(f"Error executing batch {i+1} in script {script_name}: {str(e)}")
                    logger.error(f"Batch content: {batch[:200]}...")
                    raise SQLExecutionError(batch, e, table_name=script_name)
            
            # Commit once at the end of the entire script
            conn.commit()
            
        elapsed = time.time() - start_time
        logger.info(f"Completed script: {script_name} - executed {batch_count} batches in {elapsed:.2f} seconds")
        record_success()
    except SQLExecutionError:
        conn.rollback()  # Rollback on error
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Error in script {script_name}: {e}")
        logger.info(f"Script {script_name} failed after {elapsed:.2f} seconds")
        conn.rollback()  # Rollback on error
        record_failure()
        raise SQLExecutionError(script, e, table_name=script_name)

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
