import os
import sys
import json
import logging
logger = logging.getLogger(__name__)
import subprocess
import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
import pyodbc
import re
import threading
import queue
import time
from datetime import datetime

SCRIPTS = [
    ("Justice DB Import", "01_JusticeDB_Import.py"),
    ("Operations DB Import", "02_OperationsDB_Import.py"),
    ("Financial DB Import", "03_FinancialDB_Import.py"),
    ("LOB Column Processing", "04_LOBColumns.py"),
]

CONFIG_FILE = os.path.join("config", "values.json")
# Add this code to run_etl.py to make it work with our new modular structure

def run_sequential_etl(env):
    """Run the ETL scripts sequentially in proper order."""
    from importlib import import_module
    
    # Order of execution
    import_modules = [
        "01_JusticeDB_Import",
        "02_OperationsDB_Import",
        "03_FinancialDB_Import",
        "04_LOBColumns"
    ]
    
    # Set up current environment
    old_environ = os.environ.copy()
    os.environ.update(env)
    
    try:
        for module_name in import_modules:
            module = import_module(module_name)
            proceed = module.main()  # main() should return True/False to continue
            
            if not proceed:
                logger.info(f"Stopped after {module_name}")
                break
                
    finally:
        # Restore environment
        os.environ.clear()
        os.environ.update(old_environ)

