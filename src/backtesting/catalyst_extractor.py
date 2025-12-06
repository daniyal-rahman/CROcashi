"""
Catalyst Extractor for backtesting.

Extracts historical catalyst events (trial readouts, FDA decisions, etc.)
from various data sources and loads them into the historical_catalysts table.
"""
import logging
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from database.config import SessionLocal
from database.models import (
    ClinicalTrial, Company, Disease, Drug, FDAApplication, FDASubmission,
    HistoricalCatalyst, StockPrice, TrialStatusHistory
)
from database.models.relationships import TrialSponsor, TrialDisease

logger = logging.getLogger(__name__)


def extract_fda_catalysts(
    session: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Extract FDA decision catalysts from fda_applications/fda_submissions.

    Looks for:
    - Approvals (AP) -> positive
    - Complete Response Letters (CRL) -> negative
    - Withdrawals (WD) -> negative
    - Tentative Approvals (TA) -> positive

    Args:
        session: SQLAlchemy session
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of catalyst dicts ready for insertion
    """
    logger.info("Extracting FDA decision catalysts...")

    # Query submissions with action types we care about
    query = session.query(
        FDASubmission,
        FDAApplication
    ).join(
        FDAApplication,
        FDASubmission.application_id == FDAApplication.application_id
    ).filter(
        FDASubmission.action_type.in_(['AP', 'CRL', 'TA', 'WD']),
        FDASubmission.action_date.isnot(None),
        FDASubmission.deleted_at.is_(None),
        FDAApplication.deleted_at.is_(None)
    )

    if start_date:
        query = query.filter(FDASubmission.action_date >= start_date)
    if end_date:
        query = query.filter(FDASubmission.action_date <= end_date)

    results = query.all()
    logger.info(f"Found {len(results)} FDA submission events")

    catalysts = []
    for sub, app in results:
        # Determine outcome based on action type
        if sub.action_type == 'AP':
            outcome = 'positive'
            catalyst_type = 'fda.decision.approval'
        elif sub.action_type == 'TA':
            outcome = 'positive'
            catalyst_type = 'fda.decision.tentative_approval'
        elif sub.action_type == 'CRL':
            outcome = 'negative'
            catalyst_type = 'fda.decision.crl'
        elif sub.action_type == 'WD':
            outcome = 'negative'
            catalyst_type = 'fda.decision.withdrawal'
        else:
            continue

        # Skip if no company linked
        if not app.company_id:
            continue

        catalysts.append({
            'company_id': app.company_id,
            'drug_id': app.drug_id,
            'catalyst_type': catalyst_type,
            'catalyst_date': sub.action_date,
            'outcome': outcome,
            'phase': None,  # FDA decisions are post-Phase 3
            'description': f"{sub.action_type} for {app.application_number}: {app.brand_name or app.generic_name}",
            'source_type': 'fda_submissions',
        })

    return catalysts


def extract_trial_catalysts(
    session: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Extract trial readout catalysts from clinical_trials status changes.

    Looks for status transitions indicating readouts:
    - Completed -> Could be positive or negative
    - Terminated -> Negative
    - Suspended -> Negative

    For completed trials, we infer outcome based on:
    - Whether the trial advanced to next phase
    - Whether the drug was later approved
    - Default to 'neutral' if unknown

    Args:
        session: SQLAlchemy session
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of catalyst dicts
    """
    logger.info("Extracting trial readout catalysts...")

    # Query trial status history for relevant transitions
    # Note: Database stores status in lowercase
    query = session.query(
        TrialStatusHistory,
        ClinicalTrial
    ).join(
        ClinicalTrial,
        TrialStatusHistory.trial_id == ClinicalTrial.trial_id
    ).filter(
        TrialStatusHistory.status.in_([
            'completed', 'terminated', 'suspended', 'withdrawn'
        ]),
        TrialStatusHistory.status_date.isnot(None),
        TrialStatusHistory.deleted_at.is_(None),
        ClinicalTrial.deleted_at.is_(None)
    )

    if start_date:
        query = query.filter(TrialStatusHistory.status_date >= start_date)
    if end_date:
        query = query.filter(TrialStatusHistory.status_date <= end_date)

    results = query.all()
    logger.info(f"Found {len(results)} trial status events")

    catalysts = []
    for status_hist, trial in results:
        # Determine outcome based on status (status is lowercase in DB)
        status = status_hist.status

        if status == 'completed':
            outcome = 'neutral'  # Will be enriched later
            catalyst_type = f'trial.readout.phase{trial.phase_numeric or "unknown"}'
        elif status in ['terminated', 'suspended', 'withdrawn']:
            outcome = 'negative'
            catalyst_type = f'trial.failure.phase{trial.phase_numeric or "unknown"}'
        else:
            continue

        # Get primary sponsor company
        # TrialSponsor uses entity_id (not company_id) and sponsor_role (not sponsor_type)
        company_id = None
        sponsor = session.query(TrialSponsor).filter(
            TrialSponsor.trial_id == trial.trial_id,
            TrialSponsor.sponsor_role == 'lead_sponsor',
            TrialSponsor.entity_type == 'company',
            TrialSponsor.deleted_at.is_(None)
        ).first()
        
        if sponsor:
            company_id = sponsor.entity_id

        # Skip if no company
        if not company_id:
            continue

        # Get disease from trial (relationship is trial_diseases, not diseases)
        disease_id = None
        trial_disease = session.query(TrialDisease).filter(
            TrialDisease.trial_id == trial.trial_id,
            TrialDisease.deleted_at.is_(None)
        ).first()
        
        if trial_disease:
            disease_id = trial_disease.disease_id

        catalysts.append({
            'company_id': company_id,
            'drug_id': None,  # Would need drug linkage
            'trial_id': trial.trial_id,
            'disease_id': disease_id,
            'catalyst_type': catalyst_type,
            'catalyst_date': status_hist.status_date,
            'outcome': outcome,
            'phase': trial.phase_numeric,
            'description': f"Phase {trial.phase_numeric or trial.phase or 'unknown'} {status.lower()}: {(trial.trial_title[:100] if trial.trial_title else 'Unknown trial')}",
            'source_type': 'clinicaltrials_gov',
        })

    return catalysts


def compute_stock_reaction(
    session: Session,
    company_id: uuid.UUID,
    event_date: date,
    days: int = 1
) -> Optional[float]:
    """
    Compute stock price reaction around an event.

    Args:
        session: SQLAlchemy session
        company_id: Company UUID
        event_date: Date of the event
        days: Number of days for return calculation (1 or 5)

    Returns:
        Percentage return or None if no data
    """
    # Get price on/before event date
    before_price = session.query(StockPrice).filter(
        StockPrice.company_id == company_id,
        StockPrice.price_date <= event_date,
        StockPrice.deleted_at.is_(None)
    ).order_by(StockPrice.price_date.desc()).first()

    if not before_price or not before_price.close_price:
        return None

    # Get price N days after
    after_date = event_date + timedelta(days=days)
    after_price = session.query(StockPrice).filter(
        StockPrice.company_id == company_id,
        StockPrice.price_date >= after_date,
        StockPrice.deleted_at.is_(None)
    ).order_by(StockPrice.price_date.asc()).first()

    if not after_price or not after_price.close_price:
        return None

    # Calculate return
    return_pct = (float(after_price.close_price) - float(before_price.close_price)) / float(before_price.close_price)
    return return_pct


def load_catalysts(
    session: Optional[Session] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    include_fda: bool = True,
    include_trials: bool = True,
    compute_reactions: bool = True,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Extract and load historical catalysts into the database.

    Args:
        session: SQLAlchemy session
        start_date: Optional start date filter
        end_date: Optional end date filter
        include_fda: Whether to include FDA decision catalysts
        include_trials: Whether to include trial readout catalysts
        compute_reactions: Whether to compute stock price reactions
        dry_run: If True, don't actually insert records

    Returns:
        Statistics dict
    """
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        all_catalysts = []

        # Extract from different sources
        if include_fda:
            fda_catalysts = extract_fda_catalysts(session, start_date, end_date)
            all_catalysts.extend(fda_catalysts)
            logger.info(f"Extracted {len(fda_catalysts)} FDA catalysts")

        if include_trials:
            trial_catalysts = extract_trial_catalysts(session, start_date, end_date)
            all_catalysts.extend(trial_catalysts)
            logger.info(f"Extracted {len(trial_catalysts)} trial catalysts")

        logger.info(f"Total catalysts to process: {len(all_catalysts)}")

        stats = {
            'total_extracted': len(all_catalysts),
            'inserted': 0,
            'with_stock_reaction': 0,
            'errors': 0
        }

        # Process and insert catalysts
        for i, catalyst in enumerate(all_catalysts):
            if (i + 1) % 100 == 0:
                logger.info(f"Processing catalyst {i + 1}/{len(all_catalysts)}...")

            # Compute stock reactions if requested
            if compute_reactions:
                reaction_1d = compute_stock_reaction(
                    session, catalyst['company_id'], catalyst['catalyst_date'], days=1
                )
                reaction_5d = compute_stock_reaction(
                    session, catalyst['company_id'], catalyst['catalyst_date'], days=5
                )
                catalyst['stock_reaction_1d'] = reaction_1d
                catalyst['stock_reaction_5d'] = reaction_5d

                if reaction_1d is not None:
                    stats['with_stock_reaction'] += 1

            if not dry_run:
                try:
                    stmt = insert(HistoricalCatalyst.__table__).values(
                        catalyst_id=uuid.uuid4(),
                        company_id=catalyst['company_id'],
                        drug_id=catalyst.get('drug_id'),
                        trial_id=catalyst.get('trial_id'),
                        disease_id=catalyst.get('disease_id'),
                        catalyst_type=catalyst['catalyst_type'],
                        catalyst_date=catalyst['catalyst_date'],
                        outcome=catalyst['outcome'],
                        phase=catalyst.get('phase'),
                        description=catalyst.get('description'),
                        source_type=catalyst.get('source_type'),
                        stock_reaction_1d=catalyst.get('stock_reaction_1d'),
                        stock_reaction_5d=catalyst.get('stock_reaction_5d'),
                        data_sources={'extractor_version': '1.0'}
                    ).on_conflict_do_nothing()
                    session.execute(stmt)
                    stats['inserted'] += 1

                except Exception as e:
                    logger.debug(f"Error inserting catalyst: {e}")
                    stats['errors'] += 1
            else:
                stats['inserted'] += 1

        if not dry_run:
            session.commit()
            logger.info("Committed catalysts to database")

        logger.info(
            f"Catalyst extraction complete: "
            f"{stats['inserted']} inserted, "
            f"{stats['with_stock_reaction']} with stock reactions, "
            f"{stats['errors']} errors"
        )

        return stats

    except Exception as e:
        logger.error(f"Error loading catalysts: {e}")
        session.rollback()
        raise

    finally:
        if close_session:
            session.close()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description="Extract historical catalysts")
    parser.add_argument('--dry-run', action='store_true', help="Don't insert records")
    parser.add_argument('--start-date', type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument('--end-date', type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument('--no-fda', action='store_true', help="Skip FDA catalysts")
    parser.add_argument('--no-trials', action='store_true', help="Skip trial catalysts")
    parser.add_argument('--no-reactions', action='store_true', help="Skip stock reaction calculation")
    args = parser.parse_args()

    start_date = None
    end_date = None
    if args.start_date:
        start_date = date.fromisoformat(args.start_date)
    if args.end_date:
        end_date = date.fromisoformat(args.end_date)

    stats = load_catalysts(
        start_date=start_date,
        end_date=end_date,
        include_fda=not args.no_fda,
        include_trials=not args.no_trials,
        compute_reactions=not args.no_reactions,
        dry_run=args.dry_run
    )

    print("\n=== Catalyst Extraction Results ===")
    print(f"Total extracted: {stats['total_extracted']}")
    print(f"Inserted: {stats['inserted']}")
    print(f"With stock reactions: {stats['with_stock_reaction']}")
    print(f"Errors: {stats['errors']}")
