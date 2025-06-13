"""Core ETL utilities shared across all database import scripts."""
import logging
import os
import json
import re
import unicodedata
from tqdm import tqdm

logger = logging.getLogger(__name__)

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
    """Enhanced SQL sanitization with better encoding handling."""
    if sql_text is None:
        return None
    
    try:
        # Ensure we're working with a proper string
        if isinstance(sql_text, bytes):
            # Try UTF-8 first, then fall back to latin-1
            try:
                sql_text = sql_text.decode('utf-8')
            except UnicodeDecodeError:
                sql_text = sql_text.decode('latin-1', errors='replace')
        
        # Convert to string if it's not already
        if not isinstance(sql_text, str):
            sql_text = str(sql_text)
        
        # Remove problematic control characters
        sql_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', sql_text)
        
        # Normalize Unicode
        sql_text = unicodedata.normalize('NFKC', sql_text)
        
        return sql_text
        
    except Exception as e:
        logger.warning(f"SQL sanitization failed: {str(e)}")
        # Last resort: convert to ASCII with replacement
        try:
            if isinstance(sql_text, bytes):
                return sql_text.decode('ascii', errors='replace')
            else:
                return str(sql_text).encode('ascii', errors='replace').decode('ascii')
        except:
            logger.error("Complete sanitization failure")
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