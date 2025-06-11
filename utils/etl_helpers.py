import logging
import os
import time
from typing import Optional, Any, List

logger = logging.getLogger(__name__)


def log_exception_to_file(error_details: str, log_path: str):
    """Append exception details to a log file."""
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {error_details}\n")
    except Exception as file_exc:
        logger.error(f"Failed to write to error log file: {file_exc}")
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
    # The sql_scripts directory lives at the repo root
    sql_path = os.path.join(base_dir, 'sql_scripts', filename)
    if not os.path.exists(sql_path):
        logger.error(f"SQL file not found: {sql_path}")
        raise FileNotFoundError(f"SQL file not found: {sql_path}")
    
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    if db_name:
        # Replace both variations of the database name
        sql = sql.replace('ELPaso_TX', db_name).replace('ElPaso_TX', db_name)
        logger.debug(f"Replaced database name in {filename} with {db_name}")
    
    return sql
def run_sql_step(conn, name: str, sql: str, timeout: int = 300) -> Optional[List[Any]]:
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
        cursor = conn.cursor()
        # Set the query timeout
        cursor.execute(f"SET LOCK_TIMEOUT {timeout * 1000}")  # Convert to milliseconds
        cursor.execute(sql)
        
        try:
            results = cursor.fetchall()
            logger.info(f"{name}: Retrieved {len(results)} rows")
        except Exception:
            results = None
            logger.info(f"{name}: Statement executed (no results to fetch)")
        
        cursor.close()
        elapsed = time.time() - start_time
        logger.info(f"Completed step: {name} in {elapsed:.2f} seconds")
        return results
    except Exception as e:
        logger.error(f"Error in step {name}: {str(e)}")
        raise
def run_sql_script(conn, name: str, sql: str, timeout: int = 300):
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
        cursor = conn.cursor()
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
                    cursor.execute(stmt)
                    conn.commit()
                    total_statements += 1
        
        cursor.close()
        elapsed = time.time() - start_time
        logger.info(f"Completed script: {name} - executed {total_statements} statements in {elapsed:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in script {name}: {str(e)}")
        raise
def execute_sql_with_timeout(conn, sql: str, params: Optional[tuple] = None, timeout: int = 300) -> Any:
    """Execute SQL with parameters and timeout.
    
    Args:
        conn: Database connection
        sql: SQL statement to execute
        params: Optional tuple of parameters for parameterized query
        timeout: Query timeout in seconds
        
    Returns:
        Cursor after execution
    """
    cursor = conn.cursor()
    try:
        # Set the query timeout
        cursor.execute(f"SET LOCK_TIMEOUT {timeout * 1000}")  # Convert to milliseconds
        
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        
        return cursor
    except Exception:
        cursor.close()
        raise