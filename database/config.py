"""
Database configuration and connection management.
"""
import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

# Database configuration - expand environment variables if using template
db_url = os.getenv('DATABASE_URL', '')
if db_url and '${' in db_url:
    # Expand environment variables in DATABASE_URL
    db_user = os.getenv('DB_USER', 'postgres')
    db_pass = os.getenv('DB_PASS', 'postgres')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'biotech_kg')
    DATABASE_URL = f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'
else:
    DATABASE_URL = os.getenv(
        'DATABASE_URL',
        'postgresql://postgres:postgres@localhost:5432/biotech_kg'
    )

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=False,  # Set to True for SQL query logging
)

# Session factory
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Usage:
        with get_db_session() as session:
            # use session
            pass
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function for FastAPI-style usage.
    
    Usage:
        for session in get_db():
            # use session
            break
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database: create extensions and tables.
    """
    from database.models import Base
    
    # Create PostgreSQL extensions
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"pg_trgm\";"))
        conn.commit()
    
    # Create all tables
    Base.metadata.create_all(bind=engine)


@event.listens_for(Engine, "connect")
def set_postgres_settings(dbapi_conn, connection_record):
    """Set PostgreSQL-specific connection settings."""
    # Enable JSONB operators
    with dbapi_conn.cursor() as cursor:
        cursor.execute("SET search_path TO public;")


