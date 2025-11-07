-- Create database for biotech knowledge graph
-- Run this as a superuser or user with CREATEDB privilege

CREATE DATABASE biotech_kg;

-- Connect to the new database
\c biotech_kg

-- Grant privileges (if needed)
-- GRANT ALL PRIVILEGES ON DATABASE biotech_kg TO ncfd;

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

\q

