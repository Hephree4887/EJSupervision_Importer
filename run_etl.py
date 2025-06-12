import os
import sys
import json
import subprocess
import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
import pyodbc
import re

SCRIPTS = [
    ("Justice DB Import", "01_JusticeDB_Import.py"),
    ("Operations DB Import", "02_OperationsDB_Import.py"),
    ("Financial DB Import", "03_FinancialDB_Import.py"),
    ("LOB Column Processing", "04_LOBColumns.py"),
]

CONFIG_FILE = os.path.join("config", "values.json")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EJ Supervision Importer")
        self.resizable(False, False)
        self.conn_str = None
        self.csv_dir = ""
        self.config_values = self._load_config()
        self._create_connection_widgets()
        self.status_labels = {}  # Store status labels

    def _load_config(self):
        """Load configuration from JSON file if it exists"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
        return {
            "driver": "",
            "server": "",
            "database": "",
            "user": "",
            "password": "",
            "csv_dir": "",
            "include_empty_tables": False
        }

    def _save_config(self):
        """Save current configuration to JSON file"""
        config = {
            "driver": self.entries["driver"].get(),
            "server": self.entries["server"].get(),
            "database": self.entries["database"].get(),
            "user": self.entries["user"].get(),
            "password": self.entries["password"].get(),
            "csv_dir": self.csv_dir_var.get(),
            "include_empty_tables": self.include_empty_var.get()
        }
        
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def _create_connection_widgets(self):
        fields = ["Driver", "Server", "Database", "User", "Password"]
        self.entries = {}
        for i, field in enumerate(fields):
            lbl = tk.Label(self, text=field+":")
            lbl.grid(row=i, column=0, sticky="e", padx=5, pady=2)
            ent = tk.Entry(self, width=40)
            if field.lower() == "password":
                ent.config(show="*")
            # Pre-populate with config values if available
            field_key = field.lower()
            if field_key in self.config_values and self.config_values[field_key]:
                ent.insert(0, self.config_values[field_key])
            ent.grid(row=i, column=1, padx=5, pady=2)
            self.entries[field.lower()] = ent

        row = len(fields)
        lbl = tk.Label(self, text="CSV Directory:")
        lbl.grid(row=row, column=0, sticky="e", padx=5, pady=2)
        self.csv_dir_var = tk.StringVar()
        if "csv_dir" in self.config_values:
            self.csv_dir_var.set(self.config_values["csv_dir"])
        ent = tk.Entry(self, textvariable=self.csv_dir_var, width=40)
        ent.grid(row=row, column=1, padx=5, pady=2)
        browse_btn = tk.Button(self, text="Browse", command=self._browse_csv_dir)
        browse_btn.grid(row=row, column=2, padx=5, pady=2)

        # checkbox to include empty tables
        self.include_empty_var = tk.BooleanVar(value=self.config_values.get("include_empty_tables", False))
        chk = tk.Checkbutton(self, text="Include empty tables", variable=self.include_empty_var)
        chk.grid(row=row+1, column=0, columnspan=2, pady=(5, 0))

        test_btn = tk.Button(self, text="Test Connection", command=self.test_connection)
        test_btn.grid(row=row+2, column=0, columnspan=2, pady=10)

    def _browse_csv_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.csv_dir_var.set(directory)

    def _show_script_widgets(self):
        if hasattr(self, "script_frame"):
            return

        self.script_frame = tk.Frame(self)
        start_row = len(self.entries) + 3
        self.script_frame.grid(row=start_row, column=0, columnspan=3, sticky="nsew")

        # Add column headers
        tk.Label(self.script_frame, text="Script", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Label(self.script_frame, text="Action", font=("Arial", 10, "bold")).grid(row=0, column=1, sticky="w", padx=5, pady=2)
        tk.Label(self.script_frame, text="Current Table", font=("Arial", 10, "bold")).grid(row=0, column=2, sticky="w", padx=5, pady=2)

        for idx, (label, path) in enumerate(sorted(SCRIPTS, key=lambda x: x[1]), 1):
            tk.Label(self.script_frame, text=path).grid(row=idx, column=0, sticky="w", padx=5, pady=2)
            tk.Button(
                self.script_frame,
                text="Run",
                command=lambda p=path: self.run_script(p)
            ).grid(row=idx, column=1, padx=5, pady=2)
            
            # Add status label for current table
            status_var = tk.StringVar(value="Not started")
            status_lbl = tk.Label(self.script_frame, textvariable=status_var, 
                                 width=30, anchor="w", bg="#f0f0f0")
            status_lbl.grid(row=idx, column=2, sticky="w", padx=5, pady=2)
            self.status_labels[path] = status_var

        self.output_text = scrolledtext.ScrolledText(self.script_frame, width=80, height=20)
        self.output_text.grid(row=len(SCRIPTS)+1, column=0, columnspan=3, pady=(10, 0))

    def _build_conn_str(self):
        driver = self.entries["driver"].get() or "{ODBC Driver 17 for SQL Server}"
        server = self.entries["server"].get()
        database = self.entries["database"].get()
        user = self.entries["user"].get()
        password = self.entries["password"].get()

        parts = [f"DRIVER={driver}", f"SERVER={server}"]
        if database:
            parts.append(f"DATABASE={database}")
        if user:
            parts.append(f"UID={user}")
        if password:
            parts.append(f"PWD={password}")
        return ";".join(parts)

    def test_connection(self):
        conn_str = self._build_conn_str()
        if not conn_str:
            messagebox.showerror("Error", "Please provide connection details")
            return
        try:
            pyodbc.connect(conn_str, timeout=5)
        except Exception as exc:
            messagebox.showerror("Connection Failed", str(exc))
            return

        messagebox.showinfo("Success", "Connection successful!")
        self.conn_str = conn_str
        os.environ["MSSQL_TARGET_CONN_STR"] = conn_str
        db_name = self.entries["database"].get()
        if db_name:
            os.environ["MSSQL_TARGET_DB_NAME"] = db_name
        self.csv_dir = self.csv_dir_var.get()
        if self.csv_dir:
            os.environ["EJ_CSV_DIR"] = self.csv_dir
        
        # Save current configuration
        self._save_config()
        
        self._show_script_widgets()

    def run_script(self, path):
        if not self.conn_str:
            messagebox.showerror("Error", "Please test the connection first")
            return
            
        # Reset status label
        self.status_labels[path].set("Starting...")
        
        os.environ["INCLUDE_EMPTY_TABLES"] = "1" if self.include_empty_var.get() else "0"
        self.output_text.insert(tk.END, f"Running {path}...\n")
        self.output_text.see(tk.END)
        
        try:
            # Use Popen instead of run to capture output in real-time
            process = subprocess.Popen(
                [sys.executable, path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Patterns to match table processing notifications
            drop_pattern = re.compile(r"Drop If Exists:\((\w+)\.([^)]+)\)")
            select_pattern = re.compile(r"Select INTO:\((\w+)\.([^)]+)\)")
            
            # Update GUI with output in real-time
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    # Check for table name in output
                    drop_match = drop_pattern.search(output)
                    select_match = select_pattern.search(output)
                    
                    if drop_match:
                        db, table = drop_match.groups()
                        self.status_labels[path].set(f"Dropping: {table}")
                    elif select_match:
                        db, table = select_match.groups()
                        self.status_labels[path].set(f"Creating: {table}")
                    
                    self.output_text.insert(tk.END, output)
                    self.output_text.see(tk.END)
                    self.update()  # Update the GUI
                    
            return_code = process.poll()
            if return_code != 0:
                self.output_text.insert(tk.END, f"Process exited with return code {return_code}\n")
                self.status_labels[path].set("ERROR")
            else:
                self.status_labels[path].set("Completed")

        except Exception as exc:
            self.output_text.insert(tk.END, f"Error running {path}: {exc}\n")
            self.status_labels[path].set("ERROR")
            
        self.output_text.insert(tk.END, f"Finished {path}\n\n")
        self.output_text.see(tk.END)

if __name__ == "__main__":
    App().mainloop()