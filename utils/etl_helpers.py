import logging
import os
import time

logger = logging.getLogger(__name__)


def log_exception_to_file(error_details: str, log_path: str):
    """Append exception details to a log file."""
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(error_details + "\n")
    except Exception as file_exc:
        logger.error(f"Failed to write to error log file: {file_exc}")
def load_sql(filename: str, db_name: str | None = None) -> str:
    """Load a SQL file from the sql_scripts directory.

    If ``db_name`` is provided, occurrences of the hard coded ``ELPaso_TX``
    database name are replaced with the supplied value so the scripts can run
    against any target database.
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
        sql = sql.replace('ELPaso_TX', db_name).replace('ElPaso_TX', db_name)
    return sql
def run_sql_step(conn, name: str, sql: str):
    """Execute a single SQL statement and fetch any results."""
    logger.info(f"Starting step: {name}")
    start_time = time.time()
    try:
        cursor = conn.cursor()
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
def run_sql_script(conn, name: str, sql: str):
    """Execute a multi-statement SQL script."""
    logger.info(f"Starting script: {name}")
    start_time = time.time()
    try:
        cursor = conn.cursor()
        statements = [stmt.strip() for stmt in sql.split(';') if stmt.strip()]
        for stmt in statements:
            cursor.execute(stmt)
            conn.commit()
        cursor.close()
        elapsed = time.time() - start_time
        logger.info(f"Completed script: {name} in {elapsed:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in script {name}: {str(e)}")
        raise
