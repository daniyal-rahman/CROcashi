#!/usr/bin/env python3
"""
Company Profile Generator

Generates markdown risk reports for biotech companies based on clinical trial data.

Usage:
    python generate_company_profile.py "Amgen"
    python generate_company_profile.py --id <uuid>
    python generate_company_profile.py --all  # generates for all companies with 5+ trials
"""
import argparse
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import UUID

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.entities import Company, Disease, Drug
from database.models.relationships import CompanyDrug, TrialDisease, TrialDrug, TrialSponsor
from src.models.clinical_constants import TrialStatus


# =============================================================================
# Configuration
# =============================================================================

MIN_TRIALS_FOR_REPORT = 3  # Skip companies with fewer trials
MIN_TRIALS_FOR_BATCH = 5   # For --all mode

RISK_THRESHOLDS = {
    'termination_rate_overall': 0.25,      # 25%
    'termination_rate_phase_2_3': 0.30,    # 30%
    'indication_concentration': 0.50,       # 50%
    'min_drugs': 5,                         # Small portfolio threshold
}


# =============================================================================
# Data Classes
# =============================================================================

class CompanyData:
    """Container for company profile data."""
    
    def __init__(self):
        self.company: Optional[Company] = None
        self.company_id: Optional[UUID] = None
        self.trials: List[ClinicalTrial] = []
        self.drugs: List[Drug] = []
        self.indications: Dict[str, List[ClinicalTrial]] = defaultdict(list)
        self.drug_trials: Dict[UUID, List[ClinicalTrial]] = defaultdict(list)
        self.duplicate_warning: Optional[str] = None
        self.trials_without_start_date: int = 0


# =============================================================================
# Company Lookup
# =============================================================================

def find_company(
    session: Session,
    name: Optional[str] = None,
    company_id: Optional[UUID] = None
) -> Tuple[Optional[Company], Optional[str]]:
    """
    Find a company by name or ID.
    
    Returns:
        Tuple of (Company, duplicate_warning)
    """
    duplicate_warning = None
    
    if company_id:
        company = session.query(Company).filter(
            Company.company_id == company_id,
            Company.deleted_at.is_(None)
        ).first()
        return company, None
    
    if name:
        # Exact match first
        company = session.query(Company).filter(
            Company.name.ilike(name),
            Company.deleted_at.is_(None)
        ).first()
        
        if not company:
            # Try partial match
            company = session.query(Company).filter(
                Company.name.ilike(f'%{name}%'),
                Company.deleted_at.is_(None)
            ).first()
        
        if company:
            # Check for duplicates (Novartis/Novartis Pharmaceuticals issue)
            base_name = name.split()[0] if ' ' in name else name
            similar = session.query(Company).filter(
                Company.name.ilike(f'%{base_name}%'),
                Company.deleted_at.is_(None)
            ).all()
            
            if len(similar) > 1:
                names = [c.name for c in similar]
                duplicate_warning = f"Multiple entities found for '{base_name}': {', '.join(names)}"
        
        return company, duplicate_warning
    
    return None, None


def get_companies_for_batch(session: Session, min_trials: int = MIN_TRIALS_FOR_BATCH) -> List[Company]:
    """Get all companies with at least min_trials trials."""
    # Subquery to count trials per company
    trial_counts = session.query(
        TrialSponsor.entity_id,
        func.count(TrialSponsor.trial_id).label('trial_count')
    ).filter(
        TrialSponsor.entity_type == 'company',
        TrialSponsor.deleted_at.is_(None)
    ).group_by(TrialSponsor.entity_id).subquery()
    
    companies = session.query(Company).join(
        trial_counts,
        Company.company_id == trial_counts.c.entity_id
    ).filter(
        trial_counts.c.trial_count >= min_trials,
        Company.deleted_at.is_(None)
    ).order_by(trial_counts.c.trial_count.desc()).all()
    
    return companies


# =============================================================================
# Data Fetching
# =============================================================================

