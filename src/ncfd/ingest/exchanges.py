# src/ncfd/ingest/exchanges.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Sequence
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import JSONB

@dataclass(frozen=True)
class ExchangeRow:
    code: str
    mic: str | None
    name: str
    country: str = "US"
    is_allowed: bool = True
    metadata: dict | None = None

def upsert_exchanges(
    session: Session,
    rows: Sequence[ExchangeRow],
    disallowed_countries: Iterable[str] = ("CN", "HK"),
) -> dict:
    """
    Upsert exchanges; force `is_allowed = false` for disallowed countries
    (e.g., CN/HK), regardless of input.
    Returns counts: {"upserted": int, "forced_disallowed": int}
    """
    disallowed = {c.upper() for c in disallowed_countries}
    upserted = 0
    forced = 0

    sql = (
        text("""
        INSERT INTO exchanges(code, mic, name, country, is_allowed, metadata)
        VALUES (:code, :mic, :name, :country, :is_allowed, COALESCE(:metadata, '{}'::jsonb))
        ON CONFLICT (code) DO UPDATE SET
          mic        = EXCLUDED.mic,
          name       = EXCLUDED.name,
          country    = EXCLUDED.country,
          is_allowed = EXCLUDED.is_allowed,
          metadata   = EXCLUDED.metadata
        """)
        # <-- Make sure :metadata is treated as JSONB, not a plain Python dict
        .bindparams(bindparam("metadata", type_=JSONB))
    )

    for r in rows:
        is_allowed = bool(r.is_allowed) and (r.country or "US").upper() not in disallowed
        if r.is_allowed and not is_allowed:
            forced += 1

        session.execute(sql, {
            "code": r.code,
            "mic": r.mic,
            "name": r.name,
            "country": r.country or "US",
            "is_allowed": is_allowed,
            "metadata": r.metadata or {},
        })
        upserted += 1

    return {"upserted": upserted, "forced_disallowed": forced}

# Optional CLI (only needed if you want to drive it via a file)
def _load_from_yaml(path: str) -> tuple[list[ExchangeRow], list[str]]:
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise RuntimeError("pyyaml is required to load YAML files") from e

    with open(path, "r", encoding="utf-8") as f:
        conf = yaml.safe_load(f)

    rows = []
    for x in conf.get("exchanges", []):
        rows.append(ExchangeRow(
            code=x["code"],
            mic=x.get("mic"),
            name=x["name"],
            country=x.get("country", "US"),
            is_allowed=bool(x.get("is_allowed", True)),
            metadata=x.get("metadata") or {},
        ))
    disallowed = conf.get("disallowed_countries", ["CN", "HK"])
    return rows, disallowed

if __name__ == "__main__":
    # usage: python -m ncfd.ingest.exchanges config/exchanges.yml
    import os, sys
    from sqlalchemy import create_engine
    if len(sys.argv) != 2:
        print("usage: python -m ncfd.ingest.exchanges <exchanges.yml>")
        sys.exit(2)

    rows, disallowed = _load_from_yaml(sys.argv[1])
    db_url = os.environ["DATABASE_URL"]
    eng = create_engine(db_url, future=True)
    from sqlalchemy.orm import Session
    with Session(eng) as s, s.begin():
        stats = upsert_exchanges(s, rows, disallowed)
    print(f"Upserted: {stats['upserted']}, forced_disallowed: {stats['forced_disallowed']}")
