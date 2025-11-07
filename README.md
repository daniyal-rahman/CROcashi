## Biotech Knowledge Graph Platform

This repository contains Python scripts to fetch raw data from high-priority biotech/pharma sources and a comprehensive PostgreSQL database schema for entity resolution and relationship mapping.

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Database Setup

The database schema uses SQLAlchemy 2.0+ and Alembic for migrations. It supports complex entity resolution across companies, drugs, clinical trials, publications, patents, and regulatory events.

#### 1. PostgreSQL Installation

Ensure PostgreSQL is installed and running:

```bash
# macOS (using Homebrew)
brew install postgresql@14
brew services start postgresql@14

# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

#### 2. Create Database

```bash
# Connect to PostgreSQL
psql postgres

# Create database and user
CREATE DATABASE biotech_kg;
CREATE USER biotech_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE biotech_kg TO biotech_user;
\q
```

#### 3. Configure Database Connection

Create a `.env` file in the project root:

```bash
DATABASE_URL=postgresql://biotech_user:your_password@localhost:5432/biotech_kg
```

#### 4. Initialize Database

```bash
# Option 1: Using the init script
python database/init_db.py

# Option 2: Using Alembic (recommended for production)
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

#### 5. Verify Installation

```python
from database.config import get_db_session
from database.models import Company, Drug

# Test connection
with get_db_session() as session:
    companies = session.query(Company).count()
    print(f"Database connected! Companies: {companies}")
```

### Database Schema Overview

The database includes 45+ tables organized into:

- **Entities**: Companies, Institutions, Drugs, Targets, Mechanisms, Diseases
- **Clinical**: Clinical Trials, Regulatory Events
- **Publications**: Publications, Patents, Conferences, SEC Filings
- **Relationships**: 20+ relationship tables connecting entities
- **Resolution**: Entity aliases, matching, confidence tracking
- **Staging**: Raw data staging before entity resolution

Key features:
- UUID primary keys for all tables
- Temporal tracking (date ranges for ownership, name changes)
- JSONB for flexible metadata storage
- Comprehensive indexes for performance
- Proper foreign key constraints with cascade behaviors

### Database Usage Examples

See `database/examples.py` for example queries demonstrating:

- Company-drug relationships
- Drug indications and trials
- Disease-drug mappings
- Complex multi-table queries
- Search functionality

```python
from database.config import get_db_session
from database.utils import (
    get_company_by_name,
    get_company_pipeline,
    get_trials_for_drug,
    search_drugs
)

with get_db_session() as session:
    # Find company
    company = get_company_by_name(session, "Pfizer")
    
    # Get pipeline
    drugs = get_company_pipeline(session, company.company_id)
    
    # Search drugs
    results = search_drugs(session, "umab", limit=10)
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1

# View history
alembic history
```

### Data Ingestion

#### Run sample ingestions

```bash
python scripts/run_samples.py
```

Outputs are written under `data/raw/{source}/` as JSON, HTML, or downloaded files.

#### Run with report

```bash
python scripts/run_with_report.py
```

This writes a consolidated report to `reports/ingestion_report.md` and `reports/ingestion_report.json`, including success/failure reasons.

### Sources Covered

- ClinicalTrials.gov API (sample page)
- WHO ICTRP bulk CSV (requires current export URL)
- EMA Clinical Trials search (first page scrape)
- FDA Drugs@FDA data files (link scrape + download)
- FDA Orange Book data files (link scrape + download)
- FDA FAERS quarterly data (attempt recent quarter patterns)
- PubMed E-utilities (ESearch + ESummary)
- PMC E-utilities (ESearch + ESummary)
- bioRxiv API (recent window)
- medRxiv API (recent window)
- And 100+ more sources (see `data_sources_covered.md`)

### Notes

- WHO ICTRP bulk export link can change; update the URL in `ingestion/who_ictrp.py` or pass it when calling `download_bulk_csv`.
- NCBI rate limits: ~3 req/s without an API key, ~10 req/s with a key. These scripts throttle accordingly if you supply a key to the call.
- Database uses PostgreSQL-specific features (JSONB, arrays, extensions). Ensure PostgreSQL 12+ is used.


