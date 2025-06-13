"""Base classes for database importers."""
import logging
import os
from tqdm import tqdm

class BaseDBImporter:
    """Base class for all database importers."""
    
    DB_TYPE = "Base"
    DEFAULT_LOG_FILE = "PreDMSErrorLog.txt"
    DEFAULT_CSV_FILE = None
    
    def __init__(self):
        self.config = {
            'sql_timeout': 600  # Default timeout in seconds
        }
        self.db_name = None
        
    def parse_args(self):
        """Parse command line arguments."""
        raise NotImplementedError("Subclasses must implement parse_args()")
    
    def execute_preprocessing(self, conn):
        """Run preprocessing steps."""
        raise NotImplementedError("Subclasses must implement execute_preprocessing()")
    
    def safe_tqdm(self, iterable, **kwargs):
        """Return tqdm iterator with error handling."""
        return tqdm(iterable, **kwargs)
        
    def run(self):
        """Run the import process."""
        args = self.parse_args()
        # Implementation would go here
        pass