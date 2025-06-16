import os
import sys
import types
import json
import importlib.util
from pathlib import Path

# Stub optional dependencies used by run_etl when importing
if "tkinter" not in sys.modules:
    tk = types.ModuleType("tkinter")
    tk.Tk = object
    tk.Label = object
    tk.Entry = object
    tk.Button = object
    tk.Checkbutton = object
    tk.Frame = object
    tk.BooleanVar = object
    tk.StringVar = object
    tk.scrolledtext = types.SimpleNamespace(ScrolledText=object)
    tk.messagebox = types.SimpleNamespace(showerror=lambda *a, **k: None,
                                          showinfo=lambda *a, **k: None)
    tk.filedialog = types.SimpleNamespace(askdirectory=lambda *a, **k: "")
    sys.modules["tkinter"] = tk
    sys.modules["tkinter.messagebox"] = tk.messagebox
    sys.modules["tkinter.scrolledtext"] = tk.scrolledtext
    sys.modules["tkinter.filedialog"] = tk.filedialog

if "pyodbc" not in sys.modules:
    class _DummyError(Exception):
        pass
    sys.modules["pyodbc"] = types.SimpleNamespace(Error=_DummyError, connect=lambda *a, **k: None)


def _import_run_etl_from_repo(tmp_cwd):
    """Import run_etl.py as if executed from a different directory."""
    run_etl_path = Path(__file__).resolve().parents[1] / "run_etl.py"
    spec = importlib.util.spec_from_file_location("run_etl", run_etl_path)
    module = importlib.util.module_from_spec(spec)
    cwd = os.getcwd()
    os.chdir(tmp_cwd)
    try:
        spec.loader.exec_module(module)  # type: ignore
    finally:
        os.chdir(cwd)
    return module


def test_load_config_from_other_directory(tmp_path):
    run_etl = _import_run_etl_from_repo(tmp_path)

    # Ensure CONFIG_FILE is absolute and points to the repo config directory
    assert os.path.isabs(run_etl.CONFIG_FILE)
    assert run_etl.CONFIG_FILE.endswith(os.path.join("config", "values.json"))

    # Write a sample config file at the expected location
    os.makedirs(os.path.dirname(run_etl.CONFIG_FILE), exist_ok=True)
    with open(run_etl.CONFIG_FILE, "w") as f:
        json.dump({"driver": "dummy"}, f)

    config = run_etl.App._load_config(object())
    assert config.get("driver") == "dummy"


def test_save_config_writes_absolute_path(tmp_path):
    run_etl = _import_run_etl_from_repo(tmp_path)

    class DummyVar:
        def __init__(self, value):
            self._v = value
        def get(self):
            return self._v

    dummy_app = types.SimpleNamespace(
        entries={name: types.SimpleNamespace(get=lambda n=name: f"val_{n}")
                 for name in ["driver", "server", "database", "user", "password"]},
        csv_dir_var=DummyVar("/tmp/csv"),
        include_empty_var=DummyVar(True),
    )

    run_etl.App._save_config(dummy_app)
    assert os.path.exists(run_etl.CONFIG_FILE)
    with open(run_etl.CONFIG_FILE) as f:
        data = json.load(f)
    assert data["csv_dir"] == "/tmp/csv"


def test_show_script_widgets_preserves_order(monkeypatch, tmp_path):
    """Buttons should be created in the order defined by ``SCRIPTS``."""
    # Build a minimal tkinter stub with the widget methods used by ``App``.
    class DummyWidget:
        def __init__(self, *a, **kw):
            pass
        def grid(self, *a, **kw):
            pass
        def pack(self, *a, **kw):
            pass
        def config(self, *a, **kw):
            pass
        def insert(self, *a, **kw):
            pass
        def get(self):
            return ""
        def delete(self, *a, **kw):
            pass
        def see(self, *a, **kw):
            pass
        def grid_rowconfigure(self, *a, **kw):
            pass
        def grid_columnconfigure(self, *a, **kw):
            pass

    class DummyEntry(DummyWidget):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._val = ""
        def insert(self, idx, val):
            self._val = val
        def get(self):
            return self._val

    class DummyVar:
        def __init__(self, value=None):
            self._v = value
        def get(self):
            return self._v
        def set(self, val):
            self._v = val

    class DummyTk(DummyWidget):
        def title(self, *a, **k):
            pass
        def resizable(self, *a, **k):
            pass
        def minsize(self, *a, **k):
            pass
        def after(self, *a, **k):
            pass

    class DummyScrolled(DummyWidget):
        pass

    tk = types.SimpleNamespace(
        Tk=DummyTk,
        Label=DummyWidget,
        Entry=DummyEntry,
        Button=DummyWidget,
        Checkbutton=DummyWidget,
        Frame=DummyWidget,
        BooleanVar=DummyVar,
        StringVar=DummyVar,
        scrolledtext=types.SimpleNamespace(ScrolledText=DummyScrolled),
        filedialog=types.SimpleNamespace(askdirectory=lambda: ""),
        messagebox=types.SimpleNamespace(showerror=lambda *a, **k: None,
                                         showinfo=lambda *a, **k: None),
        END=None,
        WORD=None,
        LEFT=None,
    )

    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setitem(sys.modules, "tkinter.filedialog", tk.filedialog)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", tk.messagebox)
    monkeypatch.setitem(sys.modules, "tkinter.scrolledtext", tk.scrolledtext)

    monkeypatch.setitem(sys.modules, "pyodbc",
                        types.SimpleNamespace(Error=Exception,
                                             connect=lambda *a, **k: None))

    run_etl = _import_run_etl_from_repo(tmp_path)
    app = run_etl.App()
    app._show_script_widgets()

    assert list(app.run_buttons.keys()) == [p for _, p in run_etl.SCRIPTS]


def test_build_conn_str(tmp_path):
    run_etl = _import_run_etl_from_repo(tmp_path)

    class DummyEntry:
        def __init__(self, val):
            self._v = val
        def get(self):
            return self._v

    app = types.SimpleNamespace(
        entries={
            'driver': DummyEntry('{SQL}'),
            'server': DummyEntry('srv'),
            'database': DummyEntry('db'),
            'user': DummyEntry('u'),
            'password': DummyEntry('p'),
        }
    )

    assert run_etl.App._build_conn_str(app) == 'DRIVER={SQL};SERVER=srv;DATABASE=db;UID=u;PWD=p'


def test_run_sequential_etl_restores_env(monkeypatch, tmp_path):
    run_etl = _import_run_etl_from_repo(tmp_path)

    calls = []
    def make_mod(name, ret=True):
        mod = types.SimpleNamespace()
        def main():
            calls.append(name)
            return ret
        mod.main = main
        return mod

    modules = {
        '01_JusticeDB_Import': make_mod('01'),
        '02_OperationsDB_Import': make_mod('02', ret=False),
        '03_FinancialDB_Import': make_mod('03'),
        '04_LOBColumns': make_mod('04'),
    }
    for name, mod in modules.items():
        monkeypatch.setitem(sys.modules, name, mod)

    monkeypatch.setenv('FOO', 'old')
    run_etl.run_sequential_etl({'FOO': 'new'})

    assert os.environ['FOO'] == 'old'
    assert calls == ['01', '02']
