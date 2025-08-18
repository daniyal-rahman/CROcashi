# src/ncfd/ingest/securities.py
from __future__ import annotations
from datetime import date
from typing import Any, Optional

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB


class ExchangeNotAllowed(ValueError):
    pass


def _resolve_allowed_exchange_id(session: Session, exchange_code: str) -> int:
    """Return exchange_id for an allowed exchange, else raise ExchangeNotAllowed."""
    row = session.execute(
        text(
            """
            SELECT exchange_id, is_allowed
            FROM exchanges
            WHERE code = :code
            """
        ),
        {"code": exchange_code},
    ).mappings().first()

    if not row:
        raise ExchangeNotAllowed(f"Exchange '{exchange_code}' not found")
    if not row["is_allowed"]:
        raise ExchangeNotAllowed(f"Exchange '{exchange_code}' is not allowed")

    return int(row["exchange_id"])


def upsert_security_active(
    session: Session,
    *,
    company_id: int,
    exchange_code: str,
    ticker: str,
    effective_date: date,
    sec_type: str = "common",  # maps to postgres enum security_type
    currency: str = "USD",
    figi: Optional[str] = None,
    cik: Optional[int] = None,
    is_primary_listing: bool = True,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    """
    Make `ticker` active for (company_id, exchange_code) starting `effective_date`.

    Steps:
      1) resolve exchange_id (must be is_allowed = true),
      2) idempotency: if the exact active listing already exists with the same start date, return it,
      3) close any existing open rows for this ticker whose start <= effective_date
         (mark active ones as delisted) to avoid overlap / unique violations,
      4) insert new active row [effective_date, ∞).

    Returns the active security_id.
    """
    ticker_norm = ticker.upper()
    exchange_id = _resolve_allowed_exchange_id(session, exchange_code)

    # 2) Idempotency: same company/exchange/ticker already active with same start date?
    existing_same_span = session.execute(
        text(
            """
            SELECT security_id
            FROM securities
            WHERE ticker_norm = :tn
              AND status = 'active'
              AND company_id = :cid
              AND exchange_id = :xid
              AND upper_inf(effective_range)
              AND lower(effective_range) = :start_date
            """
        ),
        {"tn": ticker_norm, "cid": company_id, "xid": exchange_id, "start_date": effective_date},
    ).scalar()
    if existing_same_span:
        return int(existing_same_span)

    # 3) Close any open slice (active or not) that started before :start_date,
    #    mark active ones as delisted, and annotate metadata.
    session.execute(
        text(
            """
            UPDATE securities
            SET
              status = CASE WHEN status = 'active' THEN 'delisted' ELSE status END,
              effective_range = daterange(lower(effective_range), :start_date, '[)'),
              updated_at = NOW(),
              metadata = COALESCE(metadata, '{}'::jsonb)
                         || jsonb_build_object('auto_closed_on', CAST(:start_date AS date))
            WHERE ticker_norm = :tn
              AND upper_inf(effective_range)
              AND lower(effective_range) <= :start_date
            """
        ),
        {"tn": ticker_norm, "start_date": effective_date},
    )

    # 4) Defensive: if there are *non-active* open rows that still overlap
    #    the new active window [start, ∞), trim them too.
    session.execute(
        text(
            """
            UPDATE securities
            SET effective_range = daterange(lower(effective_range), :start_date, '[)'),
                updated_at = NOW()
            WHERE ticker_norm = :tn
              AND status <> 'active'
              AND upper(effective_range) IS NULL
              AND effective_range && daterange(:start_date, NULL, '[)')
            """
        ),
        {"tn": ticker_norm, "start_date": effective_date},
    )
        # 4) Insert the new active row
    insert_sql = (
        text(
            """
            INSERT INTO securities(
                company_id, exchange_id, ticker, ticker_norm,
                type, status, is_primary_listing,
                effective_range, currency, figi, cik, metadata
            )
            VALUES (
                :company_id, :exchange_id, :ticker, upper(:ticker),
                CAST(:sec_type AS security_type), 'active'::security_status, :is_primary,
                daterange(:start_date, NULL, '[)'), :currency, :figi, :cik,
                COALESCE(:metadata, '{}'::jsonb)
            )
            RETURNING security_id
            """
        ).bindparams(bindparam("metadata", type_=JSONB))
    )

    security_id = session.execute(
        insert_sql,
        {
            "company_id": company_id,
            "exchange_id": exchange_id,
            "ticker": ticker,
            "sec_type": sec_type,
            "is_primary": is_primary_listing,
            "start_date": effective_date,
            "currency": currency,
            "figi": figi,
            "cik": cik,
            "metadata": metadata or {},
        },
    ).scalar_one()

    return int(security_id)


def deactivate_security(
    session: Session,
    *,
    ticker: str,
    end_date: date,
    set_status: str = "delisted",
) -> int:
    """
    Close any open effective_range for this ticker by setting an end_date and
    insert a zero-length marker row at end_date with the given status (default 'delisted').
    Returns number of affected rows from the close step (0 or 1).
    """
    # 1) Close the current open slice AND set its status
    close_sql = text(
        """
        WITH current AS (
            SELECT security_id
            FROM securities
            WHERE ticker_norm = upper(:tkr)
              AND upper_inf(effective_range)
              AND lower(effective_range) < :end_date
            LIMIT 1
        )
        UPDATE securities s
        SET effective_range = daterange(lower(s.effective_range), :end_date, '[)'),
            status = CAST(:status AS security_status),
            updated_at = NOW()
        FROM current
        WHERE s.security_id = current.security_id
        RETURNING s.security_id
        """
    )
    closed = session.execute(
        close_sql, {"tkr": ticker, "end_date": end_date, "status": set_status}
    ).fetchall()

    # 2) Insert a zero-length marker row at end_date (empty range doesn't overlap by gist '&&')
    if closed:
        insert_marker = text(
            """
            INSERT INTO securities(
                company_id, exchange_id, ticker, ticker_norm,
                type, status, is_primary_listing,
                effective_range, currency, figi, cik, metadata
            )
            SELECT
                s.company_id, s.exchange_id, s.ticker, s.ticker_norm,
                s.type, CAST(:status AS security_status), s.is_primary_listing,
                daterange(:end_date, :end_date, '[)'),
                s.currency, s.figi, s.cik, s.metadata
            FROM securities s
            WHERE s.security_id = :sid
            """
        )
        session.execute(
            insert_marker,
            {"sid": closed[0][0], "end_date": end_date, "status": set_status},
        )

    return len(closed)


def transfer_ticker_ownership(
    session: Session,
    *,
    from_company_id: int,
    to_company_id: int,
    exchange_code: str,
    ticker: str,
    effective_date: date,
    currency: str = "USD",
) -> int:
    """
    Convenience: close any open ranges (owned by `from_company_id` or others),
    then create a new active listing for `to_company_id` on `exchange_code`.
    Returns the new security_id.
    """
    # Close open ranges first (for this ticker only)
    deactivate_security(
        session, ticker=ticker, end_date=effective_date, set_status="delisted"
    )

    # Insert new active
    return upsert_security_active(
        session,
        company_id=to_company_id,
        exchange_code=exchange_code,
        ticker=ticker,
        effective_date=effective_date,
        sec_type="common",
        currency=currency,
        is_primary_listing=True,
    )
