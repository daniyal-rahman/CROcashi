"""
SEC CIK-Ticker mapping ingestion.

Downloads the SEC company_tickers.json file and matches CIKs/tickers
to existing companies in the database using fuzzy matching.
"""
import json
import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fuzzywuzzy import fuzz
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.config import SessionLocal
from database.models import Company, CompanyTicker
from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient

logger = logging.getLogger(__name__)

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def fetch_sec_tickers(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Fetch the SEC company_tickers.json file.

    This file contains CIK -> ticker mappings for all SEC-registered companies.

    Args:
        save_dir: Optional directory to save the raw JSON file

    Returns:
        Dictionary with ticker data from SEC
    """
    client = HttpClient(
        requests_per_second=1.0,
        user_agent="CROcashi-Ingestion contact@example.com"
    )

    logger.info(f"Fetching SEC tickers from {SEC_TICKERS_URL}")
    resp = client.get(SEC_TICKERS_URL)
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "sec_company_tickers.json", resp.text)
        logger.info(f"Saved SEC tickers to {save_dir}/sec_company_tickers.json")

    return data


def parse_sec_tickers(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse the SEC tickers JSON into a list of company records.

    The SEC JSON format is:
    {
        "0": {"cik_str": 1234, "ticker": "AAPL", "title": "APPLE INC"},
        "1": {"cik_str": 5678, "ticker": "MSFT", "title": "MICROSOFT CORP"},
        ...
    }

    Args:
        data: Raw JSON data from SEC

    Returns:
        List of dicts with cik, ticker, and company_name keys
    """
    records = []

    for key, entry in data.items():
        if isinstance(entry, dict):
            cik = entry.get('cik_str')
            ticker = entry.get('ticker')
            title = entry.get('title', '')

            if cik and ticker:
                records.append({
                    'cik': str(cik).zfill(10),  # Zero-pad to 10 digits
                    'ticker': ticker.upper(),
                    'company_name': title.upper()
                })

    logger.info(f"Parsed {len(records)} ticker records from SEC data")
    return records


def normalize_company_name(name: str) -> str:
    """
    Normalize company name for matching.

    - Uppercase
    - Remove common suffixes (INC, CORP, LLC, etc.)
    - Remove punctuation
    """
    if not name:
        return ""

    name = name.upper().strip()

    # Remove common suffixes
    suffixes = [
        ' INC', ' INCORPORATED', ' CORP', ' CORPORATION',
        ' LLC', ' LP', ' LTD', ' LIMITED', ' PLC',
        ' CO', ' COMPANY', ' HOLDINGS', ' GROUP',
        ' PHARMACEUTICALS', ' PHARMA', ' THERAPEUTICS', ' BIOSCIENCES',
        ' BIOPHARMA', ' BIOTECH', ' BIOTECHNOLOGY'
    ]

    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]

    # Remove punctuation
    name = ''.join(c for c in name if c.isalnum() or c.isspace())

    # Collapse whitespace
    name = ' '.join(name.split())

    return name


def build_company_index(
    db_companies: List[Tuple[uuid.UUID, str, Optional[str]]]
) -> Tuple[Dict[str, Tuple[uuid.UUID, str]], List[Tuple[uuid.UUID, str, str]]]:
    """
    Build lookup indexes for fast company matching.

    Returns:
        ticker_index: Dict mapping uppercase ticker to (company_id, name)
        normalized_companies: List of (company_id, name, normalized_name)
    """
    ticker_index = {}
    normalized_companies = []

    for company_id, db_name, existing_ticker in db_companies:
        # Build ticker index
        if existing_ticker:
            ticker_index[existing_ticker.upper()] = (company_id, db_name)

        # Pre-compute normalized names
        normalized_name = normalize_company_name(db_name)
        normalized_companies.append((company_id, db_name, normalized_name))

    return ticker_index, normalized_companies


