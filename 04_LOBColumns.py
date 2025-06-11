import logging
import time
import json
import os
import argparse
from dotenv import load_dotenv
import pandas as pd
import urllib
import sqlalchemy
from db.mssql import get_target_connection
from tqdm import tqdm
from sqlalchemy.types import Text
import tkinter as tk
from tkinter import messagebox
from config import settings

from utils.etl_helpers import (
    log_exception_to_file,
    load_sql,
    run_sql_step,
    run_sql_script,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

DEFAULT_LOG_FILE = "PreDMSErrorLog_LOBS.txt"

# Database name used within the dynamic SQL statements
DB_NAME = settings.MSSQL_TARGET_DB_NAME or settings._parse_database_name(settings.MSSQL_TARGET_CONN_STR)

def parse_args():
    """Parse command line arguments for the LOB Column processing script."""
    parser = argparse.ArgumentParser(description="LOB Column Processing")
    parser.add_argument(
        "--log-file",
        help="Path to the error log file. Overrides the EJ_LOG_DIR environment variable."
    )
    parser.add_argument(
        "--include-empty", 
        action="store_true",
        help="Include empty tables in the LOB column processing."
    )
    parser.add_argument(
        "--config-file",
        help="Path to JSON configuration file with all settings."
    )
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true",
        help="Enable verbose logging."
    )
    return parser.parse_args()

def validate_environment():
    """Validate required environment variables and their values."""
    required_vars = {
        'MSSQL_TARGET_CONN_STR': "Database connection string is required",
    }
    
    optional_vars = {
        'EJ_LOG_DIR': "Directory for log files (defaults to current directory)",
        'INCLUDE_EMPTY_TABLES': "Set to '1' to include empty tables (defaults to '0')",
        'SQL_TIMEOUT': "Timeout in seconds for SQL operations (defaults to 300)"
    }
    
    # Check required vars
    missing = []
    for var, desc in required_vars.items():
        if not os.environ.get(var):
            missing.append(f"{var}: {desc}")
    
    if missing:
        raise EnvironmentError(f"Missing required environment variables:\n" + 
                              "\n".join(missing))
    
    # Log optional vars
    for var, desc in optional_vars.items():
        value = os.environ.get(var)
        if value:
            logger.info(f"Using {var}={value}")
        else:
            logger.info(f"{var} not set. {desc}")

def load_config(config_file=None):
    """Load configuration from JSON file if provided, otherwise use defaults."""
    config = {
        "include_empty_tables": False,
        "log_filename": DEFAULT_LOG_FILE,
        "sql_timeout": 300,  # seconds
    }
    
    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
            logger.info(f"Loaded configuration from {config_file}")
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
    
    return config

def get_max_length(conn, schema, table, column, datatype, timeout=300):
    """Determine the maximum length needed for a text/varchar column."""
    cursor = conn.cursor()
    try:
        if datatype.lower() in ('varchar', 'nvarchar'):
            sql = f"SELECT MAX(LEN([{column}])) FROM [{schema}].[{table}]"
        elif datatype.lower() in ('text', 'ntext'):
            # For text/ntext, cast to nvarchar(max) for LEN
            sql = f"SELECT MAX(LEN(CAST([{column}] AS NVARCHAR(MAX)))) FROM [{schema}].[{table}]"
        else:
            return None
        
        cursor.execute(sql, timeout=timeout)
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else 0
    except Exception as e:
        logger.error(f"Error getting max length for {schema}.{table}.{column}: {e}")
        return None
    finally:
        cursor.close()

def build_alter_column_sql(schema, table, column, datatype, max_length):
    """Build the SQL statement to alter a column based on its max length."""
    if max_length is None or max_length == 0:
        return f"ALTER TABLE [{schema}].[{table}] ALTER COLUMN [{column}] CHAR(1) NULL"
    elif max_length > 8000:
        return f"ALTER TABLE [{schema}].[{table}] ALTER COLUMN [{column}] TEXT NULL"
    else:
        return f"ALTER TABLE [{schema}].[{table}] ALTER COLUMN [{column}] VARCHAR({max_length}) NULL"

def create_lob_tracking_table(conn, config):
    """Create the table to track LOB column updates."""
    logger.info("Creating LOB_COLUMN_UPDATES tracking table")
    gather_lobs_sql = load_sql('lob/gather_lobs.sql', DB_NAME)
    run_sql_script(conn, 'gather_lobs', gather_lobs_sql, timeout=config['sql_timeout'])
    logger.info("LOB tracking table created successfully")

