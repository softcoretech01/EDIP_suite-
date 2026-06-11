import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Generator

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Fetch database configuration from environment
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "erp_db")
MYSQL_USERNAME = os.getenv("MYSQL_USERNAME", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")

def get_engine():
    """
    Creates and returns a SQLAlchemy engine for MySQL using PyMySQL driver
    with connection pooling enabled.
    """
    try:
        import urllib.parse
        encoded_password = urllib.parse.quote_plus(MYSQL_PASSWORD) if MYSQL_PASSWORD else ""
        DATABASE_URL = f"mysql+pymysql://{MYSQL_USERNAME}:{encoded_password}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
        
        # Create engine with connection pooling and timeout handling
        engine = create_engine(
            DATABASE_URL,
            pool_size=5,             # Default number of connections in the pool
            max_overflow=10,         # Max extra connections if pool is full
            pool_timeout=30,         # Seconds to wait before giving up on getting a connection
            pool_recycle=1800,       # Recycle connections after 30 minutes to prevent staleness
            connect_args={"connect_timeout": 10} # Timeout for initial connection attempt
        )
        return engine
    except Exception as e:
        logger.error(f"Failed to create database engine: {e}")
        raise

# Initialize engine and session maker
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db() -> Generator:
    """
    Dependency injection function for FastAPI to get a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_connection() -> dict:
    """
    Health check function to verify the database connection.
    Returns a dictionary with status and details.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "connected", "details": f"Connected to MySQL at {MYSQL_HOST}:{MYSQL_PORT}"}
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Database connection test failed: {error_msg}")
        return {"status": "disconnected", "error": error_msg}
