@echo off
echo Building EJ Importer...
echo.

REM Clean up old builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Ensure all dependencies are installed
echo Installing dependencies...
pip install --upgrade pip
pip install pyinstaller
pip install -r requirements.txt
echo.

REM Create the executable
echo Building executable...
pyinstaller --clean run_etl.spec
echo.

REM Create config directory in dist folder if it doesn't exist
if not exist "dist\EJImporter\config" mkdir "dist\EJImporter\config"

REM Copy the values.json if it exists
if exist "config\values.json" (
    copy "config\values.json" "dist\EJImporter\config\"
    echo Copied values.json to distribution
) else (
    echo No values.json found - users will need to configure on first run
)

REM Create empty directories for CSV files and logs
if not exist "dist\EJImporter\csv" mkdir "dist\EJImporter\csv"
if not exist "dist\EJImporter\logs" mkdir "dist\EJImporter\logs"

REM Create a README for the distribution
echo Creating README...
echo EJ Importer > "dist\EJImporter\README.txt"
echo ========== >> "dist\EJImporter\README.txt"
echo. >> "dist\EJImporter\README.txt"
echo Prerequisites: >> "dist\EJImporter\README.txt"
echo - Microsoft ODBC Driver 17 for SQL Server must be installed >> "dist\EJImporter\README.txt"
echo - Place your CSV files in the 'csv' folder >> "dist\EJImporter\README.txt"
echo. >> "dist\EJImporter\README.txt"
echo To run: Double-click EJImporter.exe >> "dist\EJImporter\README.txt"
echo. >> "dist\EJImporter\README.txt"
echo Configuration will be saved in config\values.json >> "dist\EJImporter\README.txt"
echo Error logs will be created in the logs folder >> "dist\EJImporter\README.txt"

echo.
echo Build complete! 
echo Distribution folder: dist\EJImporter\
echo.
pause