import logging
import time
import os
from dotenv import load_dotenv
import pandas as pd
import urllib
import sqlalchemy
from db.mssql import get_target_connection
from botocore.exceptions import ClientError
from tqdm import tqdm
from sqlalchemy.types import Text
import tkinter as tk
from tkinter import messagebox

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def log_exception_to_file(error_details, log_path=r"C:\LargeFileHolder\7373\PreDMSErrorLog_Justice.txt"):
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(error_details + "\n")
    except Exception as file_exc:
        logger.error(f"Failed to write to error log file: {file_exc}")
def load_sql(filename):
    base_dir = os.path.dirname(__file__)
    sql_path = os.path.join(base_dir, 'sql_scripts', filename)
    if not os.path.exists(sql_path):
        logger.error(f"SQL file not found: {sql_path}")
        raise FileNotFoundError(f"SQL file not found: {sql_path}")
    with open(sql_path, 'r', encoding='utf-8') as f:
        return f.read()
def run_sql_step(conn, name, sql):
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
def run_sql_script(conn, name, sql):
    logger.info(f"Starting script: {name}")
    start_time = time.time()
    try:
        cursor = conn.cursor()
        # Split on semicolon, filter out empty statements
        statements = [stmt.strip() for stmt in sql.split(';') if stmt.strip()]
        for stmt in statements:
            cursor.execute(stmt)
            conn.commit()  # Commit after each statement
        cursor.close()
        elapsed = time.time() - start_time
        logger.info(f"Completed script: {name} in {elapsed:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in script {name}: {str(e)}")
        raise

