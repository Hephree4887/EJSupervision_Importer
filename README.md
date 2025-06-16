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
4. When the connection test succeeds the entered values are written to
   `config/values.json` so they are pre-filled on the next launch.

The connection string will be built from the provided details and passed to
the selected ETL scripts using the `MSSQL_TARGET_CONN_STR` environment
variable.

## ETL Scripts

The repository contains four independent ETL modules:

- **01_JusticeDB_Import.py** – loads data extracted from the Justice
  application and stages it in the target database.
- **02_OperationsDB_Import.py** – processes tables from the Operations system
  using the same workflow as the Justice import.
- **03_FinancialDB_Import.py** – migrates the Financial database content
  including auxiliary lookup tables.
- **04_LOBColumns.py** – inspects large object columns and generates `ALTER`
  statements to resize them before final migration.

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

### Environment Variables

The following variables control the scripts when run from the command line:

- **`MSSQL_TARGET_CONN_STR`** – ODBC connection string for the target
  SQL Server instance. This is automatically populated when you test the
  connection in the helper UI.
- **`MSSQL_TARGET_DB_NAME`** – optional explicit database name. When not
  provided it is derived from the connection string.
- **`EJ_CSV_DIR`** – directory containing the `*_Selects_*.csv` files.
  Selecting a folder in the UI sets this variable for the launched scripts.
- **`EJ_LOG_DIR`** – where error logs should be written. Defaults to the current
  working directory.
- **`SQL_TIMEOUT`** – per-statement timeout in seconds (defaults to 300).
- **`INCLUDE_EMPTY_TABLES`** – set to `1` to include tables with no data.
- **`BATCH_SIZE`** – number of rows fetched at a time by the LOB column script.

Values entered in the UI are stored in `config/values.json` so that subsequent
runs start with the last used settings.

### Helper UI

Running `python run_etl.py` opens a small Tkinter interface. After testing the
connection you can choose which ETL modules to run. Each selected script is
executed in sequence and its output appears in the UI. The application sets the
required environment variables for you based on the information entered in the
form.

## Examples

Run the Justice ETL with a JSON configuration file and custom timeout. Empty
tables are included by setting an environment variable:

```bash
SQL_TIMEOUT=600 INCLUDE_EMPTY_TABLES=1 \
python 01_JusticeDB_Import.py --config-file config/values.json \
  --log-file logs/justice.log
```

The Tk helper can run all scripts sequentially while still honouring the retry
logic built into `utils/etl_helpers.run_sql_step_with_retry`:

```bash
# Launch the helper UI
SQL_TIMEOUT=600 python run_etl.py
```

To run a specific module directly provide the required variables:

```bash
MSSQL_TARGET_CONN_STR="Driver=...;Server=sql;Database=MyDB;UID=user;PWD=pass" \
EJ_CSV_DIR=/path/to/csv \
python 02_OperationsDB_Import.py --log-file logs/ops.log
```

If a transient `pyodbc.Error` occurs the command will be retried up to
`ETLConstants.MAX_RETRY_ATTEMPTS` times.
