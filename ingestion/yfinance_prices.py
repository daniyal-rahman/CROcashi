"""
yfinance stock price ingestion.

Downloads historical stock prices for all companies with ticker mappings
and stores them in the stock_prices table with pre-computed metrics.
"""
import logging
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import yfinance as yf
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from database.config import SessionLocal
from database.models import Company, CompanyTicker, StockPrice

logger = logging.getLogger(__name__)


def get_tickers_to_fetch(
    session: Session,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get list of tickers that need price data fetched.

    Returns tickers that have company_tickers mappings and are currently active.

    Args:
        session: SQLAlchemy session
        limit: Optional limit on number of tickers to return

    Returns:
        List of dicts with company_id, ticker, company_name
    """
    query = session.query(
        CompanyTicker.company_id,
        CompanyTicker.ticker,
        Company.name.label('company_name')
    ).join(
        Company,
        CompanyTicker.company_id == Company.company_id
    ).filter(
        CompanyTicker.deleted_at.is_(None),
        CompanyTicker.valid_until.is_(None),  # Only current tickers
        CompanyTicker.is_primary == True,  # Only primary tickers
        Company.deleted_at.is_(None)
    ).distinct(
        CompanyTicker.company_id  # One ticker per company
    )

    if limit:
        query = query.limit(limit)

    results = query.all()
    return [
        {
            'company_id': r.company_id,
            'ticker': r.ticker,
            'company_name': r.company_name
        }
        for r in results
    ]


def get_latest_price_date(
    session: Session,
    company_id: uuid.UUID
) -> Optional[date]:
    """
    Get the most recent price date for a company.

    Args:
        session: SQLAlchemy session
        company_id: Company UUID

    Returns:
        Most recent price_date or None if no prices exist
    """
    result = session.query(
        func.max(StockPrice.price_date)
    ).filter(
        StockPrice.company_id == company_id,
        StockPrice.deleted_at.is_(None)
    ).scalar()

    return result


def fetch_yfinance_prices(
    ticker: str,
    start_date: date,
    end_date: date
) -> List[Dict[str, Any]]:
    """
    Fetch historical prices from yfinance.

    Args:
        ticker: Stock ticker symbol
        start_date: Start date for historical data
        end_date: End date for historical data

    Returns:
        List of price records with OHLCV data
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            auto_adjust=False  # Get raw prices + adjusted separately
        )

        if hist.empty:
            logger.warning(f"No price data returned for {ticker}")
            return []

        records = []
        for idx, row in hist.iterrows():
            price_date = idx.date() if hasattr(idx, 'date') else idx
            records.append({
                'price_date': price_date,
                'open_price': float(row['Open']) if row['Open'] == row['Open'] else None,
                'high_price': float(row['High']) if row['High'] == row['High'] else None,
                'low_price': float(row['Low']) if row['Low'] == row['Low'] else None,
                'close_price': float(row['Close']) if row['Close'] == row['Close'] else None,
                'adjusted_close': float(row['Adj Close']) if 'Adj Close' in row and row['Adj Close'] == row['Adj Close'] else None,
                'volume': int(row['Volume']) if row['Volume'] == row['Volume'] else None,
            })

        return records

    except Exception as e:
        logger.error(f"Error fetching prices for {ticker}: {e}")
        return []


