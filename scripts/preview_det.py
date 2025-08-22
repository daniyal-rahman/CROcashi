#!/usr/bin/env python
import os
from contextlib import contextmanager

try:
    from ncfd.db.session import get_session  # preferred
except Exception:
    try:
        from ncfd.db import get_session
    except Exception:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        _DSN = os.environ.get(
            "PSQL_DSN",
            "postgresql+psycopg2://ncfd:ncfd@127.0.0.1:/ncfd",
        )
        _engine = create_engine(_DSN, pool_pre_ping=True)
        _Session = sessionmaker(bind=_engine)

        @contextmanager
        def get_session():
            s = _Session()
            try:
                yield s
            finally:
                s.close()

from sqlalchemy import text
from ncfd.mapping.det import det_resolve

def main():
    with get_session() as s:
        # Show rules loaded
        try:
            rules = s.execute(text("SELECT pattern, company_id, priority FROM resolver_det_rules ORDER BY priority, pattern")).fetchall()
            print(f"Loaded {len(rules)} det rules")
        except Exception as e:
            print("resolver_det_rules not found:", e)

        samples = [
            "Genentech, Inc.",
            "F. Hoffmann-La Roche Ltd",
            "Hoffmann-La Roche",
            "Roche",
            "Genentech Inc",
        ]
        for t in samples:
            det = det_resolve(s, t)
            if det:
                print(f"[det] {t!r} -> cid={det.company_id} method={det.method}")
            else:
                print(f"[det] {t!r} -> no deterministic match")

if __name__ == "__main__":
    main()
