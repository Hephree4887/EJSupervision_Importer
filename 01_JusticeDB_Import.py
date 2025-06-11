import logging
import time
import json
import sys
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

DEFAULT_LOG_FILE = "PreDMSErrorLog_Justice.txt"

# Determine the target database name from environment variables/connection
# string. This value replaces the hard coded 'ELPaso_TX' references in the SQL
# scripts so the ETL can run against any target database.
DB_NAME = settings.MSSQL_TARGET_DB_NAME or settings._parse_database_name(settings.MSSQL_TARGET_CONN_STR)

def parse_args():
    """Parse command line arguments for the Justice DB import script."""
    parser = argparse.ArgumentParser(description="Justice DB Import ETL Process")
    parser.add_argument(
        "--log-file",
        help="Path to the error log file. Overrides the EJ_LOG_DIR environment variable."
    )
    parser.add_argument(
        "--csv-file",
        help="Path to the Justice Selects CSV file. Overrides the EJ_CSV_DIR environment variable."
    )
    parser.add_argument(
        "--include-empty", 
        action="store_true",
        help="Include empty tables in the migration process."
    )
    parser.add_argument(
        "--skip-pk-creation", 
        action="store_true",
        help="Skip primary key and constraint creation step."
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
        'EJ_CSV_DIR': "Directory containing ETL CSV files is required"
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
            
    # Validate paths
    csv_dir = os.environ.get('EJ_CSV_DIR')
    if not os.path.exists(csv_dir):
        raise EnvironmentError(f"EJ_CSV_DIR path does not exist: {csv_dir}")
def load_config(config_file=None):
    """Load configuration from JSON file if provided, otherwise use defaults."""
    config = {
        "include_empty_tables": False,
        "csv_filename": "EJ_Justice_Selects_ALL.csv",
        "log_filename": DEFAULT_LOG_FILE,
        "skip_pk_creation": False,
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
def define_supervision_scope(conn, config):
    """Run SQL scripts to define supervision scope."""
    logger.info("Defining supervision scope...")
    steps = [
        {'name': 'GatherCaseIDs', 'sql': load_sql('justice/gather_caseids.sql', DB_NAME)},
        {'name': 'GatherChargeIDs', 'sql': load_sql('justice/gather_chargeids.sql', DB_NAME)},
        {'name': 'GatherPartyIDs', 'sql': load_sql('justice/gather_partyids.sql', DB_NAME)},
        {'name': 'GatherWarrantIDs', 'sql': load_sql('justice/gather_warrantids.sql', DB_NAME)},
        {'name': 'GatherHearingIDs', 'sql': load_sql('justice/gather_hearingids.sql', DB_NAME)},
        {'name': 'GatherEventIDs', 'sql': load_sql('justice/gather_eventids.sql', DB_NAME)}
    ]
    
    for step in safe_tqdm(steps, desc="SQL Script Progress", unit="step"):
        run_sql_step(conn, step['name'], step['sql'], timeout=config['sql_timeout'])
        conn.commit()
    
    logger.info("All Staging steps completed successfully. Supervision Scope Defined.")
def prepare_drop_and_select(conn, config):
    """Prepare SQL statements for dropping and selecting data."""
    logger.info("Gathering list of Justice tables with SQL Commands to be migrated.")
    additional_sql = load_sql('justice/gather_drops_and_selects.sql', DB_NAME)
    run_sql_script(conn, 'gather_drops_and_selects', additional_sql, timeout=config['sql_timeout'])
def import_joins(config, log_file):
    """Import JOIN statements from CSV to build selection queries."""
    logger.info("Importing JOINS from Justice Selects CSV")
    
    # Set up database connection for pandas
    conn_str = os.environ['MSSQL_TARGET_CONN_STR']
    params = urllib.parse.quote_plus(conn_str)
    db_url = f"mssql+pyodbc:///?odbc_connect={params}"
    engine = sqlalchemy.create_engine(db_url)
    
    # Get CSV path from config
    csv_path = config.get('csv_file') or os.path.join(
        os.environ.get('EJ_CSV_DIR', ''),
        config['csv_filename']
    )
    
    if not os.path.exists(csv_path):
        error_msg = f"CSV file not found: {csv_path}"
        logger.error(error_msg)
        log_exception_to_file(error_msg, log_file)
        raise FileNotFoundError(error_msg)
    
    # Read and import CSV
    df = pd.read_csv(csv_path, delimiter='|')
    df = df.astype({
        'DatabaseName': 'str', 'SchemaName': 'str', 'TableName': 'str',
        'Freq': 'str', 'InScopeFreq': 'str', 'Select_Only': 'str',
        'fConvert': 'str', 'Drop_IfExists': 'str', 'Selection': 'str',
        'Select_Into': 'str'
    })
    
    # Write to SQL table
    df.to_sql(
        'TableUsedSelects',
        con=engine,
        if_exists='replace',
        index=False,
        dtype={'Select_Into': Text(), 'Drop_IfExists': Text()}
    )
    
    logger.info(f"Successfully imported {len(df)} JOIN definitions from {csv_path}")
    return engine
def update_joins_in_tables(conn, config):
    """Update the TablesToConvert table with JOINs."""
    logger.info("Updating JOINS in TablesToConvert List")
    update_joins_sql = load_sql('justice/update_joins.sql', DB_NAME)
    run_sql_script(conn, 'update_joins', update_joins_sql, timeout=config['sql_timeout'])
    logger.info("Updating JOINS for Justice tables is complete.")
def execute_table_operations(conn, config, log_file):
    """Execute DROP and SELECT INTO operations for all tables."""
    logger.info("Executing table operations (DROP/SELECT)")
    
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT RowID, DatabaseName, SchemaName, TableName, fConvert, ScopeRowCount,
               Drop_IfExists, CAST(Select_Into AS VARCHAR(MAX)) + CAST(Joins AS VARCHAR(MAX)) AS [Select_Into]
        FROM {DB_NAME}.dbo.TablesToConvert S
        WHERE fConvert=1
        ORDER BY DatabaseName, SchemaName, TableName
    """)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    for idx, row in enumerate(safe_tqdm(rows, desc="Drop/Select", unit="table"), 1):
        row_dict = dict(zip(columns, row))
        drop_sql = row_dict.get('Drop_IfExists')
        select_into_sql = row_dict.get('Select_Into')
        table_name = row_dict.get('TableName')
        schema_name = row_dict.get('SchemaName')
        scope_row_count = row_dict.get('ScopeRowCount')
        full_table_name = f"{schema_name}.{table_name}"
        
        # Skip empty tables unless configured to include them
        if not config['include_empty_tables'] and (scope_row_count is None or int(scope_row_count) <= 0):
            logger.info(f"Skipping Select INTO for {full_table_name}: scope_row_count is {scope_row_count}")
            continue
        
        if drop_sql and drop_sql.strip():
            #logger.info(f"RowID:{idx} Drop If Exists:(Justice.{full_table_name})")
            try:
                cursor.execute(drop_sql)
                conn.commit()
                
                if select_into_sql and select_into_sql.strip():
                    #logger.info(f"RowID:{idx} Select INTO:(Justice.{full_table_name})")
                    cursor.execute(select_into_sql)
                    conn.commit()
            except Exception as e:
                error_msg = f"Error executing statements for row {idx} (Justice.{full_table_name}): {e}"
                logger.error(error_msg)
                log_exception_to_file(error_msg, log_file)
    
    cursor.close()
    logger.info("All Drop_IfExists and Select_Into statements executed for the JUSTICE Database")
def create_primary_keys(conn, config, log_file):
    """Create primary keys and NOT NULL constraints."""
    if config['skip_pk_creation']:
        logger.info("Skipping primary key and constraint creation as requested in configuration")
        return
    
    logger.info("Generating List of Primary Keys and NOT NULL Columns")
    pk_sql = load_sql('justice/create_primarykeys.sql', DB_NAME)
    run_sql_script(conn, 'create_primarykeys', pk_sql, timeout=config['sql_timeout'])
    
    cursor = conn.cursor()
    cursor.execute(f"""
        WITH CTE_PKS AS (
            SELECT 1 AS TYPEY, S.DatabaseName, S.SchemaName, S.TableName, S.Script
            FROM {DB_NAME}.dbo.PrimaryKeyScripts S
            WHERE S.ScriptType='NOT_NULL'
            UNION
            SELECT 2 AS TYPEY, S.DatabaseName, S.SchemaName, S.TableName, S.Script
            FROM {DB_NAME}.dbo.PrimaryKeyScripts S
            WHERE S.ScriptType='PK'
        )
        SELECT S.TYPEY, S.DatabaseName, S.SchemaName, S.TableName,
               REPLACE(S.Script, 'FLAG NOT NULL', 'BIT NOT NULL') AS [Script], TTC.fConvert
        FROM CTE_PKS S
        INNER JOIN {DB_NAME}.dbo.TablesToConvert TTC WITH (NOLOCK)
            ON S.SCHEMANAME=TTC.SchemaName AND S.TABLENAME=TTC.TableName
        WHERE TTC.fConvert=1
        ORDER BY S.SCHEMANAME, S.TABLENAME, S.TYPEY
    """)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    for idx, row in enumerate(safe_tqdm(rows, desc="PK Creation", unit="table"), 1):
        row_dict = dict(zip(columns, row))
        createpk_sql = row_dict.get('Script')
        schema_name = row_dict.get('SchemaName')
        table_name = row_dict.get('TableName')
        full_table_name = f"{schema_name}.{table_name}"
        
        logger.info(f"RowID:{idx} PK Creation:(Justice.{full_table_name})")
        try:
            cursor.execute(createpk_sql)
            conn.commit()
        except Exception as e:
            error_msg = f"Error executing PK statements for row {idx} (Justice.{full_table_name}): {e}"
            logger.error(error_msg)
            log_exception_to_file(error_msg, log_file)
    
    cursor.close()
    logger.info("All Primary Key/NOT NULL statements executed FOR THE JUSTICE DATABASE.")
def show_completion_message():
    """Show a message box indicating completion and asking to continue."""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    proceed = messagebox.askyesno(
        "Justice DB Migration Complete",
        "The Justice DB migration is complete.\n\n"
        "You may now drop the Justice DB database if desired.\n\n"
        "Click Yes to proceed to Operations migration, or No to stop."
    )
    root.destroy()
    return proceed
def safe_tqdm(iterable, **kwargs):
    """Wrapper for tqdm that falls back to a simple iterator if tqdm fails."""
    try:
        # First try with default settings
        for item in tqdm(iterable, **kwargs):
            yield item
    except OSError:
        # If that fails, try with a safer configuration
        for item in tqdm(iterable, ascii=True, disable=None, **kwargs):
            yield item
    except:
        # If all tqdm attempts fail, just use the regular iterable
        print(f"Progress bar disabled: {kwargs.get('desc', 'Processing')}")
        for item in iterable:
            yield item

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
        if args.skip_pk_creation:
            config["skip_pk_creation"] = True
        
        # Set up paths
        config['log_file'] = args.log_file or os.path.join(
            os.environ.get("EJ_LOG_DIR", ""), 
            config["log_filename"]
        )
        
        config['csv_file'] = args.csv_file or os.path.join(
            os.environ.get("EJ_CSV_DIR", ""),
            config["csv_filename"]
        )
        
        logger.info(f"Using configuration: {json.dumps(config, indent=2)}")
        
        # Begin database operations
        try:
            with get_target_connection() as target_conn:
                # Step 1: Define supervision scope
                define_supervision_scope(target_conn, config)
                
                # Step 2: Prepare SQL commands for drops and inserts
                prepare_drop_and_select(target_conn, config)
                
                # Step 3: Import joins from CSV
                import_joins(config, config['log_file'])
                
                # Step 4: Update joins in tables
                update_joins_in_tables(target_conn, config)
                
                # Step 5: Execute table operations
                execute_table_operations(target_conn, config, config['log_file'])
                
                # Step 6: Create primary keys and constraints
                create_primary_keys(target_conn, config, config['log_file'])
                
                # Step 7: Show completion message
                proceed = show_completion_message()
                if not proceed:
                    logger.info("User chose to stop after Justice migration.")
                    return
                
                # If user chose to proceed, the next step would be called here
                # (e.g., operations migration)
                
        except Exception as e:
            logger.exception("Unexpected error during database operations")
            raise e
                
    except Exception as e:
        logger.exception("Unexpected error")
        import traceback
        error_details = traceback.format_exc()
        
        # Try to log the error to file
        try:
            log_exception_to_file(error_details, config.get('log_file', DEFAULT_LOG_FILE))
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
