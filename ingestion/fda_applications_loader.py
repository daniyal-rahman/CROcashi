"""
FDA Applications and Submissions loader.

Loads data from openFDA API into the fda_applications and
fda_submissions tables, with company and drug entity matching.
"""
import logging
import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from fuzzywuzzy import fuzz
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from database.config import SessionLocal
from database.models import Company, Drug, FDAApplication, FDASubmission
from ingestion.utils.http import HttpClient

logger = logging.getLogger(__name__)

# OpenFDA API endpoint for drug approvals
OPENFDA_DRUGSFDA_URL = "https://api.fda.gov/drug/drugsfda.json"


def fetch_openfda_applications(
    limit: int = 1000,
    skip: int = 0
) -> List[Dict[str, Any]]:
    """
    Fetch drug application data from openFDA API.

    Args:
        limit: Number of records per request (max 1000)
        skip: Number of records to skip

    Returns:
        List of application records
    """
    client = HttpClient(requests_per_second=2.0)

    params = {
        'limit': min(limit, 1000),
        'skip': skip
    }

    logger.info(f"Fetching openFDA drugsfda (skip={skip}, limit={limit})")
    resp = client.get(OPENFDA_DRUGSFDA_URL, params=params)
    data = client.json_or_text(resp)

    if isinstance(data, dict) and 'results' in data:
        return data['results']

    return []


