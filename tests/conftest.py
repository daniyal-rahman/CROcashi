# tests/conftest.py
import os
import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event

# Import environment loader
try:
    from tests.utils.env_loader import setup_test_environment, get_test_env
except ImportError:
    # Fallback for when running tests directly
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from utils.env_loader import setup_test_environment, get_test_env


# Load environment variables before any tests run
setup_test_environment()


@pytest.fixture(scope="session", autouse=True)
def ensure_test_env():
    """Ensure test environment variables are set up for all tests."""
    # This fixture runs once per test session and ensures env vars are loaded
    setup_test_environment()
    yield
    # Cleanup if needed


@pytest.fixture
def test_env():
    """Provide access to test environment variables."""
    return get_test_env()


@pytest.fixture
def session():
    import ncfd.db.session as dbs

    engine = getattr(dbs, "engine", None) or dbs.get_engine()
    conn = engine.connect()
    outer = conn.begin()  # one outer transaction per test

    Session = sessionmaker(bind=conn, autoflush=False, autocommit=False)
    s = Session()

    # start a SAVEPOINT so test code can call commit() freely
    s.begin_nested()

    @event.listens_for(s, "after_transaction_end")
    def restart_savepoint(sess, trans):
        # option A: check the real Connection correctly
        if trans.nested and not sess.connection().closed:
            sess.begin_nested()

        # (Alternatively, the classic pattern is:)
        # if trans.nested and not trans._parent.nested:
        #     sess.begin_nested()

    try:
        yield s
    finally:
        s.close()
        outer.rollback()   # <<< important: discard everything done in the test
        conn.close()
