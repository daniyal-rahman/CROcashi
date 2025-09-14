# Coding Standards

This document outlines the coding standards and best practices for the CROcashi project.

## 🚨 Critical Rules

### 1. Timezone Handling
- **ALWAYS** use `datetime.now(timezone.utc)` instead of `datetime.now()`
- **NEVER** use naive datetime objects in production code
- Use `datetime.now(timezone.utc)` for all datetime operations

```python
# ✅ Correct
from datetime import datetime, timezone
now = datetime.now(timezone.utc)

# ❌ Wrong
now = datetime.now()  # Naive datetime
```

### 2. Security
- **NEVER** use MD5 for security purposes (checksums, hashing)
- **ALWAYS** use SHA-256 or stronger for cryptographic operations
- **NEVER** hardcode secrets or API keys

```python
# ✅ Correct
import hashlib
checksum = hashlib.sha256(content).hexdigest()

# ❌ Wrong
checksum = hashlib.md5(content).hexdigest()  # Cryptographically broken
```

### 3. Logging
- **NEVER** use `print()` for debug output in production code
- **ALWAYS** use proper logging with appropriate levels
- **ALWAYS** include context in log messages

```python
# ✅ Correct
import logging
logger = logging.getLogger(__name__)
logger.debug("Processing trial %s", trial_id)
logger.warning("Validation failed for %s", field_name)

# ❌ Wrong
print(f"DEBUG: Processing trial {trial_id}")
```

## 📝 Code Style

### 1. Formatting
- Use Black with 88 character line length
- Use isort for import organization
- Follow PEP 8 for general style

### 2. Naming Conventions
- Use snake_case for functions and variables
- Use PascalCase for classes
- Use UPPER_CASE for constants
- Use descriptive names that explain purpose

```python
# ✅ Good
def calculate_trial_risk_score(trial_data):
    pass

class TrialRiskCalculator:
    pass

MAX_RETRY_ATTEMPTS = 3

# ❌ Bad
def calc(td):
    pass

class calc:
    pass

max = 3
```

### 3. Function Design
- Keep functions under 50 lines when possible
- Single responsibility principle
- Clear input/output contracts
- Proper error handling

```python
# ✅ Good
def validate_trial_data(trial_data: Dict[str, Any]) -> ValidationResult:
    """Validate trial data and return detailed results."""
    if not trial_data:
        raise ValueError("Trial data cannot be empty")
    
    errors = []
    # ... validation logic
    
    return ValidationResult(errors=errors, is_valid=len(errors) == 0)

# ❌ Bad
def validate(td):
    # 100+ lines of mixed validation logic
    pass
```

## 🔧 Error Handling

### 1. Exception Handling
- Use specific exceptions, not generic `except Exception`
- Always log errors with context
- Don't suppress exceptions without good reason

```python
# ✅ Good
try:
    result = process_data(data)
except ValueError as e:
    logger.error("Invalid data format: %s", e)
    raise
except ConnectionError as e:
    logger.error("Database connection failed: %s", e)
    raise

# ❌ Bad
try:
    result = process_data(data)
except Exception as e:
    pass  # Silent failure
```

### 2. Validation
- Validate inputs at function boundaries
- Use type hints for better IDE support
- Provide clear error messages

```python
# ✅ Good
def process_trial(trial_id: str, data: Dict[str, Any]) -> TrialResult:
    if not trial_id:
        raise ValueError("Trial ID cannot be empty")
    if not isinstance(data, dict):
        raise TypeError("Data must be a dictionary")
    
    # ... processing logic

# ❌ Bad
def process_trial(trial_id, data):
    # No validation
    pass
```

## 🗄️ Database

### 1. Models
- Use SQLAlchemy with proper type hints
- Include proper indexes for performance
- Use foreign keys for referential integrity
- Never duplicate column definitions

```python
# ✅ Good
class Trial(Base):
    __tablename__ = "trials"
    
    trial_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nct_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )

# ❌ Bad
class Trial(Base):
    __tablename__ = "trials"
    
    trial_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trial_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # Duplicate!
```

### 2. Queries
- Use parameterized queries to prevent SQL injection
- Add proper error handling for database operations
- Use transactions for multi-step operations

## 🧪 Testing

### 1. Test Structure
- Use pytest for testing
- Write tests for all public functions
- Use descriptive test names
- Mock external dependencies

```python
# ✅ Good
def test_calculate_trial_risk_with_valid_data():
    """Test risk calculation with valid trial data."""
    trial_data = {"phase": "3", "sample_size": 1000}
    result = calculate_trial_risk(trial_data)
    assert result.risk_score > 0
    assert result.risk_score <= 1

# ❌ Bad
def test_calc():
    result = calc(data)
    assert result > 0
```

### 2. Test Coverage
- Aim for >80% code coverage
- Test both success and failure cases
- Test edge cases and boundary conditions

## 📚 Documentation

### 1. Docstrings
- Use Google-style docstrings
- Include type hints
- Document exceptions
- Provide usage examples

```python
def calculate_trial_risk(trial_data: Dict[str, Any]) -> RiskResult:
    """Calculate risk score for a clinical trial.
    
    Args:
        trial_data: Dictionary containing trial information
            - phase: Trial phase (1, 2, 3, 4)
            - sample_size: Number of participants
            - indication: Disease indication
            
    Returns:
        RiskResult with calculated risk score and confidence
        
    Raises:
        ValueError: If trial_data is missing required fields
        TypeError: If trial_data is not a dictionary
        
    Example:
        >>> data = {"phase": "3", "sample_size": 1000}
        >>> result = calculate_trial_risk(data)
        >>> print(f"Risk: {result.risk_score:.2f}")
        Risk: 0.75
    """
```

### 2. README Files
- Keep README files up to date
- Include setup instructions
- Document configuration options
- Provide usage examples

## 🔄 Code Review Checklist

Before submitting code for review, ensure:

- [ ] All tests pass
- [ ] No debug print statements
- [ ] Proper timezone handling
- [ ] No MD5 usage
- [ ] Proper error handling
- [ ] Type hints included
- [ ] Docstrings updated
- [ ] Code formatted with Black
- [ ] Imports sorted with isort
- [ ] No duplicate code
- [ ] Functions are reasonably sized
- [ ] Variable names are descriptive
- [ ] No hardcoded secrets

## 🛠️ Tools

### Pre-commit Hooks
The project uses pre-commit hooks to enforce these standards:

- Black: Code formatting
- isort: Import sorting
- flake8: Linting
- bandit: Security checks
- mypy: Type checking
- Custom hooks for datetime, MD5, and debug prints

### Setup
```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## 📈 Continuous Improvement

- Regularly review and update these standards
- Collect feedback from team members
- Monitor code quality metrics
- Address technical debt promptly

## 🆘 Getting Help

If you have questions about these standards:

1. Check this document first
2. Ask in team chat
3. Schedule a code review session
4. Create an issue for clarification

Remember: These standards exist to make our code more maintainable, secure, and reliable. Following them benefits everyone on the team!
