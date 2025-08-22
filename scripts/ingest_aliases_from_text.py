# scripts/ingest_aliases_from_text.py
import sys
import argparse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ncfd.ingest.aliases import ingest_aliases_from_text, AliasInput

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=None, help="DATABASE_URL (overrides env)")
    p.add_argument("--company-id", type=int, required=True)
    p.add_argument("--source", default="8-K")
    p.add_argument("--source-url", default=None)
    p.add_argument("--file", required=True, help="Text file containing filing text")
    args = p.parse_args()

    with open(args.file, "r") as f:
        text = f.read()

    engine = create_engine(args.db or "", future=True)
    with Session(engine) as s, s.begin():
        stats = ingest_aliases_from_text(s, [
            AliasInput(company_id=args.company_id, text=text, source=args.source, source_url=args.source_url)
        ])
        print(stats)

if __name__ == "__main__":
    main()