def match_company(
    sec_record: Dict[str, Any],
    ticker_index: Dict[str, Tuple[uuid.UUID, str]],
    normalized_companies: List[Tuple[uuid.UUID, str, str]],
    min_score: int = 85
) -> Optional[Tuple[uuid.UUID, str, int]]:
    """
    Match a SEC ticker record to a database company using fuzzy matching.

    Args:
        sec_record: Dict with 'cik', 'ticker', 'company_name' from SEC
        ticker_index: Dict mapping uppercase ticker to (company_id, name)
        normalized_companies: List of (company_id, name, normalized_name)
        min_score: Minimum fuzzy match score (0-100) required

    Returns:
        Tuple of (company_id, company_name, match_score) or None if no match
    """
    sec_ticker = sec_record['ticker']

    # Fast path: exact ticker match via O(1) lookup
    if sec_ticker in ticker_index:
        company_id, db_name = ticker_index[sec_ticker]
        return (company_id, db_name, 100)

    # Slow path: fuzzy name matching
    sec_name = normalize_company_name(sec_record['company_name'])

    # Early exit if SEC name is too short for meaningful matching
    if len(sec_name) < 3:
        return None

    best_match = None
    best_score = 0

    for company_id, db_name, db_name_normalized in normalized_companies:
        # Skip if normalized names have very different lengths (unlikely to match)
        len_diff = abs(len(sec_name) - len(db_name_normalized))
        if len_diff > max(len(sec_name), len(db_name_normalized)) * 0.5:
            continue

        # Try multiple fuzzy matching strategies
        score1 = fuzz.ratio(sec_name, db_name_normalized)

        # Only compute token_set_ratio if ratio is promising
        if score1 >= min_score - 15:
            score2 = fuzz.token_set_ratio(sec_name, db_name_normalized)
            score = max(score1, score2)
        else:
            score = score1

        if score > best_score:
            best_score = score
            best_match = (company_id, db_name, score)

            # Early exit if we found a very high quality match
            if best_score >= 98:
                break

    if best_match and best_score >= min_score:
        return best_match

    return None