def compute_rolling_metrics(
    prices: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Compute rolling metrics: 1-day returns, 52-week high/low.

    Processes prices in chronological order and computes:
    - pct_change_1d: (close - prev_close) / prev_close
    - high_52w: Rolling 252-day maximum close
    - low_52w: Rolling 252-day minimum close

    Args:
        prices: List of price records sorted by date

    Returns:
        Same list with metrics added
    """
    if not prices:
        return prices

    # Sort by date
    sorted_prices = sorted(prices, key=lambda x: x['price_date'])

    # Compute metrics
    prev_close = None
    close_history = []

    for price in sorted_prices:
        close = price['close_price']

        # 1-day return
        if prev_close and prev_close != 0:
            price['pct_change_1d'] = (close - prev_close) / prev_close
        else:
            price['pct_change_1d'] = None

        # Add to history for rolling window
        if close is not None:
            close_history.append(close)

        # Keep only last 252 trading days (~1 year)
        if len(close_history) > 252:
            close_history.pop(0)

        # 52-week high/low
        if close_history:
            price['high_52w'] = max(close_history)
            price['low_52w'] = min(close_history)
        else:
            price['high_52w'] = None
            price['low_52w'] = None

        prev_close = close

    return sorted_prices


def ingest_stock_prices(
    session: Optional[Session] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    ticker_limit: Optional[int] = None,
    days_back: int = 1095,  # ~3 years
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Ingest stock prices from yfinance for all companies with tickers.

    This function:
    1. Gets all companies with active ticker mappings
    2. For each, fetches historical prices from yfinance
    3. Computes rolling metrics (52w high/low, daily returns)
    4. Upserts into stock_prices table

    Args:
        session: SQLAlchemy session (creates new if None)
        start_date: Start date for historical data (default: days_back from today)
        end_date: End date for historical data (default: today)
        ticker_limit: Limit number of tickers to process (for testing)
        days_back: Number of days of history to fetch if start_date not specified
        dry_run: If True, don't actually insert records

    Returns:
        Statistics dict with processed, inserted, errors, etc.
    """
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        # Set date range
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=days_back)

        logger.info(f"Fetching stock prices from {start_date} to {end_date}")

        # Get tickers to fetch
        tickers = get_tickers_to_fetch(session, limit=ticker_limit)
        logger.info(f"Found {len(tickers)} tickers to fetch")

        stats = {
            'total_tickers': len(tickers),
            'processed': 0,
            'skipped_no_data': 0,
            'prices_inserted': 0,
            'prices_updated': 0,
            'errors': 0,
            'error_tickers': []
        }

        for i, ticker_info in enumerate(tickers):
            ticker = ticker_info['ticker']
            company_id = ticker_info['company_id']
            company_name = ticker_info['company_name']

            # Progress logging every 10 tickers
            if (i + 1) % 10 == 0:
                logger.info(f"Processing {i + 1}/{len(tickers)} tickers...")

            try:
                # Check for existing data - only fetch what we don't have
                latest_date = get_latest_price_date(session, company_id)
                fetch_start = start_date

                if latest_date:
                    # Start from day after latest existing price
                    fetch_start = max(start_date, latest_date + timedelta(days=1))

                if fetch_start >= end_date:
                    logger.debug(f"Skipping {ticker} - already up to date")
                    stats['processed'] += 1
                    continue

                # Fetch from yfinance
                prices = fetch_yfinance_prices(ticker, fetch_start, end_date)

                if not prices:
                    stats['skipped_no_data'] += 1
                    continue

                # Compute rolling metrics
                # For accurate 52w metrics, we need to include historical data
                if latest_date:
                    # Fetch enough history for 52w calculation
                    lookback_start = fetch_start - timedelta(days=370)
                    existing_prices = session.query(
                        StockPrice.price_date,
                        StockPrice.close_price
                    ).filter(
                        StockPrice.company_id == company_id,
                        StockPrice.price_date >= lookback_start,
                        StockPrice.deleted_at.is_(None)
                    ).order_by(StockPrice.price_date).all()

                    # Combine existing + new for metric calculation
                    full_history = [
                        {'price_date': p.price_date, 'close_price': float(p.close_price) if p.close_price else None}
                        for p in existing_prices
                    ] + prices

                    # Compute metrics on full history
                    full_history = compute_rolling_metrics(full_history)

                    # Extract only the new prices with updated metrics
                    new_dates = {p['price_date'] for p in prices}
                    prices = [p for p in full_history if p['price_date'] in new_dates]
                else:
                    prices = compute_rolling_metrics(prices)

                if dry_run:
                    logger.debug(f"[DRY RUN] Would insert {len(prices)} prices for {ticker}")
                    stats['prices_inserted'] += len(prices)
                else:
                    # Upsert prices
                    for price in prices:
                        stmt = insert(StockPrice.__table__).values(
                            price_id=uuid.uuid4(),
                            company_id=company_id,
                            price_date=price['price_date'],
                            open_price=price.get('open_price'),
                            high_price=price.get('high_price'),
                            low_price=price.get('low_price'),
                            close_price=price['close_price'],
                            adjusted_close=price.get('adjusted_close'),
                            volume=price.get('volume'),
                            pct_change_1d=price.get('pct_change_1d'),
                            high_52w=price.get('high_52w'),
                            low_52w=price.get('low_52w'),
                            data_sources={'source': 'yfinance', 'ticker': ticker}
                        ).on_conflict_do_update(
                            constraint='uq_company_price_date',
                            set_={
                                'open_price': price.get('open_price'),
                                'high_price': price.get('high_price'),
                                'low_price': price.get('low_price'),
                                'close_price': price['close_price'],
                                'adjusted_close': price.get('adjusted_close'),
                                'volume': price.get('volume'),
                                'pct_change_1d': price.get('pct_change_1d'),
                                'high_52w': price.get('high_52w'),
                                'low_52w': price.get('low_52w'),
                                'last_updated': func.now()
                            }
                        )
                        session.execute(stmt)

                    session.commit()
                    stats['prices_inserted'] += len(prices)

                stats['processed'] += 1

            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                stats['errors'] += 1
                stats['error_tickers'].append(ticker)
                session.rollback()

        # Log summary
        logger.info(
            f"Stock price ingestion complete: "
            f"{stats['processed']} processed, "
            f"{stats['prices_inserted']} prices inserted/updated, "
            f"{stats['skipped_no_data']} skipped (no data), "
            f"{stats['errors']} errors"
        )

        return stats

    except Exception as e:
        logger.error(f"Error during stock price ingestion: {e}")
        session.rollback()
        raise

    finally:
        if close_session:
            session.close()


