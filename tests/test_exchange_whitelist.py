import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from ncfd.ingest.exchanges import ExchangeRow, upsert_exchanges

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, future=True)

def test_upsert_blocks_cn_hk():
    with Session(engine) as s, s.begin():
        stats = upsert_exchanges(
            s,
            rows=[
                ExchangeRow(code="HKX", mic="XHKX", name="HK Test Exch", country="HK", is_allowed=True),
                ExchangeRow(code="CNSH", mic="XSHG", name="Shanghai Test", country="CN", is_allowed=True),
                ExchangeRow(code="USX", mic="XUSX", name="US Test", country="US", is_allowed=True),
            ],
            disallowed_countries=("CN", "HK"),
        )
        assert stats["upserted"] == 3
        assert stats["forced_disallowed"] == 2

    with engine.begin() as c:
        # CN/HK should never be marked allowed
        bad = c.execute(text("""
            SELECT code FROM exchanges
            WHERE country IN ('CN','HK') AND is_allowed = TRUE
        """)).fetchall()
        assert bad == []

        # US row should be allowed
        ok = c.execute(text("SELECT is_allowed FROM exchanges WHERE code='USX'")).scalar_one()
        assert ok is True
