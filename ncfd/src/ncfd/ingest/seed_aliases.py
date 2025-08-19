# ncfd/src/ncfd/ingest/seed_aliases.py
from sqlalchemy import text
from ncfd.db.session import get_session
from ncfd.mapping.normalize import norm_name

def run():
    with get_session() as s:
        rows = s.execute(text("""
            SELECT c.company_id, c.name
            FROM companies c
            LEFT JOIN company_aliases a
              ON a.company_id = c.company_id AND a.alias_type = 'legal'
            WHERE a.company_id IS NULL
        """)).fetchall()

        inserted = 0
        for cid, name in rows:
            n = norm_name(name or "")
            if not n:
                continue
            s.execute(text("""
                INSERT INTO company_aliases (company_id, alias_type, alias, alias_norm, source)
                VALUES (:cid, 'legal', :alias, :alias_norm, 'seed-legal')
                ON CONFLICT (company_id, alias_norm, alias_type) DO NOTHING
            """), {"cid": cid, "alias": name[:500], "alias_norm": n})
            inserted += 1
        print(f"seeded legal aliases: {inserted}")

if __name__ == "__main__":
    run()