def fetch_all_openfda_applications(max_records: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Fetch all drug applications from openFDA API with pagination.

    Args:
        max_records: Maximum number of records to fetch (None = all)

    Returns:
        List of all application records
    """
    all_records = []
    skip = 0
    limit = 1000

    while True:
        records = fetch_openfda_applications(limit=limit, skip=skip)

        if not records:
            break

        all_records.extend(records)
        logger.info(f"Fetched {len(all_records)} total records...")

        if max_records and len(all_records) >= max_records:
            all_records = all_records[:max_records]
            break

        skip += limit

        # openFDA has a limit of 26000 records via skip
        if skip >= 26000:
            logger.warning("Reached openFDA skip limit (26000)")
            break

    return all_records


def parse_date(date_str: str) -> Optional[date]:
    """Parse FDA date string to date object."""
    if not date_str:
        return None

    # openFDA uses YYYYMMDD format
    for fmt in ['%Y%m%d', '%Y-%m-%d', '%b %d, %Y', '%m/%d/%Y']:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue

    return None


def extract_application_type(appl_no: str) -> str:
    """
    Extract application type from application number.

    NDA = New Drug Application
    BLA = Biologics License Application
    ANDA = Abbreviated NDA (generics)
    """
    if not appl_no:
        return 'NDA'

    appl_str = str(appl_no).upper().strip()

    if appl_str.startswith('BLA') or re.match(r'^1\d{5}$', appl_str):
        return 'BLA'
    elif appl_str.startswith('ANDA') or re.match(r'^[78]\d{5}$', appl_str):
        return 'ANDA'
    else:
        return 'NDA'


def normalize_application_number(appl_no: str) -> str:
    """
    Normalize application number to standard format.
    """
    if not appl_no:
        return ''

    appl_str = str(appl_no).upper().strip()

    # Remove any prefix
    appl_str = re.sub(r'^(NDA|BLA|ANDA)', '', appl_str)

    # Determine type and format
    appl_type = extract_application_type(appl_no)
    return f"{appl_type}{appl_str}"


def match_company_fuzzy(
    sponsor_name: str,
    companies: List[Tuple[uuid.UUID, str]],
    min_score: int = 80
) -> Optional[uuid.UUID]:
    """Match sponsor name to company using fuzzy matching."""
    if not sponsor_name:
        return None

    sponsor_normalized = sponsor_name.upper().strip()

    suffixes = [' INC', ' CORP', ' LLC', ' LTD', ' CO', ' PHARMACEUTICALS', ' PHARMA']
    for suffix in suffixes:
        sponsor_normalized = sponsor_normalized.replace(suffix, '')

    best_match = None
    best_score = 0

    for company_id, company_name in companies:
        company_normalized = company_name.upper().strip()
        for suffix in suffixes:
            company_normalized = company_normalized.replace(suffix, '')

        score = fuzz.ratio(sponsor_normalized, company_normalized)
        token_score = fuzz.token_set_ratio(sponsor_normalized, company_normalized)
        score = max(score, token_score)

        if score > best_score:
            best_score = score
            best_match = company_id

    if best_match and best_score >= min_score:
        return best_match

    return None


def match_drug_fuzzy(
    drug_name: str,
    drugs: List[Tuple[uuid.UUID, str, Optional[str]]],
    min_score: int = 85
) -> Optional[uuid.UUID]:
    """Match drug name to drug entity using fuzzy matching."""
    if not drug_name:
        return None

    drug_normalized = drug_name.upper().strip()

    best_match = None
    best_score = 0

    for drug_id, primary_name, generic_name in drugs:
        for name in [primary_name, generic_name]:
            if not name:
                continue

            name_normalized = name.upper().strip()
            score = fuzz.ratio(drug_normalized, name_normalized)

            if score > best_score:
                best_score = score
                best_match = drug_id

    if best_match and best_score >= min_score:
        return best_match

    return None


def load_fda_applications(
    session: Optional[Session] = None,
    max_records: Optional[int] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Load FDA applications and submissions from openFDA API into the database.

    The openFDA drugsfda endpoint returns records with structure:
    {
        "application_number": "NDA123456",
        "sponsor_name": "PFIZER INC",
        "products": [...],
        "submissions": [...]
    }

    Args:
        session: SQLAlchemy session
        max_records: Maximum number of records to fetch (None = all available)
        dry_run: If True, don't actually insert records

    Returns:
        Statistics dict
    """
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        # Fetch data from openFDA API
        logger.info("Fetching FDA applications from openFDA API...")
        fda_records = fetch_all_openfda_applications(max_records=max_records)
        logger.info(f"Fetched {len(fda_records)} application records")

        # Get reference data from database
        logger.info("Loading reference data from database...")
        companies = session.query(
            Company.company_id,
            Company.name
        ).filter(
            Company.deleted_at.is_(None)
        ).all()
        companies_list = [(c.company_id, c.name) for c in companies]
        logger.info(f"Loaded {len(companies_list)} companies")

        drugs = session.query(
            Drug.drug_id,
            Drug.primary_name,
            Drug.generic_name
        ).filter(
            Drug.deleted_at.is_(None)
        ).all()
        drugs_list = [(d.drug_id, d.primary_name, d.generic_name) for d in drugs]
        logger.info(f"Loaded {len(drugs_list)} drugs")

        # Stats
        stats = {
            'applications_parsed': 0,
            'applications_inserted': 0,
            'applications_matched_company': 0,
            'applications_matched_drug': 0,
            'submissions_parsed': 0,
            'submissions_inserted': 0,
            'errors': 0
        }

        application_map = {}  # application_number -> application_id

        # Process applications
        logger.info(f"Processing {len(fda_records)} applications...")

        for i, record in enumerate(fda_records):
            if (i + 1) % 1000 == 0:
                logger.info(f"Processing application {i + 1}/{len(fda_records)}...")

            appl_no = record.get('application_number')
            if not appl_no:
                continue

            stats['applications_parsed'] += 1

            # Normalize application number
            application_number = normalize_application_number(appl_no)
            application_type = extract_application_type(appl_no)

            # Get sponsor info
            sponsor_name = record.get('sponsor_name')

            # Get product info (first product)
            products = record.get('products', [])
            brand_name = None
            generic_name = None
            if products:
                product = products[0]
                brand_name = product.get('brand_name')
                generic_name = product.get('active_ingredients', [{}])[0].get('name') if product.get('active_ingredients') else None

            # Get openFDA info if available
            openfda = record.get('openfda', {})
            if not brand_name and openfda.get('brand_name'):
                brand_name = openfda['brand_name'][0] if isinstance(openfda['brand_name'], list) else openfda['brand_name']
            if not generic_name and openfda.get('generic_name'):
                generic_name = openfda['generic_name'][0] if isinstance(openfda['generic_name'], list) else openfda['generic_name']

            # Match company
            company_id = match_company_fuzzy(sponsor_name, companies_list)
            if company_id:
                stats['applications_matched_company'] += 1

            # Match drug
            drug_name = brand_name or generic_name
            drug_id = match_drug_fuzzy(drug_name, drugs_list)
            if drug_id:
                stats['applications_matched_drug'] += 1

            # Find approval date from submissions
            submissions = record.get('submissions', [])
            approval_date = None
            for sub in submissions:
                if sub.get('submission_status') == 'AP':
                    approval_date = parse_date(sub.get('submission_status_date'))
                    if approval_date:
                        break

            if not dry_run:
                try:
                    stmt = insert(FDAApplication.__table__).values(
                        application_id=uuid.uuid4(),
                        application_number=application_number,
                        application_type=application_type,
                        drug_id=drug_id,
                        company_id=company_id,
                        sponsor_name=sponsor_name,
                        brand_name=brand_name,
                        generic_name=generic_name,
                        approval_date=approval_date,
                        data_sources={'source': 'openfda_drugsfda'}
                    ).on_conflict_do_update(
                        index_elements=['application_number'],
                        set_={
                            'drug_id': drug_id,
                            'company_id': company_id,
                            'sponsor_name': sponsor_name,
                            'brand_name': brand_name,
                            'generic_name': generic_name,
                            'approval_date': approval_date,
                            'last_updated': func.now()
                        }
                    )
                    session.execute(stmt)
                    stats['applications_inserted'] += 1

                    # Get application_id for submissions
                    app_record = session.query(FDAApplication).filter(
                        FDAApplication.application_number == application_number
                    ).first()
                    if app_record:
                        application_map[application_number] = app_record.application_id

                except Exception as e:
                    logger.error(f"Error inserting application {appl_no}: {e}")
                    stats['errors'] += 1
            else:
                application_map[application_number] = uuid.uuid4()
                stats['applications_inserted'] += 1

            # Process submissions for this application
            for sub in submissions:
                stats['submissions_parsed'] += 1

                submission_type = sub.get('submission_type', 'ORIG')
                submission_number = None
                try:
                    submission_number = int(sub.get('submission_number', 0))
                except (ValueError, TypeError):
                    pass

                # Parse action type
                action_type = sub.get('submission_status')
                if action_type:
                    action_type = action_type.upper()
                    if action_type not in ['AP', 'CRL', 'TA', 'WD', 'RL']:
                        action_type = None

                # Parse dates
                action_date = parse_date(sub.get('submission_status_date'))

                # Review priority
                review_priority = sub.get('review_priority')

                if not dry_run and application_number in application_map:
                    try:
                        stmt = insert(FDASubmission.__table__).values(
                            submission_id=uuid.uuid4(),
                            application_id=application_map[application_number],
                            submission_type=submission_type,
                            submission_number=submission_number,
                            action_date=action_date,
                            action_type=action_type,
                            review_priority=review_priority,
                            data_sources={'source': 'openfda_drugsfda'}
                        ).on_conflict_do_nothing()
                        session.execute(stmt)
                        stats['submissions_inserted'] += 1

                    except Exception as e:
                        logger.debug(f"Error inserting submission: {e}")
                        stats['errors'] += 1
                else:
                    stats['submissions_inserted'] += 1

        if not dry_run:
            session.commit()
            logger.info(f"Committed changes to database")

        logger.info(
            f"FDA data load complete: "
            f"{stats['applications_inserted']} applications, "
            f"{stats['submissions_inserted']} submissions, "
            f"{stats['applications_matched_company']} matched to companies, "
            f"{stats['applications_matched_drug']} matched to drugs"
        )

        return stats

    except Exception as e:
        logger.error(f"Error loading FDA data: {e}")
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

    parser = argparse.ArgumentParser(description="Load FDA applications and submissions")
    parser.add_argument('--dry-run', action='store_true', help="Don't insert records")
    parser.add_argument('--max-records', type=int, default=None, help="Max records to fetch")
    args = parser.parse_args()

    stats = load_fda_applications(
        max_records=args.max_records,
        dry_run=args.dry_run
    )

    print("\n=== FDA Applications Load Results ===")
    print(f"Applications parsed: {stats['applications_parsed']}")
    print(f"Applications inserted: {stats['applications_inserted']}")
    print(f"  - Matched to companies: {stats['applications_matched_company']}")
    print(f"  - Matched to drugs: {stats['applications_matched_drug']}")
    print(f"Submissions parsed: {stats['submissions_parsed']}")
    print(f"Submissions inserted: {stats['submissions_inserted']}")
    print(f"Errors: {stats['errors']}")
