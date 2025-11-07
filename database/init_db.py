"""
Database initialization script.
Creates extensions and sets up the database.
"""
import sys
from database.config import engine, init_db
from database.models import Base


def main():
    """Initialize the database."""
    print("Initializing database...")
    
    try:
        # Create extensions and tables
        init_db()
        
        print("✓ Database initialized successfully!")
        print("\nNext steps:")
        print("1. Run 'alembic revision --autogenerate -m \"Initial schema\"' to create migration")
        print("2. Run 'alembic upgrade head' to apply migrations")
        print("\nOr use the init_db() function directly from database.config")
        
    except Exception as e:
        print(f"✗ Error initializing database: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