def gather_lob_columns(conn, config, log_file):
    """Gather information about LOB columns and determine optimal sizes."""
    logger.info("Gathering information about LOB columns")
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            s.[NAME] AS SchemaName,
            t.[NAME] AS TableName,
            c.[NAME] AS ColumnName,
            TYPE_NAME(c.user_type_id) AS DataType,
            CASE WHEN TYPE_NAME(c.user_type_id) IN ('varchar', 'nvarchar') 
                 THEN c.max_length ELSE NULL END AS CurrentLength,
            (SELECT COUNT(*) FROM sys.objects o WHERE o.object_id=t.object_id) AS RowCnt
        FROM {DB_NAME}.sys.tables t
        INNER JOIN {DB_NAME}.sys.schemas s ON t.schema_id=s.schema_id
        INNER JOIN {DB_NAME}.sys.columns c ON t.object_id=c.object_id
        WHERE t.[NAME] NOT IN (
            'SupContact','CaseEvent','TablesToConvert',
            'TablesToConvert_Financial','TablesToConvert_Operations'
        ) 
        AND (
            TYPE_NAME(c.user_type_id) IN ('text', 'ntext') 
            OR (TYPE_NAME(c.user_type_id) IN ('varchar', 'nvarchar') 
                AND (c.max_length > 5000 OR c.max_length=-1))
        )
        ORDER BY s.[NAME], t.[NAME], c.[NAME]
    """, timeout=config['sql_timeout'])
    
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    update_cursor = conn.cursor()
    for idx, row in enumerate(tqdm(rows, desc="Analyzing LOB Columns", unit="column"), 1):
        row_dict = dict(zip(columns, row))
        schema_name = row_dict.get('SchemaName')
        table_name = row_dict.get('TableName')
        column_name = row_dict.get('ColumnName')
        datatype = row_dict.get('DataType')
        row_cnt = row_dict.get('RowCnt') or 0

        if not config['include_empty_tables'] and row_cnt <= 0:
            logger.info(f"Skipping {schema_name}.{table_name}.{column_name}: row count is {row_cnt}")
            continue

        try:
            max_length = get_max_length(conn, schema_name, table_name, column_name, datatype, config['sql_timeout'])
            alter_column_sql = build_alter_column_sql(schema_name, table_name, column_name, datatype, max_length)
            
            insert_sql = f"""
                INSERT INTO {DB_NAME}.dbo.LOB_COLUMN_UPDATES
                (SchemaName, TableName, ColumnName, DataType, CurrentLength, RowCnt, MaxLen, AlterStatement)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            update_cursor.execute(
                insert_sql,
                (
                    schema_name,
                    table_name,
                    column_name,
                    datatype,
                    row_dict.get('CurrentLength'),
                    row_cnt,
                    max_length,
                    alter_column_sql
                ),
                timeout=config['sql_timeout']
            )
            conn.commit()
            
        except Exception as e:
            error_msg = f"Error processing LOB column {schema_name}.{table_name}.{column_name}: {e}"
            logger.error(error_msg)
            log_exception_to_file(error_msg, log_file)
    
    update_cursor.close()
    cursor.close()
    logger.info(f"Analyzed and cataloged {len(rows)} LOB columns")

def execute_lob_column_updates(conn, config, log_file):
    """Execute the ALTER statements to optimize LOB columns."""
    logger.info("Executing ALTER TABLE statements for LOB columns")
    
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT REPLACE(S.ALTERSTATEMENT,' NULL',';') AS Alter_Statement
        FROM {DB_NAME}.dbo.LOB_COLUMN_UPDATES S
        WHERE S.TABLENAME NOT LIKE '%LOB_COL%'
        ORDER BY S.MAXLEN DESC
    """, timeout=config['sql_timeout'])
    
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    for idx, row in enumerate(tqdm(rows, desc="Optimizing LOB Columns", unit="column"), 1):
        row_dict = dict(zip(columns, row))
        alter_sql = row_dict.get('Alter_Statement')
        
        if alter_sql:
            try:
                run_sql_step(conn, f"Alter Column {idx}", alter_sql, timeout=config['sql_timeout'])
                conn.commit()
            except Exception as e:
                error_msg = f"Failed to alter column (statement {idx}): {e}"
                logger.error(error_msg)
                log_exception_to_file(error_msg, log_file)
    
    cursor.close()
    logger.info(f"Completed optimizing {len(rows)} LOB columns")

def show_completion_message():
    """Show a message box indicating completion."""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    proceed = messagebox.askyesno(
        "LOB Column Processing Complete",
        "LOB column optimization is complete.\n\n"
        "The database is now ready for transfer to AWS DMS.\n\n"
        "Click Yes to exit."
    )
    root.destroy()
    return proceed

def main():
    try:
        # Initialize configuration
        args = parse_args()
        load_dotenv()
        validate_environment()
        
        # Set up logging level
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Load and merge configuration
        config = load_config(args.config_file)
        
        # Override config with environment variables
        if os.environ.get("INCLUDE_EMPTY_TABLES") == "1":
            config["include_empty_tables"] = True
        if os.environ.get("SQL_TIMEOUT"):
            config["sql_timeout"] = int(os.environ.get("SQL_TIMEOUT"))
        
        # Override config with command line arguments
        if args.include_empty:
            config["include_empty_tables"] = True
        
        # Set up log file path
        config['log_file'] = args.log_file or os.path.join(
            os.environ.get("EJ_LOG_DIR", ""), 
            config["log_filename"]
        )
        
        logger.info(f"Using configuration: {json.dumps(config, indent=2)}")
        
        # Begin database operations
        try:
            with get_target_connection() as conn:
                # Step 1: Create tracking table for LOB columns
                create_lob_tracking_table(conn, config)
                
                # Step 2: Gather LOB column information
                gather_lob_columns(conn, config, config['log_file'])
                
                # Step 3: Execute column alterations
                execute_lob_column_updates(conn, config, config['log_file'])
                
                # Step 4: Show completion message
                show_completion_message()
                
        except Exception as e:
            logger.exception("Unexpected error during database operations")
            raise e
                
    except Exception as e:
        logger.exception("Unexpected error")
        import traceback
        error_details = traceback.format_exc()
        
        # Try to log the error to file
        try:
            log_file = config.get('log_file', DEFAULT_LOG_FILE)
            log_exception_to_file(error_details, log_file)
        except Exception as log_exc:
            logger.error(f"Failed to write to error log: {log_exc}")
        
        # Try to show error message box
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("ETL Script Error", f"An error occurred:\n\n{error_details}")
            root.destroy()
        except Exception as msgbox_exc:
            logger.error(f"Failed to show error message box: {msgbox_exc}")

if __name__ == "__main__":
    main()