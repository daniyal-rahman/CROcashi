# ncfd/scripts/print_db_info.py
from sqlalchemy import text
from ncfd.db import get_session
from ncfd.mapping.det import det_resolve

def main():
    with get_session() as s:
        bind = s.get_bind()
        print("DB URL:", str(bind.url))
        print("search_path:", s.execute(text("SHOW search_path")).scalar())

        try:
            n = s.execute(text("select count(*) from resolver_det_rules")).scalar()
            print("resolver_det_rules count:", n)
        except Exception as e:
            print("resolver_det_rules error:", e)

        for t in ["Hoffmann-La Roche", "Genentech, Inc.", "Roche", "Genentech Inc", "NCI"]:
            d = det_resolve(s, t)
            print(f"det_resolve({t!r}) ->", getattr(d, "method", None), getattr(d, "company_id", None))

if __name__ == "__main__":
    main()