def ingest_sec_tickers(
    session: Optional[Session] = None,
    save_raw: bool = True,
    min_match_score: int = 85,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Ingest SEC CIK-ticker mappings and match to existing companies.

    This function:
    1. Fetches the SEC company_tickers.json file
    2. Loads all existing companies from the database
    3. Fuzzy matches SEC companies to DB companies
    4. Creates CompanyTicker records for matched companies

    Args:
        session: SQLAlchemy session (creates new if None)
        save_raw: Whether to save the raw JSON file
        min_match_score: Minimum fuzzy match score (0-100) for matching
        dry_run: If True, don't actually insert records

    Returns:
        Statistics dict with matched, unmatched, etc.
    """
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        # Fetch SEC data
        save_dir = Path("data/raw/sec_cik_ticker") if save_raw else None
        sec_data = fetch_sec_tickers(save_dir=save_dir)
        sec_records = parse_sec_tickers(sec_data)

        # Load existing companies
        logger.info("Loading existing companies from database...")
        db_companies = session.query(
            Company.company_id,
            Company.name,
            Company.ticker
        ).filter(
            Company.deleted_at.is_(None)
        ).all()

        logger.info(f"Found {len(db_companies)} companies in database")

        # Load existing tickers to avoid duplicates
        existing_tickers = session.query(
            CompanyTicker.company_id,
            CompanyTicker.ticker,
            CompanyTicker.cik
        ).filter(
            CompanyTicker.deleted_at.is_(None),
            CompanyTicker.valid_until.is_(None)  # Only current tickers
        ).all()

        existing_ticker_set = {(str(t.company_id), t.ticker) for t in existing_tickers}
        existing_cik_set = {t.cik for t in existing_tickers if t.cik}

        logger.info(f"Found {len(existing_tickers)} existing ticker mappings")

        # Build company index for fast matching
        logger.info("Building company matching index...")
        ticker_index, normalized_companies = build_company_index(db_companies)
        logger.info(f"Built index with {len(ticker_index)} ticker entries")

        # Match SEC records to companies
        stats = {
            'total_sec_records': len(sec_records),
            'matched': 0,
            'unmatched': 0,
            'inserted': 0,
            'skipped_existing': 0,
            'errors': 0,
            'unmatched_companies': []
        }

        new_tickers = []
        today = date.today()

        for i, sec_record in enumerate(sec_records):
            # Progress logging every 1000 records
            if (i + 1) % 1000 == 0:
                logger.info(f"Processed {i + 1}/{len(sec_records)} SEC records...")

            # Skip if CIK already exists
            if sec_record['cik'] in existing_cik_set:
                stats['skipped_existing'] += 1
                continue

            match = match_company(sec_record, ticker_index, normalized_companies, min_match_score)

            if match:
                company_id, company_name, score = match

                # Skip if this company-ticker combo already exists
                if (str(company_id), sec_record['ticker']) in existing_ticker_set:
                    stats['skipped_existing'] += 1
                    continue

                stats['matched'] += 1

                # Create ticker record
                ticker_record = CompanyTicker(
                    ticker_id=uuid.uuid4(),
                    company_id=company_id,
                    ticker=sec_record['ticker'],
                    cik=sec_record['cik'],
                    exchange=None,  # Could be enriched later
                    valid_from=today,
                    valid_until=None,
                    is_primary=True,
                    data_sources={
                        'source': 'sec_company_tickers',
                        'match_score': score,
                        'sec_company_name': sec_record['company_name'],
                        'matched_to': company_name,
                        'ingested_at': today.isoformat()
                    }
                )
                new_tickers.append(ticker_record)

                logger.debug(
                    f"Matched: {sec_record['ticker']} ({sec_record['company_name']}) "
                    f"-> {company_name} (score: {score})"
                )
            else:
                stats['unmatched'] += 1
                if len(stats['unmatched_companies']) < 100:  # Limit size
                    stats['unmatched_companies'].append({
                        'cik': sec_record['cik'],
                        'ticker': sec_record['ticker'],
                        'name': sec_record['company_name']
                    })

        # Insert new tickers
        if not dry_run and new_tickers:
            logger.info(f"Inserting {len(new_tickers)} new ticker mappings...")
            for ticker in new_tickers:
                try:
                    session.add(ticker)
                    stats['inserted'] += 1
                except Exception as e:
                    logger.error(f"Error inserting ticker {ticker.ticker}: {e}")
                    stats['errors'] += 1

            session.commit()
            logger.info(f"Committed {stats['inserted']} ticker mappings")
        elif dry_run:
            logger.info(f"[DRY RUN] Would insert {len(new_tickers)} ticker mappings")
            stats['inserted'] = len(new_tickers)

        # Log summary
        logger.info(
            f"SEC ticker ingestion complete: "
            f"{stats['matched']} matched, "
            f"{stats['unmatched']} unmatched, "
            f"{stats['inserted']} inserted, "
            f"{stats['skipped_existing']} skipped (existing)"
        )

        return stats

    except Exception as e:
        logger.error(f"Error during SEC ticker ingestion: {e}")
        session.rollback()
        raise

    finally:
        if close_session:
            session.close()


def get_company_by_ticker(
    ticker: str,
    session: Optional[Session] = None,
    as_of_date: Optional[date] = None
) -> Optional[Company]:
    """
    Look up a company by ticker symbol.

    Args:
        ticker: Stock ticker symbol
        session: SQLAlchemy session (creates new if None)
        as_of_date: Optional date for point-in-time lookup

    Returns:
        Company object or None if not found
    """
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        query = session.query(Company).join(
            CompanyTicker,
            Company.company_id == CompanyTicker.company_id
        ).filter(
            CompanyTicker.ticker == ticker.upper(),
            CompanyTicker.deleted_at.is_(None),
            Company.deleted_at.is_(None)
        )

        if as_of_date:
            query = query.filter(
                CompanyTicker.valid_from <= as_of_date,
                (CompanyTicker.valid_until.is_(None) | (CompanyTicker.valid_until > as_of_date))
            )
        else:
            query = query.filter(CompanyTicker.valid_until.is_(None))

        return query.first()

    finally:
        if close_session:
            session.close()


def get_company_by_cik(
    cik: str,
    session: Optional[Session] = None
) -> Optional[Company]:
    """
    Look up a company by SEC CIK.

    Args:
        cik: SEC Central Index Key
        session: SQLAlchemy session (creates new if None)

    Returns:
        Company object or None if not found
    """
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        # Normalize CIK
        cik_padded = str(int(cik)).zfill(10)

        return session.query(Company).join(
            CompanyTicker,
            Company.company_id == CompanyTicker.company_id
        ).filter(
            CompanyTicker.cik == cik_padded,
            CompanyTicker.deleted_at.is_(None),
            Company.deleted_at.is_(None)
        ).first()

    finally:
        if close_session:
            session.close()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description="Ingest SEC CIK-ticker mappings")
    parser.add_argument('--dry-run', action='store_true', help="Don't actually insert records")
    parser.add_argument('--min-score', type=int, default=85, help="Minimum fuzzy match score (0-100)")
    parser.add_argument('--no-save', action='store_true', help="Don't save raw JSON file")
    args = parser.parse_args()

    stats = ingest_sec_tickers(
        save_raw=not args.no_save,
        min_match_score=args.min_score,
        dry_run=args.dry_run
    )

    print("\n=== SEC CIK-Ticker Ingestion Results ===")
    print(f"Total SEC records: {stats['total_sec_records']}")
    print(f"Matched to DB companies: {stats['matched']}")
    print(f"Unmatched: {stats['unmatched']}")
    print(f"Inserted: {stats['inserted']}")
    print(f"Skipped (already exist): {stats['skipped_existing']}")
    print(f"Errors: {stats['errors']}")

    if stats['unmatched_companies'][:10]:
        print("\nSample unmatched companies:")
        for c in stats['unmatched_companies'][:10]:
            print(f"  {c['ticker']}: {c['name']} (CIK: {c['cik']})")
