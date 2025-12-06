"""
Catalyst and backtesting models: Historical catalysts, flag caching, FDA data.
"""
import uuid
from datetime import date

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database.models.base import BaseModel


class HistoricalCatalyst(BaseModel):
    """
    Historical catalyst events with known outcomes.

    This is the core backtesting table. Each row represents a specific
    event (trial readout, FDA decision, etc.) that occurred on a specific
    date with a known outcome - the target variable for backtesting.
    """

    __tablename__ = 'historical_catalysts'

    catalyst_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # Core identifiers
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    trial_id = Column(
        UUID(as_uuid=True),
        ForeignKey('clinical_trials.trial_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    disease_id = Column(
        UUID(as_uuid=True),
        ForeignKey('diseases.disease_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    # Catalyst type (hierarchical naming like Event model)
    catalyst_type = Column(
        String(100),
        nullable=False,
        index=True,
        comment='Hierarchical type: trial.readout.phase2, fda.decision.crl, etc.'
    )

    # Temporal
    catalyst_date = Column(
        Date,
        nullable=False,
        index=True,
        comment='Date the catalyst occurred/was announced'
    )
    announced_date = Column(
        Date,
        nullable=True,
        comment='Public announcement date (may differ from catalyst_date)'
    )

    # Outcome (target variable for backtesting)
    outcome = Column(
        String(50),
        nullable=False,
        index=True,
        comment='positive, negative, mixed, neutral'
    )
    outcome_severity = Column(
        String(50),
        nullable=True,
        comment='For negative outcomes: mild, moderate, severe, catastrophic'
    )

    # Stock reaction (for validation/analysis)
    stock_reaction_1d = Column(
        Numeric(8, 4),
        nullable=True,
        comment='1-day stock return after catalyst'
    )
    stock_reaction_5d = Column(
        Numeric(8, 4),
        nullable=True,
        comment='5-day stock return after catalyst'
    )

    # Context
    phase = Column(
        Integer,
        nullable=True,
        comment='Trial phase (1, 2, 3) for trial readouts'
    )
    description = Column(
        Text,
        nullable=True,
        comment='Brief description of the catalyst'
    )

    # Provenance
    source_type = Column(
        String(100),
        nullable=True,
        comment='Data source: 8k_filing, clinicaltrials_gov, fda_drugs, manual'
    )
    source_url = Column(
        String(1000),
        nullable=True,
        comment='URL to original source document'
    )
    data_sources = Column(
        JSONB,
        nullable=True,
        comment='Track which sources contributed to this record'
    )

    # Manual verification
    manually_verified = Column(
        Boolean,
        default=False,
        index=True,
        comment='Has this catalyst been manually verified?'
    )

    # Relationships
    company = relationship('Company', backref='catalysts')
    drug = relationship('Drug', backref='catalysts')
    trial = relationship('ClinicalTrial', backref='catalysts')
    disease = relationship('Disease', backref='catalysts')

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('positive', 'negative', 'mixed', 'neutral')",
            name='check_catalyst_outcome'
        ),
        CheckConstraint(
            "outcome_severity IN ('mild', 'moderate', 'severe', 'catastrophic') OR outcome_severity IS NULL",
            name='check_outcome_severity'
        ),
        UniqueConstraint(
            'company_id', 'drug_id', 'catalyst_type', 'catalyst_date',
            name='uq_catalyst_event'
        ),
        Index('ix_catalysts_date_type', 'catalyst_date', 'catalyst_type'),
        Index('ix_catalysts_outcome', 'outcome', 'catalyst_date'),
    )


class CatalystFlagCache(BaseModel):
    """
    Pre-computed flag values at catalyst dates.

    Stores point-in-time flag calculations to enable fast backtesting.
    All flags are computed using only data available BEFORE the
    computed_at_date (no lookahead bias).
    """

    __tablename__ = 'catalyst_flag_cache'

    cache_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    catalyst_id = Column(
        UUID(as_uuid=True),
        ForeignKey('historical_catalysts.catalyst_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Point-in-time date (all flags computed as of this date)
    computed_at_date = Column(
        Date,
        nullable=False,
        index=True,
        comment='Date flags were computed as-of (no lookahead)'
    )

    # Flag: Graveyard indication (>80% historical failure rate)
    graveyard_indication = Column(
        Boolean,
        default=False,
        index=True,
        comment='Indication has >80% historical failure rate'
    )
    graveyard_indication_score = Column(
        Numeric(5, 4),
        nullable=True,
        comment='Underlying failure rate (0.0-1.0)'
    )

    # Flag: High company termination rate (>25%)
    high_company_termination_rate = Column(
        Boolean,
        default=False,
        index=True,
        comment='Company has >25% Phase 2/3 termination rate'
    )
    company_termination_rate = Column(
        Numeric(5, 4),
        nullable=True,
        comment='Underlying termination rate (0.0-1.0)'
    )

    # Flag: Single asset company
    single_asset_company = Column(
        Boolean,
        default=False,
        index=True,
        comment='Company has only 1 drug in pipeline'
    )
    pipeline_count = Column(
        Integer,
        nullable=True,
        comment='Number of drugs in pipeline'
    )

    # Flag: Down 80% from 3-year high
    down_80_pct = Column(
        Boolean,
        default=False,
        index=True,
        comment='Stock down >80% from 3-year peak'
    )
    pct_from_3y_high = Column(
        Numeric(8, 4),
        nullable=True,
        comment='Percentage below 3-year high (0.0-1.0)'
    )

    # Flag: Prior drug failure
    prior_drug_failure = Column(
        Boolean,
        default=False,
        index=True,
        comment='Same drug had prior failed trial'
    )
    prior_failure_count = Column(
        Integer,
        nullable=True,
        comment='Number of prior failures for this drug'
    )

    # Composite flags
    any_flag_triggered = Column(
        Boolean,
        default=False,
        index=True,
        comment='At least one flag was triggered'
    )
    flag_count = Column(
        Integer,
        default=0,
        comment='Total number of flags triggered'
    )

    # Version tracking
    calculation_version = Column(
        String(50),
        nullable=True,
        comment='Algorithm version for reproducibility'
    )

    # Relationships
    catalyst = relationship('HistoricalCatalyst', backref='flag_caches')

    __table_args__ = (
        UniqueConstraint(
            'catalyst_id', 'computed_at_date', 'calculation_version',
            name='uq_catalyst_flag_cache'
        ),
        Index('ix_flag_cache_any_triggered', 'any_flag_triggered', 'computed_at_date'),
    )


class FDAApplication(BaseModel):
    """
    FDA drug applications (NDA, BLA, ANDA).

    Tracks FDA application submissions and their lifecycle,
    enabling extraction of approval and CRL catalyst events.
    """

    __tablename__ = 'fda_applications'

    application_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # FDA application number (unique identifier)
    application_number = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment='FDA application number (e.g., NDA012345, BLA125123)'
    )
    application_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment='NDA, BLA, ANDA, IND'
    )

    # Linkage to existing entities
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    # Application info (from FDA data)
    sponsor_name = Column(
        String(500),
        nullable=True,
        comment='Sponsor company name from FDA'
    )
    brand_name = Column(
        String(500),
        nullable=True,
        comment='Brand/trade name'
    )
    generic_name = Column(
        String(500),
        nullable=True,
        comment='Generic/active ingredient name'
    )

    # Status
    current_status = Column(
        String(100),
        nullable=True,
        index=True,
        comment='Current application status'
    )

    # Key dates
    submission_date = Column(
        Date,
        nullable=True,
        index=True,
        comment='Original submission date'
    )
    approval_date = Column(
        Date,
        nullable=True,
        index=True,
        comment='Approval date (if approved)'
    )

    # Metadata
    data_sources = Column(
        JSONB,
        nullable=True,
        comment='Track data sources'
    )

    # Relationships
    drug = relationship('Drug', backref='fda_applications')
    company = relationship('Company', backref='fda_applications')

    __table_args__ = (
        CheckConstraint(
            "application_type IN ('NDA', 'BLA', 'ANDA', 'IND')",
            name='check_fda_application_type'
        ),
        Index('ix_fda_applications_sponsor', 'sponsor_name'),
    )


class FDASubmission(BaseModel):
    """
    FDA submission events within an application.

    Tracks individual submissions (original, supplements) and their
    outcomes (approval, CRL, withdrawal). This is where PDUFA dates
    and regulatory decisions are recorded.
    """

    __tablename__ = 'fda_submissions'

    submission_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey('fda_applications.application_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Submission info
    submission_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='ORIG (original), SUPPL (supplement), EFFCT, etc.'
    )
    submission_number = Column(
        Integer,
        nullable=True,
        comment='Submission sequence number'
    )

    # Dates
    submission_date = Column(
        Date,
        nullable=True,
        index=True,
        comment='Date submission was filed'
    )
    action_date = Column(
        Date,
        nullable=True,
        index=True,
        comment='PDUFA action date or decision date'
    )

    # Outcome
    action_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='AP (approval), CRL (complete response letter), TA, WD, RL'
    )

    # Review details
    review_priority = Column(
        String(50),
        nullable=True,
        comment='STANDARD, PRIORITY'
    )
    orphan_designation = Column(
        Boolean,
        default=False,
        comment='Has orphan drug designation'
    )

    # Metadata
    data_sources = Column(
        JSONB,
        nullable=True,
        comment='Track data sources'
    )

    # Relationships
    application = relationship('FDAApplication', backref='submissions')

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('AP', 'CRL', 'TA', 'WD', 'RL') OR action_type IS NULL",
            name='check_fda_submission_action_type'
        ),
        CheckConstraint(
            "submission_type IN ('ORIG', 'SUPPL', 'EFFCT', 'MANUF', 'REMS') OR submission_type IS NULL",
            name='check_fda_submission_type'
        ),
        Index('ix_fda_submissions_action', 'action_type', 'action_date'),
    )
