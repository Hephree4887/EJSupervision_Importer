"""Core ETL utilities shared across all database import scripts."""
import logging
import os
import json
import re
import unicodedata
from dataclasses import dataclass, field
from tqdm import tqdm
from config import ETLConstants

_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


@dataclass
class Settings:
    """Configuration loaded from environment variables."""

    mssql_target_conn_str: str = field(default_factory=lambda: os.getenv("MSSQL_TARGET_CONN_STR"))
    ej_csv_dir: str = field(default_factory=lambda: os.getenv("EJ_CSV_DIR"))
    ej_log_dir: str = field(default_factory=lambda: os.getenv("EJ_LOG_DIR", os.getcwd()))
    include_empty_tables: bool = field(default_factory=lambda: os.getenv("INCLUDE_EMPTY_TABLES", "0") == "1")
    sql_timeout: int = field(
        default_factory=lambda: int(
            os.getenv("SQL_TIMEOUT", str(ETLConstants.DEFAULT_SQL_TIMEOUT))
        )
    )

    def __post_init__(self) -> None:
        missing = []
        if not self.mssql_target_conn_str:
            missing.append("MSSQL_TARGET_CONN_STR")
        if not self.ej_csv_dir:
            missing.append("EJ_CSV_DIR")

        if missing:
            raise ConfigError("Missing required environment variables: " + ", ".join(missing))

        if not os.path.exists(self.ej_csv_dir):
            raise ConfigError(f"EJ_CSV_DIR path does not exist: {self.ej_csv_dir}")

        if self.sql_timeout <= 0:
            raise ConfigError("SQL_TIMEOUT must be a positive integer")

def validate_environment(required_vars, optional_vars):
    """Validate environment variables with custom requirements."""
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

def load_config(config_file=None, default_config=None):
    """Load configuration from JSON file if provided, otherwise use defaults."""
    config = default_config or {}
    
    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config)
            logger.info(f"Loaded configuration from {config_file}")
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
    
    return config

def sanitize_sql(sql_text):
    """Return a sanitized SQL string or an empty string if suspicious patterns are detected."""
    if sql_text is None:
        return None

    try:
        if isinstance(sql_text, bytes):
            sql_text = sql_text.decode('utf-8', errors='replace')
        elif not isinstance(sql_text, str):
            sql_text = str(sql_text)

        sql_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', sql_text)
        sql_text = unicodedata.normalize('NFKC', sql_text)

        patterns = [
            r";\s*(?:drop|delete|truncate|alter)\s+",
            r"--",
            r"\bOR\b\s+1=1",
        ]
        injection_regex = re.compile("|".join(patterns), re.IGNORECASE)
        if injection_regex.search(sql_text):
            return ""

        if sql_text.count("'") % 2 != 0 or sql_text.count('"') % 2 != 0:
            return ""

        return sql_text

    except Exception as e:
        logger.warning(f"SQL sanitization failed: {str(e)}")
        try:
            if isinstance(sql_text, bytes):
                return sql_text.decode('ascii', errors='replace')
            else:
                return str(sql_text).encode('ascii', errors='replace').decode('ascii')
        except Exception:
            logger.error('Complete sanitization failure')
            return ""

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


def validate_sql_identifier(identifier: str) -> str:
    """Validate a string for use as a SQL identifier.

    Only allows alphanumeric characters and underscores and must not start with a digit.

    Args:
        identifier: The identifier to validate.

    Returns:
        The original identifier if valid.

    Raises:
        ValueError: If the identifier is invalid.
    """
    if not isinstance(identifier, str):
        raise ValueError("Identifier must be a string")

    if not _IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")

    return identifier
