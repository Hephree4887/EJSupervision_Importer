# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Collect all data files and hidden imports
hidden_imports = [
    'pyodbc',
    'pandas',
    'sqlalchemy',
    'sqlalchemy.sql.default_comparator',
    'sqlalchemy.dialects.mssql',
    'sqlalchemy.dialects.mssql.pyodbc',
    'mysql.connector',
    'tkinter',
    'tkinter.messagebox',
    'tkinter.scrolledtext',
    'tkinter.filedialog',
    'utils',
    'utils.logging_helper',
    'utils.etl_helpers',
    'db',
    'db.mssql',
    'db.mysql',
    'etl',
    'etl.core',
    'etl.base_importer',
    'config',
    'config.settings',
]

# Add all the ETL script modules
etl_scripts = [
    '01_JusticeDB_Import',
    '02_OperationsDB_Import', 
    '03_FinancialDB_Import',
    '04_LOBColumns'
]
hidden_imports.extend(etl_scripts)

# Collect all submodules to ensure nothing is missed
for module in ['utils', 'db', 'etl', 'config']:
    hidden_imports.extend(collect_submodules(module))

a = Analysis(
    ['run_etl.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[
        ('config', 'config'),
        ('sql_scripts', 'sql_scripts'),
        ('utils', 'utils'),
        ('db', 'db'),
        ('etl', 'etl'),
        ('01_JusticeDB_Import.py', '.'),
        ('02_OperationsDB_Import.py', '.'),
        ('03_FinancialDB_Import.py', '.'),
        ('04_LOBColumns.py', '.'),
        ('.env', '.') if os.path.exists('.env') else ('', ''),
    ],
    hiddenimports=hidden_imports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EJImporter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Keep console for debugging
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EJImporter',
)