# Database Setup Instructions

## Current Status

Your `.env` file is configured with:
- DB_USER: ncfd
- DB_NAME: biotech_kg
- DB_PORT: 5432 (please verify your PostgreSQL is running on this port)

## Issue: Database Creation Permission

The user `ncfd` does not have permission to create databases. You need to create the database manually.

## Solution Options

### Option 1: Ask PostgreSQL Superuser to Create Database (Recommended)

Ask someone with superuser access (usually `postgres` user) to run:

```bash
# As postgres user or with sudo
psql -U postgres -d postgres
CREATE DATABASE biotech_kg;
GRANT ALL PRIVILEGES ON DATABASE biotech_kg TO ncfd;
\q
```

Or using createdb command:
```bash
createdb -U postgres biotech_kg
```

### Option 2: Grant CREATEDB Privilege to Your User

If you have access to a superuser account:

```sql
ALTER USER ncfd WITH CREATEDB;
```

Then you can create the database:
```bash
createdb -U ncfd biotech_kg
```

### Option 3: Use an Existing Database

If you have access to an existing database, you can update `.env`:

```
DB_NAME=your_existing_database
```

## After Database is Created

Once the database exists, run:

```bash
source .venv/bin/activate
python database/setup_database.py
```

This will:
1. Create PostgreSQL extensions (uuid-ossp, pg_trgm)
2. Create all 45 database tables
3. Verify the setup

## Next Steps After Setup

1. **Create Alembic migration:**
   ```bash
   alembic revision --autogenerate -m "Initial schema"
   ```

2. **Review the migration file** in `database/migrations/versions/` (optional but recommended)

3. **Apply the migration:**
   ```bash
   alembic upgrade head
   ```

4. **Verify installation:**
   ```python
   from database.config import get_db_session
   from database.models import Company
   
   with get_db_session() as session:
       count = session.query(Company).count()
       print(f"✓ Database ready! Companies: {count}")
   ```

## Quick Test

Test your database connection:

```bash
psql -U ncfd -d biotech_kg -c "SELECT version();"
```

If this works, the database exists and you have access!

