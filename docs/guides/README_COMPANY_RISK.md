# Company Risk Profiles Dashboard

Complete implementation of the Company Risk Profiles Dashboard with risk scoring, metrics calculation, REST API, and React frontend.

## Architecture

### Backend
- **Service Layer**: `CompanyRiskService` for risk calculations and metrics
- **API Layer**: FastAPI with REST endpoints
- **Caching**: Redis-based caching with fallback
- **Database**: PostgreSQL with materialized views for performance

### Frontend
- **Framework**: React with TypeScript
- **Charts**: Recharts for visualizations
- **Styling**: Tailwind CSS
- **Build**: Vite

## Setup

### Backend Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run Database Migration**:
   ```bash
   alembic upgrade head
   ```

3. **Set Environment Variables** (optional):
   ```bash
   # .env file
   REDIS_URL=redis://localhost:6379/0
   DATABASE_URL=postgresql://user:pass@localhost:5432/biotech_kg
   ```

4. **Start API Server**:
   ```bash
   uvicorn src.api.main:app --reload
   ```

   API will be available at `http://localhost:8000`

### Frontend Setup

1. **Install Dependencies**:
   ```bash
   cd frontend
   npm install
   ```

2. **Start Development Server**:
   ```bash
   npm run dev
   ```

   Frontend will be available at `http://localhost:3000`

## API Endpoints

### Health Check
- `GET /api/health` - Check API health

### Company Risk
- `GET /api/companies/{company_id}/risk-profile` - Get risk score and breakdown
- `GET /api/companies/{company_id}/metrics` - Get raw metrics
- `GET /api/companies/{company_id}/timeline` - Get event timeline
- `GET /api/companies/search` - Search companies with filters

### Query Parameters

**Timeline Endpoint**:
- `start_date` (optional): Filter events from this date
- `end_date` (optional): Filter events to this date
- `event_types` (optional): Filter by event types (array)

**Search Endpoint**:
- `risk_category` (optional): Filter by risk category (LOW, MODERATE, HIGH, CRITICAL)
- `therapeutic_area` (optional): Filter by therapeutic area
- `min_programs` (optional): Minimum number of programs
- `limit` (default: 50): Maximum results
- `offset` (default: 0): Pagination offset

## Risk Scoring

The risk score (0-100) is calculated from four components:

1. **Failure Rate** (40 points): Historical failure rate
2. **Recent Failures** (30 points): Failures in last 12 months
3. **Pipeline Stagnation** (20 points): Days since last update
4. **Warning Signals** (10 points): Early warning indicators

### Risk Categories
- **LOW**: 0-25
- **MODERATE**: 25-50
- **HIGH**: 50-75
- **CRITICAL**: 75-100

## Database

### Materialized View

The `company_risk_metrics` materialized view is refreshed daily. To refresh manually:

```sql
SELECT refresh_company_risk_metrics();
```

Or via Alembic migration:
```bash
alembic upgrade head
```

## Testing

### Run Service Tests
```bash
pytest tests/test_company_risk_service.py
```

### Run API Tests
```bash
pytest tests/test_company_risk_api.py
```

## Frontend Features

1. **Company Search**: Autocomplete search with filters
2. **Risk Score Gauge**: Visual 0-100 meter with color coding
3. **Metrics Cards**: Key metrics display
4. **Timeline Visualization**: Interactive event timeline
5. **PDF Export**: Generate risk profile reports

## Deployment

### Docker (Recommended)

Create `docker-compose.yml`:
```yaml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/biotech_kg
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
  
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - api
  
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=biotech_kg
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
  
  redis:
    image: redis:7
```

### Production Considerations

1. **CORS**: Update `allow_origins` in `src/api/main.py`
2. **Caching**: Ensure Redis is available for production
3. **Database**: Use connection pooling
4. **Security**: Add authentication/authorization
5. **Monitoring**: Add logging and metrics

## API Documentation

FastAPI automatically generates OpenAPI documentation:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Troubleshooting

### Redis Not Available
The cache will automatically fall back to no-op if Redis is unavailable. This is fine for development but should be fixed for production.

### Migration Errors
If migration fails, check:
1. Database connection
2. Existing schema conflicts
3. Run `alembic current` to check migration state

### API Errors
Check:
1. Database connection
2. Company IDs exist in database
3. Event data is populated
4. Check logs for detailed errors

## Next Steps

1. Add authentication/authorization
2. Implement real-time updates (WebSockets)
3. Add more visualization types
4. Implement comparison mode (multiple companies)
5. Add alert system for risk changes
6. Peer benchmarking features