class ScriptRunner(threading.Thread):
    """Thread class to run scripts without blocking the UI."""
    
    def __init__(self, script_path, env, output_queue, status_queue):
        super().__init__(daemon=True)
        self.script_path = script_path
        self.env = env
        self.output_queue = output_queue
        self.status_queue = status_queue
        self.process = None
        self._stop_event = threading.Event()
        
    def run(self):
        """Run the script and send output to queues."""
        debug_log_path = f"{self.script_path}_debug.log"
        
        try:
            # Start the subprocess
            self.process = subprocess.Popen(
                [sys.executable, "-u", self.script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,  # Unbuffered
                text=True,
                encoding='utf-8',
                errors='replace',
                env=self.env
            )
            
            # Send initial status
            self.status_queue.put(("status", "Starting..."))
            
            with open(debug_log_path, "w", encoding="utf-8") as debug_log:
                line_count = 0
                last_ui_update = time.time()
                
                # Read output line by line
                while not self._stop_event.is_set():
                    line = self.process.stdout.readline()
                    
                    if not line:
                        # Check if process has terminated
                        if self.process.poll() is not None:
                            break
                        continue
                    
                    # Always write to debug log
                    debug_log.write(line)
                    debug_log.flush()
                    
                    line_count += 1
                    
                    # Parse status information from the line
                    self._parse_status(line)
                    
                    # Send lines to UI periodically or for important updates
                    current_time = time.time()
                    if (current_time - last_ui_update > 0.1 or  # Update every 100ms
                        "Drop If Exists" in line or 
                        "Select INTO" in line or 
                        "Error" in line or 
                        "ERROR" in line or
                        line_count <= 10):  # Always show first 10 lines
                        
                        self.output_queue.put(("output", line))
                        last_ui_update = current_time
                    
                    # For very verbose output, send periodic summaries
                    if line_count % 100 == 0:
                        summary = f"[{datetime.now().strftime('%H:%M:%S')}] Processed {line_count} lines...\n"
                        self.output_queue.put(("output", summary))
            
            # Wait for process completion
            return_code = self.process.wait()
            
            # Send completion status
            if return_code != 0:
                self.output_queue.put(("output", f"\nProcess exited with return code {return_code}\n"))
                self.status_queue.put(("status", f"FAILED (code {return_code})"))
            else:
                self.status_queue.put(("status", "COMPLETED"))
                
            self.output_queue.put(("output", f"\nFinished {self.script_path}\nDebug log: {debug_log_path}\n"))
            
        except Exception as e:
            error_msg = f"Error running {self.script_path}: {str(e)}\n"
            self.output_queue.put(("output", error_msg))
            self.status_queue.put(("status", "EXECUTION ERROR"))
            logger.error(error_msg)
        finally:
            # Signal completion
            self.output_queue.put(("done", None))
    
    def _parse_status(self, line):
        """Extract status information from output line."""
        try:
            if "Drop If Exists" in line:
                match = re.search(r"RowID:(\d+) Drop If Exists:\((.*?)\)", line)
                if match:
                    row_id, table_info = match.groups()
                    self.status_queue.put(("status", f"Dropping: {table_info}"))
            elif "Select INTO" in line:
                match = re.search(r"RowID:(\d+) Select INTO:\((.*?)\)", line)
                if match:
                    row_id, table_info = match.groups()
                    self.status_queue.put(("status", f"Creating: {table_info}"))
            elif "PK Creation" in line:
                match = re.search(r"PK Creation:\((.*?)\)", line)
                if match:
                    table_info = match.group(1)
                    self.status_queue.put(("status", f"Creating PK: {table_info}"))
            elif "Gathering" in line:
                self.status_queue.put(("status", line.strip()))
            elif "completed successfully" in line:
                self.status_queue.put(("status", "Processing..."))
        except Exception:
            # Don't let parsing errors disrupt the process
            pass
    
    def stop(self):
        """Stop the thread and subprocess."""
        self._stop_event.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EJ Supervision Importer")
        self.resizable(True, True)
        self.minsize(900, 700)  # Increased height for better visibility
        self.conn_str = None
        self.csv_dir = ""
        self.config_values = self._load_config()
        self._create_connection_widgets()
        self.status_labels = {}
        self.current_runner = None
        self.update_queue = queue.Queue()
        self.status_queue = queue.Queue()
        
        # Start the queue processing
        self._process_queues()
        
        # Schedule automatic output clearing (5 minutes = 300,000 ms)
        self._schedule_auto_clear()
    
    def _schedule_auto_clear(self):
        """Schedule automatic clearing of output every 5 minutes"""
        self.after(300000, self._auto_clear)
    
    def _auto_clear(self):
        """Automatically clear the output and reschedule"""
        if hasattr(self, "output_text"):
            self.clear_output()
            self.output_text.insert(tk.END, "[AUTO] Output automatically cleared (5-minute interval)\n\n")
        # Reschedule for next time
        self._schedule_auto_clear()
    
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
            ent = tk.Entry(self, width=60)
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
        
        # Configure row and column weights to allow expansion
        self.grid_rowconfigure(start_row, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1)

        # Add column headers
        tk.Label(self.script_frame, text="Script", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Label(self.script_frame, text="Action", font=("Arial", 10, "bold")).grid(row=0, column=1, sticky="w", padx=5, pady=2)
        tk.Label(self.script_frame, text="Current Status", font=("Arial", 10, "bold")).grid(row=0, column=2, sticky="w", padx=5, pady=2)

        self.run_buttons = {}
        for idx, (label, path) in enumerate(sorted(SCRIPTS, key=lambda x: x[1]), 1):
            tk.Label(self.script_frame, text=path).grid(row=idx, column=0, sticky="w", padx=5, pady=2)
            
            # Store button reference so we can disable/enable it
            btn = tk.Button(
                self.script_frame,
                text="Run",
                command=lambda p=path: self.run_script(p)
            )
            btn.grid(row=idx, column=1, padx=5, pady=2)
            self.run_buttons[path] = btn
            
            # Add status label for current status
            status_var = tk.StringVar(value="Not started")
            status_lbl = tk.Label(self.script_frame, textvariable=status_var, 
                                 width=50, anchor="w", bg="#f0f0f0")
            status_lbl.grid(row=idx, column=2, sticky="w", padx=5, pady=2)
            self.status_labels[path] = status_var
            
        # Configure grid for output text to expand
        self.script_frame.grid_rowconfigure(len(SCRIPTS)+1, weight=1)
        self.script_frame.grid_columnconfigure(0, weight=1)
        self.script_frame.grid_columnconfigure(1, weight=1)
        self.script_frame.grid_columnconfigure(2, weight=1)

        # Create output text area with auto-scroll checkbox
        output_frame = tk.Frame(self.script_frame)
        output_frame.grid(row=len(SCRIPTS)+1, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
        output_frame.grid_rowconfigure(0, weight=1)
        output_frame.grid_columnconfigure(0, weight=1)
        
        # Add auto-scroll checkbox
        control_frame = tk.Frame(output_frame)
        control_frame.grid(row=0, column=0, sticky="ew")
        
        self.auto_scroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(control_frame, text="Auto-scroll output", variable=self.auto_scroll_var).pack(side=tk.LEFT, padx=5)
        
        # Add clear button
        tk.Button(control_frame, text="Clear Output", command=self.clear_output).pack(side=tk.LEFT, padx=5)
        
        # Create scrolled text widget
        self.output_text = scrolledtext.ScrolledText(output_frame, width=120, height=30, wrap=tk.WORD)
        self.output_text.grid(row=1, column=0, sticky="nsew")
        
        # Add timestamp to output
        self.output_text.insert(tk.END, f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Ready to run scripts.\n\n")
    
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
    
    def clear_output(self):
        """Clear the output text area."""
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Output cleared.\n\n")
    
    def run_script(self, path):
        if not self.conn_str:
            messagebox.showerror("Error", "Please test the connection first")
            return
        
        # Disable all run buttons while a script is running
        for btn in self.run_buttons.values():
            btn.config(state=tk.DISABLED)
        
        # Reset status
        self.status_labels[path].set("Starting...")
        self.output_text.insert(tk.END, f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting {path}...\n")
        if self.auto_scroll_var.get():
            self.output_text.see(tk.END)
        
        # Set up environment
        os.environ["INCLUDE_EMPTY_TABLES"] = "1" if self.include_empty_var.get() else "0"
        
        my_env = os.environ.copy()
        my_env["PYTHONUNBUFFERED"] = "1"
        my_env["PYTHONIOENCODING"] = "utf-8"
        
        # Stop any existing runner
        if self.current_runner and self.current_runner.is_alive():
            self.current_runner.stop()
            self.current_runner.join(timeout=5)
        
        # Create and start new runner thread
        self.current_runner = ScriptRunner(path, my_env, self.update_queue, self.status_queue)
        self.current_runner.start()
        
        # Store which script is currently running
        self.current_script = path
    
    def _process_queues(self):
        """Process updates from the runner threads."""
        try:
            # Process output queue
            while True:
                try:
                    msg_type, content = self.update_queue.get_nowait()
                    
                    if msg_type == "output":
                        self.output_text.insert(tk.END, content)
                        if self.auto_scroll_var.get():
                            self.output_text.see(tk.END)
                    elif msg_type == "done":
                        # Re-enable all buttons
                        for btn in self.run_buttons.values():
                            btn.config(state=tk.NORMAL)
                        break
                        
                except queue.Empty:
                    break
            
            # Process status queue
            while True:
                try:
                    msg_type, status = self.status_queue.get_nowait()
                    if msg_type == "status" and hasattr(self, 'current_script'):
                        self.status_labels[self.current_script].set(status)
                except queue.Empty:
                    break
                    
        except Exception as e:
            logger.error(f"Error processing queues: {e}")
        
        # Schedule next check
        self.after(50, self._process_queues)  # Check every 50ms for responsive UI
    
    def destroy(self):
        """Clean up when closing the application."""
        # Stop any running threads
        if self.current_runner and self.current_runner.is_alive():
            self.current_runner.stop()
            self.current_runner.join(timeout=2)
        super().destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()