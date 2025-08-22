# tests/conftest.py
import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event

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