def fetch_company_data(session: Session, company: Company) -> CompanyData:
    """Fetch all data needed for the company profile."""
    data = CompanyData()
    data.company = company
    data.company_id = company.company_id
    
    # Get company-sponsored trials
    data.trials = session.query(ClinicalTrial).join(
        TrialSponsor,
        ClinicalTrial.trial_id == TrialSponsor.trial_id
    ).filter(
        TrialSponsor.entity_id == company.company_id,
        TrialSponsor.entity_type == 'company',
        TrialSponsor.deleted_at.is_(None),
        ClinicalTrial.deleted_at.is_(None)
    ).all()
    
    # Count trials without start_date
    data.trials_without_start_date = len([t for t in data.trials if not t.start_date])
    
    # Get company drugs via CompanyDrug relationship
    drug_ids = session.query(CompanyDrug.drug_id).filter(
        CompanyDrug.company_id == company.company_id,
        CompanyDrug.deleted_at.is_(None)
    ).distinct().all()
    drug_ids = [d[0] for d in drug_ids]
    
    if drug_ids:
        data.drugs = session.query(Drug).filter(
            Drug.drug_id.in_(drug_ids),
            Drug.deleted_at.is_(None)
        ).all()
    
    # Get indications (disease areas) for each trial
    for trial in data.trials:
        diseases = session.query(Disease).join(
            TrialDisease,
            Disease.disease_id == TrialDisease.disease_id
        ).filter(
            TrialDisease.trial_id == trial.trial_id,
            TrialDisease.deleted_at.is_(None),
            Disease.deleted_at.is_(None)
        ).all()
        
        for disease in diseases:
            data.indications[disease.disease_name].append(trial)
    
    # Get trials per drug
    for drug in data.drugs:
        drug_trials = session.query(ClinicalTrial).join(
            TrialDrug,
            ClinicalTrial.trial_id == TrialDrug.trial_id
        ).join(
            TrialSponsor,
            ClinicalTrial.trial_id == TrialSponsor.trial_id
        ).filter(
            TrialDrug.drug_id == drug.drug_id,
            TrialSponsor.entity_id == company.company_id,
            TrialSponsor.entity_type == 'company',
            TrialDrug.deleted_at.is_(None),
            TrialSponsor.deleted_at.is_(None),
            ClinicalTrial.deleted_at.is_(None)
        ).all()
        
        data.drug_trials[drug.drug_id] = drug_trials
    
    return data


# =============================================================================
# Analysis Functions
# =============================================================================

def is_terminated(trial: ClinicalTrial) -> bool:
    """Check if a trial is terminated/failed."""
    return trial.status in TrialStatus.FAILED_STATUSES


def is_active(trial: ClinicalTrial) -> bool:
    """Check if a trial is active."""
    return trial.status in TrialStatus.ACTIVE_STATUSES


def is_completed(trial: ClinicalTrial) -> bool:
    """Check if a trial completed successfully."""
    return trial.status == TrialStatus.COMPLETED


def get_phase_trials(trials: List[ClinicalTrial], phase: int) -> List[ClinicalTrial]:
    """Get trials for a specific phase."""
    return [t for t in trials if t.phase_numeric == phase]


def calculate_termination_rate(trials: List[ClinicalTrial]) -> Tuple[float, int, int]:
    """
    Calculate termination rate.
    
    Returns:
        Tuple of (rate, terminated_count, total_count)
    """
    if not trials:
        return 0.0, 0, 0
    
    terminated = len([t for t in trials if is_terminated(t)])
    total = len(trials)
    rate = terminated / total if total > 0 else 0.0
    
    return rate, terminated, total


def calculate_temporal_termination_rates(trials: List[ClinicalTrial]) -> List[Dict]:
    """
    Calculate year-by-year termination rates.
    
    Temporal logic:
    - A trial counts toward denominator when start_date <= year_end
    - A trial counts as terminated when status in FAILED_STATUSES AND 
      (completion_date <= year_end OR we assume it was terminated by that date)
    
    Returns:
        List of dicts with year, rate, terminated, total
    """
    # Filter trials with start_date
    valid_trials = [t for t in trials if t.start_date]
    
    if not valid_trials:
        return []
    
    # Get year range
    start_years = [t.start_date.year for t in valid_trials]
    min_year = min(start_years)
    max_year = max(max(start_years), date.today().year)
    
    results = []
    
    for year in range(min_year, max_year + 1):
        year_end = date(year, 12, 31)
        
        # Trials that had started by year_end
        trials_by_year_end = [t for t in valid_trials if t.start_date <= year_end]
        
        # Of those, how many were terminated by year_end?
        # Use completion_date if available, otherwise assume current status applies
        terminated_by_year_end = 0
        for trial in trials_by_year_end:
            if is_terminated(trial):
                # Check if we can determine when it was terminated
                if trial.completion_date and trial.completion_date <= year_end:
                    terminated_by_year_end += 1
                elif trial.primary_completion_date and trial.primary_completion_date <= year_end:
                    terminated_by_year_end += 1
                elif not trial.completion_date and not trial.primary_completion_date:
                    # No date info - only count if trial started that year or earlier
                    # and we're at current year (conservative approach)
                    if year == max_year:
                        terminated_by_year_end += 1
        
        total = len(trials_by_year_end)
        rate = terminated_by_year_end / total if total > 0 else 0.0
        
        results.append({
            'year': year,
            'rate': rate,
            'terminated': terminated_by_year_end,
            'total': total
        })
    
    return results


