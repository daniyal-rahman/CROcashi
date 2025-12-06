# Database Setup - Next Steps

## Current Status ✅

- ✅ All dependencies installed (SQLAlchemy 2.0+, Alembic, psycopg2-binary)
- ✅ All 45 database models created and importing successfully
- ✅ Alembic configuration files created
- ✅ Database utilities and example queries created

## Remaining Steps

### 1. Configure Database Connection

Your `.env` file currently has a template DATABASE_URL. You need to either:

**Option A: Update .env with actual values**
```bash
# Edit .env file
DATABASE_URL=postgresql://ncfd:your_password@localhost:5432/biotech_kg
```

**Option B: Set individual variables**
```bash
DB_USER=ncfd
DB_PASS=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=biotech_kg
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}
```

### 2. Create PostgreSQL Database

Connect to PostgreSQL and create the database:

```bash
# Connect (adjust username as needed)
psql -U ncfd -d postgres

# Or if you have a different default user
psql postgres

# Create database
CREATE DATABASE biotech_kg;

# Grant permissions (if needed)
GRANT ALL PRIVILEGES ON DATABASE biotech_kg TO ncfd;

# Exit
\q
```

### 3. Test Database Connection

```bash
source .venv/bin/activate
python -c "from database.config import get_db_session; print('Testing connection...'); list(get_db_session())"
```

### 4. Initialize Database Extensions

```bash
source .venv/bin/activate
python database/init_db.py
```

This will:
- Create PostgreSQL extensions (uuid-ossp, pg_trgm)
- Create all database tables

### 5. Create Initial Alembic Migration

```bash
source .venv/bin/activate
alembic revision --autogenerate -m "Initial schema"
```

This will create a migration file in `database/migrations/versions/`

### 6. Apply Migration

```bash
alembic upgrade head
```

### 7. Verify Installation

```python
from database.config import get_db_session
from database.models import Company, Drug

with get_db_session() as session:
    companies = session.query(Company).count()
    print(f"✓ Database connected! Companies: {companies}")
```

## Troubleshooting

### Connection Issues

- Verify PostgreSQL is running: `brew services list | grep postgresql`
- Check PostgreSQL port: `lsof -i :5432`
- Verify user permissions: `psql -U ncfd -l`

### Migration Issues

- If autogenerate creates unwanted changes, edit the migration file before applying
- Review the generated migration in `database/migrations/versions/`
- Test migration on a copy of the database first

### Import Errors

- Ensure virtual environment is activated: `source .venv/bin/activate`
- Verify all dependencies: `pip install -r requirements.txt`

## Quick Test Script

Create a test file `test_db_setup.py`:

```python
#!/usr/bin/env python3
"""Test database setup."""
from database.config import get_db_session, engine
from database.models import Base

def test_connection():
    """Test database connection."""
    try:
        with engine.connect() as conn:
            result = conn.execute("SELECT version();")
            print(f"✓ PostgreSQL connected: {result.fetchone()[0][:50]}...")
        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

def test_tables():
    """Test that tables can be created."""
    try:
        Base.metadata.create_all(bind=engine)
        print("✓ Tables created successfully")
        return True
    except Exception as e:
        print(f"✗ Table creation failed: {e}")
        return False

if __name__ == '__main__':
    print("Testing database setup...")
    if test_connection():
        test_tables()
```

Run with:
```bash
source .venv/bin/activate
python test_db_setup.py
```