def get_price_history(
    ticker_or_company_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve price history for a company.

    Args:
        ticker_or_company_id: Ticker symbol or company UUID string
        start_date: Optional start date filter
        end_date: Optional end date filter
        session: SQLAlchemy session (creates new if None)

    Returns:
        List of price records with date and OHLCV data
    """
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        # Determine if input is ticker or UUID
        try:
            company_id = uuid.UUID(ticker_or_company_id)
        except ValueError:
            # It's a ticker - look up company
            ticker_record = session.query(CompanyTicker).filter(
                CompanyTicker.ticker == ticker_or_company_id.upper(),
                CompanyTicker.deleted_at.is_(None),
                CompanyTicker.valid_until.is_(None)
            ).first()

            if not ticker_record:
                return []

            company_id = ticker_record.company_id

        # Query prices
        query = session.query(StockPrice).filter(
            StockPrice.company_id == company_id,
            StockPrice.deleted_at.is_(None)
        )

        if start_date:
            query = query.filter(StockPrice.price_date >= start_date)
        if end_date:
            query = query.filter(StockPrice.price_date <= end_date)

        query = query.order_by(StockPrice.price_date)

        return [
            {
                'price_date': p.price_date,
                'open': float(p.open_price) if p.open_price else None,
                'high': float(p.high_price) if p.high_price else None,
                'low': float(p.low_price) if p.low_price else None,
                'close': float(p.close_price) if p.close_price else None,
                'adjusted_close': float(p.adjusted_close) if p.adjusted_close else None,
                'volume': p.volume,
                'pct_change_1d': float(p.pct_change_1d) if p.pct_change_1d else None,
                'high_52w': float(p.high_52w) if p.high_52w else None,
                'low_52w': float(p.low_52w) if p.low_52w else None,
            }
            for p in query.all()
        ]

    finally:
        if close_session:
            session.close()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description="Ingest stock prices from yfinance")
    parser.add_argument('--dry-run', action='store_true', help="Don't actually insert records")
    parser.add_argument('--limit', type=int, default=None, help="Limit number of tickers to process")
    parser.add_argument('--days', type=int, default=1095, help="Number of days of history to fetch")
    parser.add_argument('--start-date', type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument('--end-date', type=str, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    start_date = None
    end_date = None
    if args.start_date:
        start_date = date.fromisoformat(args.start_date)
    if args.end_date:
        end_date = date.fromisoformat(args.end_date)

    stats = ingest_stock_prices(
        start_date=start_date,
        end_date=end_date,
        ticker_limit=args.limit,
        days_back=args.days,
        dry_run=args.dry_run
    )

    print("\n=== Stock Price Ingestion Results ===")
    print(f"Total tickers: {stats['total_tickers']}")
    print(f"Processed: {stats['processed']}")
    print(f"Prices inserted/updated: {stats['prices_inserted']}")
    print(f"Skipped (no data): {stats['skipped_no_data']}")
    print(f"Errors: {stats['errors']}")

    if stats['error_tickers'][:10]:
        print("\nSample error tickers:")
        for t in stats['error_tickers'][:10]:
            print(f"  {t}")
