# EJ Supervision Importer

This project contains several ETL scripts used to migrate data between
Justice, Operations and Financial databases.  Each script can be executed
independently or together using the new `run_etl.py` helper.

## Installation

Install the required packages using pip:

```bash
pip install -r requirements.txt
```


## Usage

1. Run `python run_etl.py`.
2. Enter the connection details for the target SQL Server database. Use the
   **CSV Directory** field to browse for the folder containing the CSV files
   used by the ETL scripts.
3. Select which scripts to execute and click **Run**.

The connection string will be built from the provided details and passed to
the selected ETL scripts using the `MSSQL_TARGET_CONN_STR` environment
variable.

## ETL Scripts

- **01_JusticeDB_Import.py** – migrates Justice database tables.
- **02_OperationsDB_Import.py** – migrates Operations database tables.
- **03_FinancialDB_Import.py** – migrates Financial database tables.
- **04_LOBColumns.py** – adjusts large object column lengths.

Each script expects SQL files under the `sql_scripts/` directory grouped by
database name (for example `sql_scripts/justice/` or
`sql_scripts/operations/`) and relies on `MSSQL_TARGET_CONN_STR` for the target
connection string. When a CSV directory is selected, the path is exported via
the `EJ_CSV_DIR` environment variable so the ETL scripts can locate their input
files.

Error details are written to log files. By default the logs are created in the
current working directory with names like `PreDMSErrorLog_Justice.txt`. Set the
`EJ_LOG_DIR` environment variable to override the directory or pass a full path
using the `--log-file` argument when running an individual script.
