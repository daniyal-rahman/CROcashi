# ncfd

Near-Certain Failure Detector for US-listed biotech pivotal trials.

## Development Setup

This project uses Python 3.11+ and `make` for common development tasks.

### 1. Environment Setup

First, create a virtual environment and install the required dependencies.

```bash
make setup
```

This will:
- Create a `.venv` directory with the Python virtual environment.
- Install all dependencies listed in `pyproject.toml`, including development tools like `ruff`, `black`, and `pytest`.
- Install pre-commit hooks to ensure code quality.

Activate the virtual environment to use the installed tools:
```bash
source .venv/bin/activate
```

### 2. Environment Variables

The application uses a `.env` file for configuration. Copy the example file to get started:

```bash
cp .env.example .env
```

Modify the `.env` file as needed for your local setup (e.g., database connections, API keys). The default settings are configured for local development.

### 3. Running Linters and Formatters

To ensure code quality, you can run the linter and formatter:

```bash
# Check for linting and formatting issues
make lint

# Automatically fix formatting and simple linting issues
make fmt
```

### 4. Running Tests

To run the test suite:

```bash
make test
```
*(Note: The test suite is currently empty, so this command will report that no tests were run.)*

### 5. Database Migrations

The project uses Alembic to manage database schema migrations.

To apply the latest migrations:
```bash
make db_migrate
```