# =============================================================================
# Report Generation
# =============================================================================

def generate_bar(count: int, max_count: int = 20, char: str = '█') -> str:
    """Generate ASCII bar for visualization."""
    if max_count == 0:
        return ''
    # Scale to max 20 characters
    scaled = min(int((count / max(max_count, 1)) * 20), 20)
    return char * max(scaled, 1) if count > 0 else ''


def section_overview(data: CompanyData) -> str:
    """Generate Overview section."""
    trials = data.trials
    
    total_drugs = len(data.drugs)
    total_trials = len(trials)
    active = len([t for t in trials if is_active(t)])
    completed = len([t for t in trials if is_completed(t)])
    terminated = len([t for t in trials if is_terminated(t)])
    
    lines = [
        "## Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Drugs | {total_drugs} |",
        f"| Total Trials | {total_trials} |",
        f"| Active | {active} |",
        f"| Completed | {completed} |",
        f"| Terminated | {terminated} |",
        ""
    ]
    
    return '\n'.join(lines)


def section_portfolio_by_phase(data: CompanyData) -> str:
    """Generate Portfolio by Phase section."""
    lines = ["## Portfolio by Phase", ""]
    
    phase_data = []
    for phase in [1, 2, 3]:
        phase_trials = get_phase_trials(data.trials, phase)
        count = len(phase_trials)
        terminated = len([t for t in phase_trials if is_terminated(t)])
        phase_data.append((phase, count, terminated))
    
    max_count = max(p[1] for p in phase_data) if phase_data else 1
    
    for phase, count, terminated in phase_data:
        bar = generate_bar(count, max_count)
        lines.append(f"Phase {phase}: {bar} {count} ({terminated} terminated)")
    
    # Handle trials without phase info
    no_phase = [t for t in data.trials if t.phase_numeric is None]
    if no_phase:
        lines.append(f"\n*{len(no_phase)} trial(s) without phase information*")
    
    lines.append("")
    return '\n'.join(lines)


def section_termination_history(data: CompanyData) -> str:
    """Generate Termination History section with temporal analysis."""
    lines = ["## Termination History", ""]
    
    # Overall rates
    overall_rate, overall_term, overall_total = calculate_termination_rate(data.trials)
    lines.append(f"**Overall termination rate:** {overall_rate:.1%} ({overall_term}/{overall_total})")
    
    # Phase 2/3 rates
    phase_2_3_trials = [t for t in data.trials if t.phase_numeric in [2, 3]]
    if phase_2_3_trials:
        p23_rate, p23_term, p23_total = calculate_termination_rate(phase_2_3_trials)
        lines.append(f"**Phase 2/3 termination rate:** {p23_rate:.1%} ({p23_term}/{p23_total})")
    else:
        lines.append("**Phase 2/3 termination rate:** No Phase 2/3 data")
    
    lines.append("")
    
    # Temporal analysis
    temporal_data = calculate_temporal_termination_rates(data.trials)
    
    if temporal_data:
        lines.append("### Timeline")
        lines.append("")
        lines.append("| Year | Rate | Cumulative |")
        lines.append("|------|------|------------|")
        
        for entry in temporal_data:
            rate_str = f"{entry['rate']:.1%}" if entry['total'] > 0 else "N/A"
            lines.append(f"| {entry['year']} | {rate_str} | {entry['terminated']}/{entry['total']} |")
    
    if data.trials_without_start_date > 0:
        lines.append(f"\n*{data.trials_without_start_date} trial(s) excluded from temporal analysis (no start date)*")
    
    lines.append("")
    return '\n'.join(lines)


def section_indication_exposure(data: CompanyData) -> str:
    """Generate Indication Exposure section."""
    lines = ["## Indication Exposure", ""]
    
    if not data.indications:
        lines.append("*No indication data available*")
        lines.append("")
        return '\n'.join(lines)
    
    lines.append("| Indication | Trials | Terminated | Rate |")
    lines.append("|------------|--------|------------|------|")
    
    # Sort by trial count descending
    sorted_indications = sorted(
        data.indications.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )
    
    for indication, trials in sorted_indications:
        trial_count = len(trials)
        terminated = len([t for t in trials if is_terminated(t)])
        rate = terminated / trial_count if trial_count > 0 else 0.0
        # Truncate long indication names
        display_name = indication[:40] + '...' if len(indication) > 40 else indication
        lines.append(f"| {display_name} | {trial_count} | {terminated} | {rate:.0%} |")
    
    lines.append("")
    return '\n'.join(lines)


