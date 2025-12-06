"""
Market data models: Company tickers and stock prices.
"""
import uuid
from datetime import date

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, ForeignKey,
    Index, Numeric, String, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database.models.base import BaseModel


class CompanyTicker(BaseModel):
    """
    Temporal ticker mapping with CIK and exchange information.

    Tracks ticker symbols over time, handling ticker changes and
    providing SEC CIK linkage for SEC filing matching.
    """

    __tablename__ = 'company_tickers'

    ticker_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    ticker = Column(
        String(20),
        nullable=False,
        index=True,
        comment='Stock ticker symbol (e.g., MRNA, SAVA)'
    )
    cik = Column(
        String(20),
        nullable=True,
        index=True,
        comment='SEC Central Index Key (10-digit, zero-padded)'
    )
    exchange = Column(
        String(50),
        nullable=True,
        index=True,
        comment='Stock exchange (NASDAQ, NYSE, AMEX, OTC, etc.)'
    )

    # Temporal tracking
    valid_from = Column(
        Date,
        nullable=False,
        index=True,
        comment='Date this ticker became valid'
    )
    valid_until = Column(
        Date,
        nullable=True,
        index=True,
        comment='Date this ticker was replaced (NULL = current)'
    )

    # Primary ticker flag (company can have multiple tickers, e.g., ADRs)
    is_primary = Column(
        Boolean,
        default=True,
        index=True,
        comment='Whether this is the primary trading ticker'
    )

    # Metadata
    data_sources = Column(
        JSONB,
        nullable=True,
        comment='Track which sources provided this ticker mapping'
    )

    # Relationships
    company = relationship('Company', backref='tickers')

    __table_args__ = (
        UniqueConstraint(
            'company_id', 'ticker', 'valid_from',
            name='uq_company_ticker_period'
        ),
        Index('ix_company_tickers_active', 'company_id', 'is_primary',
              postgresql_where='valid_until IS NULL AND deleted_at IS NULL'),
    )


class StockPrice(BaseModel):
    """
    Historical daily stock prices.

    Stores OHLCV data with pre-computed metrics for fast backtesting
    (rolling 52-week high/low, daily returns).
    """

    __tablename__ = 'stock_prices'

    price_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Date
    price_date = Column(
        Date,
        nullable=False,
        index=True,
        comment='Trading date'
    )

    # OHLCV data
    open_price = Column(
        Numeric(12, 4),
        nullable=True,
        comment='Opening price'
    )
    high_price = Column(
        Numeric(12, 4),
        nullable=True,
        comment='Daily high price'
    )
    low_price = Column(
        Numeric(12, 4),
        nullable=True,
        comment='Daily low price'
    )
    close_price = Column(
        Numeric(12, 4),
        nullable=False,
        comment='Closing price'
    )
    adjusted_close = Column(
        Numeric(12, 4),
        nullable=True,
        comment='Split and dividend adjusted closing price'
    )
    volume = Column(
        BigInteger,
        nullable=True,
        comment='Trading volume'
    )

    # Pre-computed metrics for fast backtesting
    pct_change_1d = Column(
        Numeric(8, 4),
        nullable=True,
        comment='1-day percentage return'
    )
    high_52w = Column(
        Numeric(12, 4),
        nullable=True,
        comment='Rolling 52-week high as of this date'
    )
    low_52w = Column(
        Numeric(12, 4),
        nullable=True,
        comment='Rolling 52-week low as of this date'
    )

    # Metadata
    data_sources = Column(
        JSONB,
        nullable=True,
        comment='Track data source (e.g., yfinance)'
    )

    # Relationships
    company = relationship('Company', backref='stock_prices')

    __table_args__ = (
        UniqueConstraint(
            'company_id', 'price_date',
            name='uq_company_price_date'
        ),
        Index('ix_stock_prices_company_date', 'company_id', 'price_date'),
    )
