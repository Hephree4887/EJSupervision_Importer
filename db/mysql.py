import os
import mysql.connector
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import Config from settings.py
try:
    from config.settings import Config
except ImportError:
    Config = None

def get_mysql_connection(
    host: str = None,
    user: str = None,
    password: str = None,
    database: str = None,
    port: int = None
):
    """
    Returns a MySQL database connection using environment variables,
    falling back to Config if not set.
    """
    host = host or os.getenv('MYSQL_HOST') or (getattr(Config, 'MYSQL_HOST', None) if Config else None)
    user = user or os.getenv('MYSQL_USER') or (getattr(Config, 'MYSQL_USER', None) if Config else None)
    password = password or os.getenv('MYSQL_PASSWORD') or (getattr(Config, 'MYSQL_PASSWORD', None) if Config else None)
    database = database or os.getenv('MYSQL_DATABASE') or (getattr(Config, 'MYSQL_DATABASE', None) if Config else None)
    port = port or int(os.getenv('MYSQL_PORT', getattr(Config, 'MYSQL_PORT', 3306) if Config else 3306))

    if not all([host, user, password, database]):
        raise ValueError("Missing required MySQL connection parameters.")

    return mysql.connector.connect(
        host=host,  
        user=user,
        password=password,
        database=database,
        port=port
    )