def section_drug_pipeline(data: CompanyData) -> str:
    """Generate Drug Pipeline Status section."""
    lines = ["## Drug Pipeline Status", ""]
    
    if not data.drugs:
        lines.append("*No drug data available*")
        lines.append("")
        return '\n'.join(lines)
    
    for drug in data.drugs:
        trials = data.drug_trials.get(drug.drug_id, [])
        
        if not trials:
            continue
        
        # Summarize phases and statuses
        phases = [str(t.phase_numeric) if t.phase_numeric else '?' for t in trials]
        has_terminated = any(is_terminated(t) for t in trials)
        
        # Count statuses
        active_count = len([t for t in trials if is_active(t)])
        completed_count = len([t for t in trials if is_completed(t)])
        terminated_count = len([t for t in trials if is_terminated(t)])
        
        status_parts = []
        if active_count:
            status_parts.append(f"{active_count} active")
        if completed_count:
            status_parts.append(f"{completed_count} completed")
        if terminated_count:
            status_parts.append(f"{terminated_count} terminated")
        
        status_str = ', '.join(status_parts) if status_parts else 'unknown'
        flag = " ⚠️" if has_terminated else ""
        
        drug_name = drug.primary_name or drug.generic_name or drug.code_name or str(drug.drug_id)[:8]
        lines.append(f"**{drug_name}:** {len(trials)} trial(s) (Phase {', '.join(phases)}) - {status_str}{flag}")
    
    lines.append("")
    return '\n'.join(lines)


def section_risk_signals(data: CompanyData) -> str:
    """Generate Risk Signals section."""
    lines = ["## Risk Signals", ""]
    
    warnings = []
    positives = []
    
    # Check termination rates
    overall_rate, _, _ = calculate_termination_rate(data.trials)
    if overall_rate > RISK_THRESHOLDS['termination_rate_overall']:
        warnings.append(f"⚠️ High overall termination rate ({overall_rate:.1%} vs {RISK_THRESHOLDS['termination_rate_overall']:.0%} threshold)")
    
    phase_2_3_trials = [t for t in data.trials if t.phase_numeric in [2, 3]]
    if phase_2_3_trials:
        p23_rate, _, _ = calculate_termination_rate(phase_2_3_trials)
        if p23_rate > RISK_THRESHOLDS['termination_rate_phase_2_3']:
            warnings.append(f"⚠️ High Phase 2/3 termination rate ({p23_rate:.1%} vs {RISK_THRESHOLDS['termination_rate_phase_2_3']:.0%} threshold)")
    
    # Check indication concentration
    if data.indications:
        total_indication_trials = sum(len(trials) for trials in data.indications.values())
        for indication, trials in data.indications.items():
            concentration = len(trials) / total_indication_trials if total_indication_trials > 0 else 0
            if concentration > RISK_THRESHOLDS['indication_concentration']:
                display_name = indication[:30] + '...' if len(indication) > 30 else indication
                warnings.append(f"⚠️ High concentration in {display_name} ({concentration:.0%} of portfolio)")
                break  # Only report the highest concentration
    
    # Check portfolio size
    if len(data.drugs) < RISK_THRESHOLDS['min_drugs']:
        warnings.append(f"⚠️ Small drug portfolio ({len(data.drugs)} drugs)")
    
    # Check for stalled pipeline
    active_trials = [t for t in data.trials if is_active(t)]
    if not active_trials:
        warnings.append("⚠️ No active trials (stalled pipeline)")
    
    # Positive signals
    if len(data.drugs) >= RISK_THRESHOLDS['min_drugs']:
        positives.append(f"✓ Diversified drug portfolio ({len(data.drugs)} drugs)")
    
    if len(data.indications) >= 5:
        positives.append(f"✓ Diversified across {len(data.indications)} indications")
    
    # Active late-stage (Phase 3) programs
    active_phase_3 = [t for t in data.trials if t.phase_numeric == 3 and is_active(t)]
    if active_phase_3:
        positives.append(f"✓ {len(active_phase_3)} active Phase 3 program(s)")
    
    # Low termination rate is positive
    if overall_rate <= 0.15 and len(data.trials) >= 5:
        positives.append(f"✓ Low termination rate ({overall_rate:.1%})")
    
    # Output
    if warnings:
        for w in warnings:
            lines.append(w)
    
    if positives:
        if warnings:
            lines.append("")
        for p in positives:
            lines.append(p)
    
    if not warnings and not positives:
        lines.append("*Insufficient data for risk assessment*")
    
    lines.append("")
    return '\n'.join(lines)


