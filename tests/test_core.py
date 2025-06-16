import os
import pytest
import sys, types

if "tqdm" not in sys.modules:
    dummy = types.ModuleType("tqdm")
    def _tqdm(iterable, **kwargs):
        for item in iterable:
            yield item
    dummy.tqdm = _tqdm
    sys.modules["tqdm"] = dummy

if "dotenv" not in sys.modules:
    mod = types.ModuleType("dotenv")
    mod.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = mod

from etl.core import sanitize_sql


def test_sanitize_sql_allows_normal_statements():
    text = "SELECT * FROM table"
    assert sanitize_sql(text) == text


def test_sanitize_sql_rejects_injection_attempt():
    malicious = "'; DROP TABLE users; --"
    result = sanitize_sql(malicious)
    assert result == ""