def main():
    load_dotenv()
    target_conn = None

    try:
        #The first thing we do is run a set of SQL Scripts that define Supervision Scope
        #Those would be 1.) Exists SupCaseHdr, Exists in ClkCaseHdr only for CaseIDs linked to SupCaseHdrIDs using xCaseBaseChrg (Only associated court records)
        steps = [
            {'name': 'GatherCaseIDs', 'sql': load_sql('gather_caseids.sql')},
            {'name': 'GatherChargeIDs', 'sql': load_sql('gather_chargeids.sql')},
            {'name': 'GatherPartyIDs', 'sql': load_sql('gather_partyids.sql')},
            {'name': 'GatherWarrantIDs', 'sql': load_sql('gather_warrantids.sql')},
            {'name': 'GatherHearingIDs', 'sql': load_sql('gather_hearingids.sql')},
            {'name': 'GatherEventIDs', 'sql': load_sql('gather_eventids.sql')}
        ]
        target_conn = get_target_connection()
        for step in tqdm(steps, desc="SQL Script Progress", unit="step"):
            run_sql_step(target_conn, step['name'], step['sql'])
            target_conn.commit()
        logger.info("All Staging steps completed successfully. Supervision Scope Defined.")

        # After gather supervision scope we now need to create the appropriate sql commands to drop and INSERT Into the target database.
        logger.info("Gathering list of Justice tables with SQL Commands to me migrated.")
        additional_sql = load_sql('gather_drops_and_selects.sql')  
        run_sql_script(target_conn, 'gather_drops_and_selects', additional_sql)

        #Now we need to import the data from the csv file that contains all the appropriate joins for all Justice tables.
        #These joins allow us to pull only in-scope records (ie INNER JOIN ELPaso_TX.dbo.CasesToConvert CTC ON Source.CaseID=CTC.CaseID)
        logger.info("Importing JOINS from EJ_Justice_Selects_ALL Source")
        conn_str = os.environ['MSSQL_TARGET_CONN_STR']
        params = urllib.parse.quote_plus(conn_str)
        db_url = f"mssql+pyodbc:///?odbc_connect={params}"
        engine = sqlalchemy.create_engine(db_url)

        df = pd.read_csv(r'C:\Users\jeff.reichert\OneDrive - Tyler Technologies, Inc\Documents\GitHub\tx_elpaso_7373\Pre-DMS\EJ_Justice_Selects_ALL.csv', delimiter='|')
        df = df.astype({'DatabaseName': 'str','SchemaName': 'str','TableName': 'str','Freq': 'str','InScopeFreq': 'str','Select_Only': 'str','fConvert': 'str','Drop_IfExists': 'str','Selection': 'str','Select_Into': 'str'})
        df.to_sql(
            'TableUsedSelects',
            con=engine,
            if_exists='replace',
            index=False,
            dtype={'Select_Into': Text(), 'Drop_IfExists': Text()}  # This is to support the long select of the OffHist table.
        )   
        #Now that we have our Joins we need to update the "TablesToConvert" table with them in order to build appropriate sql 
        logger.info("Updating JOINS in TablesToConvert List")
        update_joins_sql = load_sql('update_joins.sql')  
        run_sql_script(target_conn, 'update_joins', update_joins_sql)
        logger.info("Updating JOINS for Justice tables is complete.")

       # Now we have gathered all Justice tables with supervision scope along with the insert into statements that will move them to the target database.
        cursor = target_conn.cursor()
        cursor.execute("""SELECT RowID, DatabaseName, SchemaName, TableName, fConvert, ScopeRowCount, Drop_IfExists,CAST(Select_Into AS VARCHAR(MAX)) + Joins AS [Select_Into] FROM ELPaso_TX.dbo.TablesToConvert S WHERE fConvert=1 ORDER BY DatabaseName, SchemaName, TableName""")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        for idx, row in enumerate(tqdm(rows, desc="Drop/Select", unit="table"), 1):
            row_dict = dict(zip(columns, row))
            drop_sql = row_dict.get('Drop_IfExists')
            select_into_sql = row_dict.get('Select_Into')
            table_name = row_dict.get('TableName')
            schema_name = row_dict.get('SchemaName')
            scope_row_count = row_dict.get('ScopeRowCount')
            full_table_name = f"{schema_name}.{table_name}"  # Concatenate schema and table

            # Always execute drop_sql if it exists
            if drop_sql and drop_sql.strip():
                logger.info(f"RowID:{idx} Drop If Exists:(Justice.{full_table_name})")
                try:
                    cursor.execute(drop_sql)
                    target_conn.commit()
                    
                    # Execute select_into_sql only if scope_row_count > 0
                    if select_into_sql and select_into_sql.strip() and scope_row_count is not None and int(scope_row_count) > 0:
                        logger.info(f"RowID:{idx} Select INTO:(Justice.{full_table_name})")
                        cursor.execute(select_into_sql)
                        target_conn.commit()
                    elif scope_row_count is None or int(scope_row_count) <= 0:
                        logger.info(f"Skipping Select INTO for {full_table_name}: scope_row_count is {scope_row_count}")
                        
                except Exception as e:
                    logger.error(f"Error executing statements for row {idx} (Justice.{full_table_name}): {e}")
                    log_exception_to_file(f"Error executing statements for row {idx} (Justice.{full_table_name}): {e}")

        cursor.close()
        logger.info("All Drop_IfExists and Select_Into statements executed for the JUSTICE Database")
        # Now that we are done with out SELECT INTO statements, we need to generate a list of Primary Keys and NOT Nullable Columns for each table.
        pk_sql = load_sql('create_primarykeys.sql')  
        run_sql_script(target_conn, 'create_primarykeys', pk_sql)
        logger.info("Generating List of Primary Keys and NOT Nullable Columns")

       # Now that we have our list, run through a cursor to execute each NOT NULL and Primary Key statement (in schema,table name order)
        cursor = target_conn.cursor()
        cursor.execute("""WITH CTE_PKS AS (SELECT 1 AS TYPEY,S.DatabaseName,S.SchemaName,S.TableName,S.Script FROM ELPaso_TX.dbo.PrimaryKeyScripts S WHERE S.ScriptType='NOT_NULL' UNION SELECT 2 AS TYPEY,S.DatabaseName,S.SchemaName,S.TableName,S.Script FROM ELPaso_TX.dbo.PrimaryKeyScripts S WHERE S.ScriptType='PK') SELECT S.TYPEY,S.DatabaseName,S.SchemaName,S.TableName,REPLACE(S.Script,'FLAG NOT NULL','BIT NOT NULL') AS [Script],TTC.fConvert FROM CTE_PKS S INNER JOIN ELPaso_TX.dbo.TablesToConvert TTC WITH (NOLOCK) ON S.SCHEMANAME=TTC.SchemaName AND S.TABLENAME=TTC.TableName WHERE TTC.fConvert=1 ORDER BY S.SCHEMANAME,S.TABLENAME,S.TYPEY""")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        ####### END END JUSTICE DATABASE MIGRATION STEPS ########
        for idx, row in enumerate(tqdm(rows, desc="PK Creation", unit="table"), 1):
            row_dict = dict(zip(columns, row))
            createpk_sql = row_dict.get('Script')
            schema_name = row_dict.get('SchemaName')
            table_name = row_dict.get('TableName')
            full_table_name = f"{schema_name}.{table_name}"
            logger.info(f"RowID:{idx} PK Creation:(Justice.{full_table_name})")
            try:
                cursor.execute(createpk_sql)
                target_conn.commit()
            except Exception as e:
                logger.error(f"Error executing PK statements for row {idx} (Justice.{full_table_name}): {e}")
                log_exception_to_file(f"Error executing PK statements for row {idx} (Justice.{full_table_name}): {e}")

        cursor.close()
        logger.info("All Primary Key/NOT NULL statements executed FOR THE JUSTICE DATABASE.")

        # Notify user and prompt to continue
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        proceed = messagebox.askyesno(
            "Justice DB Migration Complete",
            "The Justice DB migration is complete.\n\n You may now drop the Justice DB database if desired.\n\nClick Yes to proceed to Operations migration, or No to stop."
        )
        root.destroy()
        if not proceed:
            logger.info("User chose to stop after Justice migration.")
            if target_conn:
                target_conn.close()
            return


    except (ClientError, Exception) as e:
        logger.exception("Unexpected error")
        import traceback
        error_details = traceback.format_exc()
        log_exception_to_file(error_details)  # <-- Add this line
        try:
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            messagebox.showerror("ETL Script Error", f"An error occurred:\n\n{error_details}")
            root.destroy()
        except Exception as msgbox_exc:
            logger.error(f"Failed to show error message box: {msgbox_exc}")

    finally:
        if target_conn:
            target_conn.close()

if __name__ == "__main__":
    main()