def generate_report(data: CompanyData) -> str:
    """Generate the full markdown report."""
    lines = [
        f"# Company Profile: {data.company.name}",
        "",
        f"Generated: {date.today().isoformat()}",
        ""
    ]
    
    # Add duplicate warning if present
    if data.duplicate_warning:
        lines.append(f"> **Note:** {data.duplicate_warning}")
        lines.append("")
    
    # Generate each section
    lines.append(section_overview(data))
    lines.append(section_portfolio_by_phase(data))
    lines.append(section_termination_history(data))
    lines.append(section_indication_exposure(data))
    lines.append(section_drug_pipeline(data))
    lines.append(section_risk_signals(data))
    
    return '\n'.join(lines)


# =============================================================================
# File Output
# =============================================================================

def save_report(report: str, company_name: str, output_dir: Path) -> Path:
    """Save report to file."""
    # Create directory if needed
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize company name for filename
    safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in company_name.lower())
    safe_name = safe_name[:50]  # Limit length
    
    filename = f"{safe_name}_{date.today().isoformat()}.md"
    filepath = output_dir / filename
    
    filepath.write_text(report, encoding='utf-8')
    
    return filepath


# =============================================================================
# Main CLI
# =============================================================================

def process_company(
    session: Session,
    company: Company,
    output_dir: Path,
    duplicate_warning: Optional[str] = None
) -> Optional[Path]:
    """Process a single company and generate report."""
    # Check minimum trials
    trial_count = session.query(func.count(TrialSponsor.trial_id)).filter(
        TrialSponsor.entity_id == company.company_id,
        TrialSponsor.entity_type == 'company',
        TrialSponsor.deleted_at.is_(None)
    ).scalar()
    
    if trial_count < MIN_TRIALS_FOR_REPORT:
        print(f"  Skipping {company.name}: only {trial_count} trials (minimum: {MIN_TRIALS_FOR_REPORT})")
        return None
    
    # Fetch data
    data = fetch_company_data(session, company)
    data.duplicate_warning = duplicate_warning
    
    # Generate report
    report = generate_report(data)
    
    # Save
    filepath = save_report(report, company.name, output_dir)
    
    return filepath


def main():
    parser = argparse.ArgumentParser(
        description='Generate company risk profile reports',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python generate_company_profile.py "Amgen"
    python generate_company_profile.py --id 123e4567-e89b-12d3-a456-426614174000
    python generate_company_profile.py --all
        """
    )
    
    parser.add_argument(
        'company_name',
        nargs='?',
        help='Company name to generate report for'
    )
    parser.add_argument(
        '--id',
        type=str,
        help='Company UUID'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help=f'Generate reports for all companies with {MIN_TRIALS_FOR_BATCH}+ trials'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='reports/company_profiles',
        help='Output directory (default: reports/company_profiles)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.company_name and not args.id and not args.all:
        parser.error('Must specify company name, --id, or --all')
    
    output_dir = project_root / args.output_dir
    
    with get_db_session() as session:
        if args.all:
            # Batch mode
            print(f"Finding companies with {MIN_TRIALS_FOR_BATCH}+ trials...")
            companies = get_companies_for_batch(session, MIN_TRIALS_FOR_BATCH)
            
            if not companies:
                print("No qualifying companies found.")
                return 1
            
            print(f"Found {len(companies)} companies. Generating reports...")
            
            success_count = 0
            for company in companies:
                print(f"Processing {company.name}...")
                filepath = process_company(session, company, output_dir)
                if filepath:
                    print(f"  Saved: {filepath}")
                    success_count += 1
            
            print(f"\nGenerated {success_count} reports in {output_dir}")
        
        else:
            # Single company mode
            company_id = UUID(args.id) if args.id else None
            company, duplicate_warning = find_company(session, args.company_name, company_id)
            
            if not company:
                print(f"Company not found: {args.company_name or args.id}")
                return 1
            
            if duplicate_warning:
                print(f"Warning: {duplicate_warning}")
            
            print(f"Generating report for {company.name}...")
            filepath = process_company(session, company, output_dir, duplicate_warning)
            
            if filepath:
                print(f"Report saved: {filepath}")
            else:
                return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

