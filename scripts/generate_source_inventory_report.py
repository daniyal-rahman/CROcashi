"""
Generate Source Inventory Report

This script generates a comprehensive report of all data sources:
- List of all data sources (name, type, status)
- Last successful run date and record counts
- Sources that are configured but not actively running
- Sources that are failing or showing errors
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, and_, or_, text, inspect
from sqlalchemy.orm import Session

from database.config import get_db_session
from database.models.sources import Source
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from database.models.base import Base
from database.models.entities import Company, Drug, Disease, Institution, Target, Mechanism
from database.models.clinical import ClinicalTrial
from database.models.relationships import (
    TrialSponsor, TrialDrug, TrialDisease, CompanyDrug
)
from database.models.lineage import DataLineage
from database.models.resolution import (
    EntityAlias, EntityMatchCandidate, MatchingReviewQueue, EntityMatchConfidence
)
from src.services.company_risk_service import CompanyRiskService


def get_all_ingestion_files() -> List[str]:
    """Get list of all ingestion source files."""
    ingestion_dir = Path(__file__).parent.parent / "ingestion"
    sources = []
    
    for file in ingestion_dir.glob("*.py"):
        if file.name.startswith("__") or file.name == "test_helper.py":
            continue
        # Remove .py extension
        source_name = file.stem
        sources.append(source_name)
    
    return sorted(sources)


def get_source_type_from_name(source_name: str) -> str:
    """Infer source type from source name."""
    name_lower = source_name.lower()
    
    if any(x in name_lower for x in ['fda', 'ema', 'mhra', 'tga', 'health_canada', 'cdsco', 'anvisa', 'hsa', 'swissmedic', 'mfds', 'who', 'ich', 'nice']):
        return 'regulatory'
    elif any(x in name_lower for x in ['pubmed', 'pmc', 'biorxiv', 'medrxiv', 'chemrxiv', 'arxiv', 'semantic', 'pubtator', 'europe_pmc']):
        return 'literature'
    elif any(x in name_lower for x in ['sec', 'alphavantage', 'openfigi', 'calcbench']):
        return 'financial'
    elif any(x in name_lower for x in ['patentsview', 'uspto', 'patent']):
        return 'patent'
    elif any(x in name_lower for x in ['clinicaltrials', 'trial', 'who_ictrp', 'ema_trials']):
        return 'clinical'
    elif any(x in name_lower for x in ['reddit', 'youtube', 'twitter', 'linkedin', 'rss', 'news', 'google_news']):
        return 'social'
    elif any(x in name_lower for x in ['warn', 'layoff', 'biospace', 'fierce', 'xtalks']):
        return 'employment'
    elif any(x in name_lower for x in ['chembl', 'pubchem', 'uniprot', 'clinvar', 'disgenet', 'opentargets', 'reactome', 'string', 'biogrid', 'orphanet', 'omim', 'clingen']):
        return 'scientific'
    elif any(x in name_lower for x in ['nih', 'nsf', 'darpa', 'barda', 'dod', 'sbir']):
        return 'funding'
    elif any(x in name_lower for x in ['asco', 'abstract']):
        return 'conference'
    else:
        return 'other'


def get_source_status_from_db(session: Session, source_name: str) -> Dict:
    """Get source status from database."""
    source = session.query(Source).filter(
        Source.source_name == source_name,
        Source.deleted_at.is_(None)
    ).first()
    
    if source:
        return {
            'exists_in_db': True,
            'is_active': source.is_active,
            'source_type': source.source_type,
            'last_checked': source.last_checked,
            'update_frequency': source.update_frequency,
            'reliability_score': float(source.reliability_score) if source.reliability_score else None,
        }
    else:
        return {
            'exists_in_db': False,
            'is_active': None,
            'source_type': None,
            'last_checked': None,
            'update_frequency': None,
            'reliability_score': None,
        }


def get_last_run_info(session: Session, source_name: str) -> Dict:
    """Get last successful run information from processing logs."""
    # Get last successful processing log entry
    last_success = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.source_name == source_name,
        SourceProcessingLog.processing_status == 'success',
        SourceProcessingLog.deleted_at.is_(None)
    ).order_by(SourceProcessingLog.processing_started_at.desc()).first()
    
    # Get last run (any status)
    last_run = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.source_name == source_name,
        SourceProcessingLog.deleted_at.is_(None)
    ).order_by(SourceProcessingLog.processing_started_at.desc()).first()
    
    # Count records in staging
    staging_count = session.query(func.count(StagingRawData.staging_id)).filter(
        StagingRawData.source_system == source_name,
        StagingRawData.deleted_at.is_(None)
    ).scalar() or 0
    
    # Count records from last 30 days
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_count = session.query(func.count(StagingRawData.staging_id)).filter(
        StagingRawData.source_system == source_name,
        StagingRawData.ingested_at >= thirty_days_ago,
        StagingRawData.deleted_at.is_(None)
    ).scalar() or 0
    
    result = {
        'last_successful_run': last_success.processing_started_at if last_success else None,
        'last_run_date': last_run.processing_started_at if last_run else None,
        'last_run_status': last_run.processing_status if last_run else None,
        'total_records_in_staging': staging_count,
        'records_last_30_days': recent_count,
        'last_run_records': None,  # Will be set below if available
    }
    
    # Get record count from last successful run if available
    if last_success:
        # Try to get count from processing details or calculate from staging
        if last_success.processing_details:
            details = last_success.processing_details
            if isinstance(details, dict):
                result['last_run_records'] = details.get('records_processed', details.get('records_pulled', None))
        
        # If not in details, estimate from staging records ingested around that time
        if 'last_run_records' not in result or result['last_run_records'] is None:
            run_date = last_success.processing_started_at
            if isinstance(run_date, datetime):
                start_window = run_date - timedelta(hours=24)
                end_window = run_date + timedelta(hours=24)
            else:
                # If it's a date, convert to datetime
                start_window = datetime.combine(run_date, datetime.min.time()) - timedelta(hours=12)
                end_window = datetime.combine(run_date, datetime.max.time()) + timedelta(hours=12)
            
            count = session.query(func.count(StagingRawData.staging_id)).filter(
                StagingRawData.source_system == source_name,
                StagingRawData.ingested_at >= start_window,
                StagingRawData.ingested_at <= end_window,
                StagingRawData.deleted_at.is_(None)
            ).scalar() or 0
            result['last_run_records'] = count if count > 0 else None
    
    return result


def get_error_info(session: Session, source_name: str) -> Dict:
    """Get error information for a source."""
    # Check for failed processing logs
    failed_runs = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.source_name == source_name,
        SourceProcessingLog.processing_status == 'failed',
        SourceProcessingLog.deleted_at.is_(None)
    ).order_by(SourceProcessingLog.processing_started_at.desc()).limit(5).all()
    
    # Check for processing errors in staging
    staging_errors = session.query(func.count(StagingRawData.staging_id)).filter(
        StagingRawData.source_system == source_name,
        StagingRawData.processing_errors.isnot(None),
        StagingRawData.deleted_at.is_(None)
    ).scalar() or 0
    
    # Get recent errors (last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_failed = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.source_name == source_name,
        SourceProcessingLog.processing_status == 'failed',
        SourceProcessingLog.processing_started_at >= thirty_days_ago,
        SourceProcessingLog.deleted_at.is_(None)
    ).count()
    
    error_messages = []
    if failed_runs:
        for run in failed_runs[:3]:  # Get top 3 most recent
            if run.errors:
                error_messages.extend(run.errors[:2])  # Get first 2 errors from each
    
    return {
        'has_errors': len(failed_runs) > 0 or staging_errors > 0,
        'failed_runs_count': len(failed_runs),
        'recent_failed_runs': recent_failed,
        'staging_errors_count': staging_errors,
        'error_messages': error_messages[:5],  # Limit to 5 messages
    }


def generate_report() -> str:
    """Generate the Source Inventory Report."""
    all_sources = get_all_ingestion_files()
    
    report_lines = []
    report_lines.append("# Source Inventory Report")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        # Categorize sources
        active_sources = []
        inactive_sources = []
        failing_sources = []
        no_data_sources = []
        not_configured_sources = []
        
        for source_name in all_sources:
            db_status = get_source_status_from_db(session, source_name)
            run_info = get_last_run_info(session, source_name)
            error_info = get_error_info(session, source_name)
            
            source_type = db_status['source_type'] or get_source_type_from_name(source_name)
            is_active = db_status['is_active'] if db_status['exists_in_db'] else None
            has_data = run_info['total_records_in_staging'] > 0
            has_errors = error_info['has_errors']
            
            source_data = {
                'name': source_name,
                'type': source_type,
                'db_status': db_status,
                'run_info': run_info,
                'error_info': error_info,
                'has_data': has_data,
            }
            
            if has_errors:
                failing_sources.append(source_data)
            elif is_active is False:
                inactive_sources.append(source_data)
            elif not db_status['exists_in_db']:
                not_configured_sources.append(source_data)
            elif not has_data:
                no_data_sources.append(source_data)
            else:
                active_sources.append(source_data)
        
        # Summary section
        report_lines.append("## Summary")
        report_lines.append("")
        report_lines.append(f"- **Total Sources Implemented:** {len(all_sources)}")
        report_lines.append(f"- **Active Sources:** {len(active_sources)}")
        report_lines.append(f"- **Inactive Sources:** {len(inactive_sources)}")
        report_lines.append(f"- **Failing Sources:** {len(failing_sources)}")
        report_lines.append(f"- **Sources with No Data:** {len(no_data_sources)}")
        report_lines.append(f"- **Not Configured in DB:** {len(not_configured_sources)}")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Active Sources
        report_lines.append("## Active Sources")
        report_lines.append("")
        report_lines.append("| Source Name | Type | Last Successful Run | Records (Last Run) | Total Records | Records (30d) | Status |")
        report_lines.append("|-------------|------|---------------------|-------------------|---------------|---------------|--------|")
        
        def get_sort_date(run_info):
            """Get a comparable date for sorting."""
            last_run = run_info.get('last_successful_run')
            if last_run is None:
                return date.min
            if isinstance(last_run, datetime):
                return last_run.date()
            return last_run
        
        for source in sorted(active_sources, key=lambda x: get_sort_date(x['run_info']), reverse=True):
            name = source['name']
            source_type = source['type']
            last_success = source['run_info']['last_successful_run']
            last_run_records = source['run_info']['last_run_records']
            total_records = source['run_info']['total_records_in_staging']
            recent_records = source['run_info']['records_last_30_days']
            
            if last_success:
                if isinstance(last_success, datetime):
                    last_success_str = last_success.strftime('%Y-%m-%d')
                else:
                    last_success_str = last_success.strftime('%Y-%m-%d')
            else:
                last_success_str = "Never"
            records_str = f"{last_run_records:,}" if last_run_records else "N/A"
            total_str = f"{total_records:,}" if total_records > 0 else "0"
            recent_str = f"{recent_records:,}" if recent_records > 0 else "0"
            
            status = "✅ Active"
            if source['db_status']['is_active'] is False:
                status = "⚠️ Inactive in DB"
            
            report_lines.append(f"| {name} | {source_type} | {last_success_str} | {records_str} | {total_str} | {recent_str} | {status} |")
        
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Failing Sources
        if failing_sources:
            report_lines.append("## ⚠️ Failing Sources")
            report_lines.append("")
            report_lines.append("| Source Name | Type | Last Run | Last Status | Failed Runs | Recent Errors | Error Messages |")
            report_lines.append("|-------------|------|----------|-------------|-------------|---------------|---------------|")
            
            for source in sorted(failing_sources, key=lambda x: x['error_info']['recent_failed_runs'], reverse=True):
                name = source['name']
                source_type = source['type']
                last_run = source['run_info']['last_run_date']
                last_status = source['run_info']['last_run_status'] or "Unknown"
                failed_count = source['error_info']['failed_runs_count']
                recent_failed = source['error_info']['recent_failed_runs']
                errors = "; ".join(source['error_info']['error_messages'][:2]) if source['error_info']['error_messages'] else "No error messages"
                
                if last_run:
                    if isinstance(last_run, datetime):
                        last_run_str = last_run.strftime('%Y-%m-%d')
                    else:
                        last_run_str = last_run.strftime('%Y-%m-%d')
                else:
                    last_run_str = "Never"
                errors_str = errors[:100] + "..." if len(errors) > 100 else errors
                
                report_lines.append(f"| {name} | {source_type} | {last_run_str} | {last_status} | {failed_count} | {recent_failed} | {errors_str} |")
            
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")
        
        # Inactive Sources
        if inactive_sources:
            report_lines.append("## Inactive Sources (Configured but Not Running)")
            report_lines.append("")
            report_lines.append("| Source Name | Type | Last Checked | Total Records | Notes |")
            report_lines.append("|-------------|------|-------------|---------------|-------|")
            
            for source in sorted(inactive_sources, key=lambda x: x['name']):
                name = source['name']
                source_type = source['type']
                last_checked = source['db_status']['last_checked']
                total_records = source['run_info']['total_records_in_staging']
                
                if last_checked:
                    if isinstance(last_checked, datetime):
                        last_checked_str = last_checked.strftime('%Y-%m-%d')
                    else:
                        last_checked_str = last_checked.strftime('%Y-%m-%d')
                else:
                    last_checked_str = "Never"
                total_str = f"{total_records:,}" if total_records > 0 else "0"
                
                notes = "Marked as inactive in database"
                if total_records == 0:
                    notes += " - No data ingested"
                
                report_lines.append(f"| {name} | {source_type} | {last_checked_str} | {total_str} | {notes} |")
            
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")
        
        # Sources with No Data
        if no_data_sources:
            report_lines.append("## Sources with No Data")
            report_lines.append("")
            report_lines.append("| Source Name | Type | Last Run | Last Status | Notes |")
            report_lines.append("|-------------|------|----------|-------------|-------|")
            
            for source in sorted(no_data_sources, key=lambda x: x['name']):
                name = source['name']
                source_type = source['type']
                last_run = source['run_info']['last_run_date']
                last_status = source['run_info']['last_run_status'] or "Never run"
                
                if last_run:
                    if isinstance(last_run, datetime):
                        last_run_str = last_run.strftime('%Y-%m-%d')
                    else:
                        last_run_str = last_run.strftime('%Y-%m-%d')
                else:
                    last_run_str = "Never"
                
                notes = "No records in staging table"
                if last_status == 'failed':
                    notes += " - Last run failed"
                
                report_lines.append(f"| {name} | {source_type} | {last_run_str} | {last_status} | {notes} |")
            
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")
        
        # Not Configured Sources
        if not_configured_sources:
            report_lines.append("## Sources Not Configured in Database")
            report_lines.append("")
            report_lines.append("These sources have ingestion scripts but are not registered in the `sources` table.")
            report_lines.append("")
            report_lines.append("| Source Name | Inferred Type | Total Records | Notes |")
            report_lines.append("|-------------|---------------|---------------|-------|")
            
            for source in sorted(not_configured_sources, key=lambda x: x['name']):
                name = source['name']
                source_type = source['type']
                total_records = source['run_info']['total_records_in_staging']
                
                total_str = f"{total_records:,}" if total_records > 0 else "0"
                
                notes = "Not registered in sources table"
                if total_records > 0:
                    notes += " - Has data but not configured"
                
                report_lines.append(f"| {name} | {source_type} | {total_str} | {notes} |")
            
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")
        
        # Detailed Statistics
        report_lines.append("## Detailed Statistics")
        report_lines.append("")
        
        # Count by type
        type_counts = defaultdict(int)
        for source in all_sources:
            db_status = get_source_status_from_db(session, source)
            source_type = db_status['source_type'] or get_source_type_from_name(source)
            type_counts[source_type] += 1
        
        report_lines.append("### Sources by Type")
        report_lines.append("")
        for source_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            report_lines.append(f"- **{source_type}**: {count}")
        report_lines.append("")
        
        # Sources with most records
        report_lines.append("### Top 10 Sources by Total Records")
        report_lines.append("")
        all_source_data = []
        for source_name in all_sources:
            run_info = get_last_run_info(session, source_name)
            all_source_data.append({
                'name': source_name,
                'total_records': run_info['total_records_in_staging']
            })
        
        top_sources = sorted(all_source_data, key=lambda x: x['total_records'], reverse=True)[:10]
        report_lines.append("| Rank | Source Name | Total Records |")
        report_lines.append("|------|-------------|---------------|")
        for i, source in enumerate(top_sources, 1):
            report_lines.append(f"| {i} | {source['name']} | {source['total_records']:,} |")
        report_lines.append("")
        
        # Recent activity
        report_lines.append("### Most Active Sources (Last 30 Days)")
        report_lines.append("")
        recent_activity = []
        for source_name in all_sources:
            run_info = get_last_run_info(session, source_name)
            if run_info['records_last_30_days'] > 0:
                recent_activity.append({
                    'name': source_name,
                    'records': run_info['records_last_30_days']
                })
        
        recent_activity = sorted(recent_activity, key=lambda x: x['records'], reverse=True)[:10]
        if recent_activity:
            report_lines.append("| Rank | Source Name | Records (30d) |")
            report_lines.append("|------|-------------|---------------|")
            for i, source in enumerate(recent_activity, 1):
                report_lines.append(f"| {i} | {source['name']} | {source['records']:,} |")
        else:
            report_lines.append("No sources have ingested data in the last 30 days.")
        report_lines.append("")
    
    return "\n".join(report_lines)


def get_table_categories():
    """Define table categories for organization."""
    return {
        'staging': ['staging_raw_data'],
        'entity': [
            'companies', 'institutions', 'drugs', 'drug_chemical_identity', 'drug_names',
            'targets', 'mechanisms', 'diseases', 'disease_names'
        ],
        'clinical': ['clinical_trials', 'trial_status_history', 'regulatory_events'],
        'publication': ['publications', 'patents', 'conferences', 'conference_presentations', 'sec_filings'],
        'relationship': [
            'company_ownership_history', 'company_drugs', 'drug_ownership_history',
            'drug_targets', 'drug_mechanisms', 'drug_indications', 'drug_combinations',
            'trial_sponsors', 'trial_funding', 'trial_drugs', 'trial_diseases',
            'publication_drugs', 'publication_trials', 'publication_companies',
            'patent_drugs', 'patent_companies',
            'regulatory_drug_events', 'regulatory_company_events',
            'presentation_drugs', 'presentation_companies', 'presentation_trials',
            'filing_companies', 'filing_drugs'
        ],
        'resolution': [
            'entity_aliases', 'entity_matches', 'entity_match_confidence',
            'matching_review_queue', 'entity_match_candidates',
            'entity_matching_rules', 'source_processing_log', 'data_quality_metrics'
        ],
        'infrastructure': ['sources', 'data_lineage', 'entity_merges', 'events'],
    }


def get_all_table_counts(session: Session) -> Dict[str, int]:
    """Get row counts for all tables in the database."""
    table_counts = {}
    
    # Get all table names from SQLAlchemy metadata
    inspector = inspect(session.bind)
    all_tables = inspector.get_table_names()
    
    for table_name in all_tables:
        try:
            # Use raw SQL for reliable counting
            result = session.execute(
                text(f'SELECT COUNT(*) FROM "{table_name}"')
            ).scalar()
            table_counts[table_name] = result or 0
        except Exception as e:
            # If table doesn't exist or error, set to 0
            table_counts[table_name] = 0
    
    return table_counts


def generate_database_schema_report() -> str:
    """Generate Database Schema Report section."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Database Schema Report")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        table_counts = get_all_table_counts(session)
        categories = get_table_categories()
        
        # Summary
        total_tables = len(table_counts)
        total_rows = sum(table_counts.values())
        empty_tables = [name for name, count in table_counts.items() if count == 0]
        small_tables = [name for name, count in table_counts.items() if 0 < count < 10]
        
        report_lines.append("## Summary")
        report_lines.append("")
        report_lines.append(f"- **Total Tables:** {total_tables}")
        report_lines.append(f"- **Total Rows Across All Tables:** {total_rows:,}")
        report_lines.append(f"- **Empty Tables:** {len(empty_tables)}")
        report_lines.append(f"- **Small Tables (< 10 rows):** {len(small_tables)}")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # All Tables with Row Counts
        report_lines.append("## All Tables and Row Counts")
        report_lines.append("")
        report_lines.append("| Table Name | Row Count | Category |")
        report_lines.append("|------------|-----------|----------|")
        
        # Sort tables by count (descending)
        sorted_tables = sorted(table_counts.items(), key=lambda x: x[1], reverse=True)
        
        for table_name, count in sorted_tables:
            # Determine category
            category = "other"
            for cat, tables in categories.items():
                if table_name in tables:
                    category = cat
                    break
            
            count_str = f"{count:,}" if count > 0 else "0"
            report_lines.append(f"| {table_name} | {count_str} | {category} |")
        
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Staging vs Production Tables
        report_lines.append("## Staging vs Production Tables")
        report_lines.append("")
        
        staging_tables = [t for t in categories['staging'] if t in table_counts]
        production_tables = [t for t, count in table_counts.items() 
                            if t not in categories['staging'] and t not in categories['infrastructure']]
        
        report_lines.append("### Staging Tables")
        report_lines.append("")
        if staging_tables:
            report_lines.append("| Table Name | Row Count |")
            report_lines.append("|------------|-----------|")
            for table in staging_tables:
                count = table_counts.get(table, 0)
                report_lines.append(f"| {table} | {count:,} |")
        else:
            report_lines.append("No staging tables found.")
        report_lines.append("")
        
        staging_total = sum(table_counts.get(t, 0) for t in staging_tables)
        production_total = sum(table_counts.get(t, 0) for t in production_tables)
        
        report_lines.append(f"**Staging Total:** {staging_total:,} rows")
        report_lines.append(f"**Production Total:** {production_total:,} rows")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Entity Tables
        report_lines.append("## Entity Tables")
        report_lines.append("")
        report_lines.append("| Table Name | Row Count | Description |")
        report_lines.append("|------------|-----------|------------|")
        
        entity_descriptions = {
            'companies': 'Biotech/pharma companies',
            'institutions': 'Academic/hospital/research institutions',
            'drugs': 'Drug entities',
            'drug_chemical_identity': 'Drug chemical identifiers',
            'drug_names': 'Drug name variations',
            'targets': 'Biological targets (proteins, genes)',
            'mechanisms': 'Drug mechanisms of action',
            'diseases': 'Disease entities',
            'disease_names': 'Disease name variations',
        }
        
        entity_tables = [t for t in categories['entity'] if t in table_counts]
        entity_total = 0
        for table in sorted(entity_tables):
            count = table_counts.get(table, 0)
            entity_total += count
            desc = entity_descriptions.get(table, 'Entity table')
            report_lines.append(f"| {table} | {count:,} | {desc} |")
        
        report_lines.append("")
        report_lines.append(f"**Entity Tables Total:** {entity_total:,} rows")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Relationship/Edge Tables
        report_lines.append("## Relationship/Edge Tables")
        report_lines.append("")
        report_lines.append("| Table Name | Row Count | Description |")
        report_lines.append("|------------|-----------|------------|")
        
        relationship_descriptions = {
            'company_ownership_history': 'Company ownership relationships',
            'company_drugs': 'Company-drug associations',
            'drug_ownership_history': 'Drug ownership history',
            'drug_targets': 'Drug-target relationships',
            'drug_mechanisms': 'Drug-mechanism relationships',
            'drug_indications': 'Drug-disease indications',
            'drug_combinations': 'Drug combination therapies',
            'trial_sponsors': 'Trial sponsor relationships',
            'trial_funding': 'Trial funding sources',
            'trial_drugs': 'Trial-drug relationships',
            'trial_diseases': 'Trial-disease relationships',
            'publication_drugs': 'Publication-drug mentions',
            'publication_trials': 'Publication-trial references',
            'publication_companies': 'Publication-company mentions',
            'patent_drugs': 'Patent-drug associations',
            'patent_companies': 'Patent-company associations',
            'regulatory_drug_events': 'Regulatory events for drugs',
            'regulatory_company_events': 'Regulatory events for companies',
            'presentation_drugs': 'Conference presentation-drug links',
            'presentation_companies': 'Conference presentation-company links',
            'presentation_trials': 'Conference presentation-trial links',
            'filing_companies': 'SEC filing-company links',
            'filing_drugs': 'SEC filing-drug mentions',
        }
        
        relationship_tables = [t for t in categories['relationship'] if t in table_counts]
        relationship_total = 0
        for table in sorted(relationship_tables):
            count = table_counts.get(table, 0)
            relationship_total += count
            desc = relationship_descriptions.get(table, 'Relationship table')
            report_lines.append(f"| {table} | {count:,} | {desc} |")
        
        report_lines.append("")
        report_lines.append(f"**Relationship Tables Total:** {relationship_total:,} rows")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Clinical Tables
        report_lines.append("## Clinical Tables")
        report_lines.append("")
        report_lines.append("| Table Name | Row Count | Description |")
        report_lines.append("|------------|-----------|------------|")
        
        clinical_descriptions = {
            'clinical_trials': 'Clinical trial records',
            'trial_status_history': 'Trial status change history',
            'regulatory_events': 'Regulatory events (approvals, rejections, etc.)',
        }
        
        clinical_tables = [t for t in categories['clinical'] if t in table_counts]
        clinical_total = 0
        for table in sorted(clinical_tables):
            count = table_counts.get(table, 0)
            clinical_total += count
            desc = clinical_descriptions.get(table, 'Clinical table')
            report_lines.append(f"| {table} | {count:,} | {desc} |")
        
        report_lines.append("")
        report_lines.append(f"**Clinical Tables Total:** {clinical_total:,} rows")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Publication Tables
        report_lines.append("## Publication Tables")
        report_lines.append("")
        report_lines.append("| Table Name | Row Count | Description |")
        report_lines.append("|------------|-----------|------------|")
        
        publication_descriptions = {
            'publications': 'Scientific publications',
            'patents': 'Patent records',
            'conferences': 'Conference records',
            'conference_presentations': 'Conference presentations',
            'sec_filings': 'SEC filing records',
        }
        
        publication_tables = [t for t in categories['publication'] if t in table_counts]
        publication_total = 0
        for table in sorted(publication_tables):
            count = table_counts.get(table, 0)
            publication_total += count
            desc = publication_descriptions.get(table, 'Publication table')
            report_lines.append(f"| {table} | {count:,} | {desc} |")
        
        report_lines.append("")
        report_lines.append(f"**Publication Tables Total:** {publication_total:,} rows")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Empty or Suspiciously Small Tables
        report_lines.append("## Empty or Suspiciously Small Tables")
        report_lines.append("")
        
        if empty_tables:
            report_lines.append("### Empty Tables (0 rows)")
            report_lines.append("")
            report_lines.append("| Table Name | Category |")
            report_lines.append("|------------|----------|")
            for table in sorted(empty_tables):
                category = "other"
                for cat, tables in categories.items():
                    if table in tables:
                        category = cat
                        break
                report_lines.append(f"| {table} | {category} |")
            report_lines.append("")
        
        if small_tables:
            report_lines.append("### Small Tables (< 10 rows)")
            report_lines.append("")
            report_lines.append("| Table Name | Row Count | Category |")
            report_lines.append("|------------|-----------|----------|")
            for table in sorted(small_tables):
                count = table_counts.get(table, 0)
                category = "other"
                for cat, tables in categories.items():
                    if table in tables:
                        category = cat
                        break
                report_lines.append(f"| {table} | {count:,} | {category} |")
            report_lines.append("")
        
        if not empty_tables and not small_tables:
            report_lines.append("✅ All tables have data (≥ 10 rows).")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Infrastructure Tables
        report_lines.append("## Infrastructure Tables")
        report_lines.append("")
        report_lines.append("| Table Name | Row Count | Description |")
        report_lines.append("|------------|-----------|------------|")
        
        infrastructure_descriptions = {
            'sources': 'Data source metadata',
            'data_lineage': 'Data provenance tracking',
            'entity_merges': 'Entity merge audit trail',
            'events': 'Event stream records',
        }
        
        infrastructure_tables = [t for t in categories['infrastructure'] if t in table_counts]
        for table in sorted(infrastructure_tables):
            count = table_counts.get(table, 0)
            desc = infrastructure_descriptions.get(table, 'Infrastructure table')
            report_lines.append(f"| {table} | {count:,} | {desc} |")
        
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Resolution Tables
        report_lines.append("## Entity Resolution Tables")
        report_lines.append("")
        report_lines.append("| Table Name | Row Count | Description |")
        report_lines.append("|------------|-----------|------------|")
        
        resolution_descriptions = {
            'entity_aliases': 'Entity alias mappings',
            'entity_matches': 'Entity match records',
            'entity_match_confidence': 'Match confidence scores',
            'matching_review_queue': 'Matches pending review',
            'entity_match_candidates': 'Potential matches',
            'entity_matching_rules': 'Matching rules configuration',
            'source_processing_log': 'Source processing audit log',
            'data_quality_metrics': 'Data quality statistics',
        }
        
        resolution_tables = [t for t in categories['resolution'] if t in table_counts]
        resolution_total = 0
        for table in sorted(resolution_tables):
            count = table_counts.get(table, 0)
            resolution_total += count
            desc = resolution_descriptions.get(table, 'Resolution table')
            report_lines.append(f"| {table} | {count:,} | {desc} |")
        
        report_lines.append("")
        report_lines.append(f"**Resolution Tables Total:** {resolution_total:,} rows")
        report_lines.append("")
    
    return "\n".join(report_lines)


def generate_pipeline_flow_report() -> str:
    """Generate Data Pipeline Flow Report showing the funnel for key entity types."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Data Pipeline Flow Report")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("This report traces the flow of data through the pipeline for key entity types.")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        # Key sources that produce companies, drugs, and trials
        key_sources = {
            'companies': ['clinicaltrials_gov', 'sec_edgar', 'fda_drugs', 'openfda', 'pubmed'],
            'drugs': ['clinicaltrials_gov', 'fda_drugs', 'openfda', 'pubmed'],
            'trials': ['clinicaltrials_gov'],
        }
        
        # Overall staging statistics
        total_staging = session.query(func.count(StagingRawData.staging_id)).filter(
            StagingRawData.deleted_at.is_(None)
        ).scalar() or 0
        
        processed_staging = session.query(func.count(StagingRawData.staging_id)).filter(
            StagingRawData.processed == True,
            StagingRawData.deleted_at.is_(None)
        ).scalar() or 0
        
        unprocessed_staging = total_staging - processed_staging
        
        report_lines.append("## Overall Pipeline Statistics")
        report_lines.append("")
        report_lines.append(f"- **Total Records in Staging:** {total_staging:,}")
        report_lines.append(f"- **Processed Records:** {processed_staging:,} ({processed_staging/total_staging*100:.1f}%)" if total_staging > 0 else "- **Processed Records:** 0")
        report_lines.append(f"- **Unprocessed Records:** {unprocessed_staging:,} ({unprocessed_staging/total_staging*100:.1f}%)" if total_staging > 0 else "- **Unprocessed Records:** 0")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # For each entity type, trace the flow
        for entity_type, sources in key_sources.items():
            report_lines.append(f"## {entity_type.capitalize()} Flow")
            report_lines.append("")
            
            # Get staging records for these sources
            staging_by_source = {}
            processed_by_source = {}
            unprocessed_by_source = {}
            
            for source in sources:
                total = session.query(func.count(StagingRawData.staging_id)).filter(
                    StagingRawData.source_system == source,
                    StagingRawData.deleted_at.is_(None)
                ).scalar() or 0
                
                processed = session.query(func.count(StagingRawData.staging_id)).filter(
                    StagingRawData.source_system == source,
                    StagingRawData.processed == True,
                    StagingRawData.deleted_at.is_(None)
                ).scalar() or 0
                
                staging_by_source[source] = total
                processed_by_source[source] = processed
                unprocessed_by_source[source] = total - processed
            
            # Get entity counts from lineage or direct count
            if entity_type == 'companies':
                entity_count = session.query(func.count(Company.company_id)).filter(
                    Company.deleted_at.is_(None)
                ).scalar() or 0
                
                # Count companies from key sources via lineage
                companies_from_sources = session.query(func.count(func.distinct(DataLineage.record_id))).filter(
                    DataLineage.table_name == 'companies',
                    DataLineage.deleted_at.is_(None)
                ).scalar() or 0
                
            elif entity_type == 'drugs':
                entity_count = session.query(func.count(Drug.drug_id)).filter(
                    Drug.deleted_at.is_(None)
                ).scalar() or 0
                
                drugs_from_sources = session.query(func.count(func.distinct(DataLineage.record_id))).filter(
                    DataLineage.table_name == 'drugs',
                    DataLineage.deleted_at.is_(None)
                ).scalar() or 0
                
            elif entity_type == 'trials':
                entity_count = session.query(func.count(ClinicalTrial.trial_id)).filter(
                    ClinicalTrial.deleted_at.is_(None)
                ).scalar() or 0
                
                trials_from_sources = session.query(func.count(func.distinct(DataLineage.record_id))).filter(
                    DataLineage.table_name == 'clinical_trials',
                    DataLineage.deleted_at.is_(None)
                ).scalar() or 0
            
            # Get relationship counts
            if entity_type == 'companies':
                # Company-drug relationships
                rel_count = session.query(func.count(CompanyDrug.id)).filter(
                    CompanyDrug.deleted_at.is_(None)
                ).scalar() or 0
                
            elif entity_type == 'drugs':
                # Drug-trial relationships (composite primary key - count distinct pairs)
                rel_count = session.query(func.count(TrialDrug.trial_id)).filter(
                    TrialDrug.deleted_at.is_(None)
                ).scalar() or 0
                
            elif entity_type == 'trials':
                # Trial relationships (sponsors, drugs, diseases) - all use composite primary keys
                sponsor_count = session.query(func.count(TrialSponsor.trial_id)).filter(
                    TrialSponsor.deleted_at.is_(None)
                ).scalar() or 0
                drug_count = session.query(func.count(TrialDrug.trial_id)).filter(
                    TrialDrug.deleted_at.is_(None)
                ).scalar() or 0
                disease_count = session.query(func.count(TrialDisease.trial_id)).filter(
                    TrialDisease.deleted_at.is_(None)
                ).scalar() or 0
                rel_count = sponsor_count + drug_count + disease_count
            
            # Build funnel table
            total_staging_for_type = sum(staging_by_source.values())
            total_processed_for_type = sum(processed_by_source.values())
            
            report_lines.append("### Funnel Analysis")
            report_lines.append("")
            report_lines.append("| Stage | Count | % of Previous | % of Initial |")
            report_lines.append("|-------|-------|--------------|-------------|")
            
            # Stage 1: Raw records in staging
            report_lines.append(f"| **1. Raw Records in Staging** | {total_staging_for_type:,} | 100.0% | 100.0% |")
            
            # Stage 2: Processed records
            if total_staging_for_type > 0:
                pct_of_prev = (total_processed_for_type / total_staging_for_type) * 100
                report_lines.append(f"| **2. Processed Records** | {total_processed_for_type:,} | {pct_of_prev:.1f}% | {pct_of_prev:.1f}% |")
            else:
                report_lines.append(f"| **2. Processed Records** | 0 | N/A | 0.0% |")
            
            # Stage 3: Resolved entities
            if entity_type == 'companies':
                entities_tracked = companies_from_sources
            elif entity_type == 'drugs':
                entities_tracked = drugs_from_sources
            elif entity_type == 'trials':
                entities_tracked = trials_from_sources
            else:
                entities_tracked = entity_count
            
            if total_processed_for_type > 0:
                pct_of_prev = (entities_tracked / total_processed_for_type) * 100 if total_processed_for_type > 0 else 0
                pct_of_initial = (entities_tracked / total_staging_for_type) * 100 if total_staging_for_type > 0 else 0
                report_lines.append(f"| **3. Resolved Entities Created** | {entity_count:,} | {pct_of_prev:.1f}% | {pct_of_initial:.1f}% |")
            else:
                report_lines.append(f"| **3. Resolved Entities Created** | {entity_count:,} | N/A | 0.0% |")
            
            # Stage 4: Relationships created
            if entity_type == 'trials':
                if total_processed_for_type > 0:
                    pct_of_prev = (rel_count / total_processed_for_type) * 100 if total_processed_for_type > 0 else 0
                    pct_of_initial = (rel_count / total_staging_for_type) * 100 if total_staging_for_type > 0 else 0
                    report_lines.append(f"| **4. Relationships Created** | {rel_count:,} | {pct_of_prev:.1f}% | {pct_of_initial:.1f}% |")
                else:
                    report_lines.append(f"| **4. Relationships Created** | {rel_count:,} | N/A | 0.0% |")
            else:
                if entity_count > 0:
                    pct_of_prev = (rel_count / entity_count) * 100 if entity_count > 0 else 0
                    pct_of_initial = (rel_count / total_staging_for_type) * 100 if total_staging_for_type > 0 else 0
                    report_lines.append(f"| **4. Relationships Created** | {rel_count:,} | {pct_of_prev:.1f}% | {pct_of_initial:.1f}% |")
                else:
                    report_lines.append(f"| **4. Relationships Created** | {rel_count:,} | N/A | 0.0% |")
            
            report_lines.append("")
            
            # Loss analysis
            report_lines.append("### Loss Analysis")
            report_lines.append("")
            
            if total_staging_for_type > 0:
                lost_at_stage2 = total_staging_for_type - total_processed_for_type
                lost_at_stage3 = total_processed_for_type - entity_count if total_processed_for_type > entity_count else 0
                
                report_lines.append(f"- **Lost at Stage 2 (Not Processed):** {lost_at_stage2:,} ({lost_at_stage2/total_staging_for_type*100:.1f}%)")
                if lost_at_stage2 > 0:
                    report_lines.append("  - Records in staging but not yet processed")
                
                if lost_at_stage3 > 0:
                    report_lines.append(f"- **Lost at Stage 3 (No Entity Created):** {lost_at_stage3:,} ({lost_at_stage3/total_staging_for_type*100:.1f}%)")
                    report_lines.append("  - Records processed but no entity created (may be duplicates, validation failures, etc.)")
                else:
                    report_lines.append("- **Lost at Stage 3:** 0 (All processed records created entities)")
            else:
                report_lines.append("- No staging records found for these sources")
            
            report_lines.append("")
            
            # Breakdown by source
            report_lines.append("### Breakdown by Source")
            report_lines.append("")
            report_lines.append("| Source | Staging Records | Processed | Unprocessed | Entities Created |")
            report_lines.append("|--------|----------------|------------|-------------|------------------|")
            
            for source in sources:
                staging = staging_by_source.get(source, 0)
                processed = processed_by_source.get(source, 0)
                unprocessed = unprocessed_by_source.get(source, 0)
                
                # Count entities from this source via lineage
                if entity_type == 'companies':
                    entities_from_source = session.query(func.count(func.distinct(DataLineage.record_id))).join(
                        Source, DataLineage.source_id == Source.source_id
                    ).filter(
                        DataLineage.table_name == 'companies',
                        Source.source_name == source,
                        DataLineage.deleted_at.is_(None)
                    ).scalar() or 0
                elif entity_type == 'drugs':
                    entities_from_source = session.query(func.count(func.distinct(DataLineage.record_id))).join(
                        Source, DataLineage.source_id == Source.source_id
                    ).filter(
                        DataLineage.table_name == 'drugs',
                        Source.source_name == source,
                        DataLineage.deleted_at.is_(None)
                    ).scalar() or 0
                elif entity_type == 'trials':
                    entities_from_source = session.query(func.count(func.distinct(DataLineage.record_id))).join(
                        Source, DataLineage.source_id == Source.source_id
                    ).filter(
                        DataLineage.table_name == 'clinical_trials',
                        Source.source_name == source,
                        DataLineage.deleted_at.is_(None)
                    ).scalar() or 0
                else:
                    entities_from_source = 0
                
                report_lines.append(f"| {source} | {staging:,} | {processed:,} | {unprocessed:,} | {entities_from_source:,} |")
            
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")
        
        # Detailed relationship breakdown for trials
        report_lines.append("## Trial Relationships Breakdown")
        report_lines.append("")
        
        sponsor_count = session.query(func.count(TrialSponsor.trial_id)).filter(
            TrialSponsor.deleted_at.is_(None)
        ).scalar() or 0
        
        drug_count = session.query(func.count(TrialDrug.trial_id)).filter(
            TrialDrug.deleted_at.is_(None)
        ).scalar() or 0
        
        disease_count = session.query(func.count(TrialDisease.trial_id)).filter(
            TrialDisease.deleted_at.is_(None)
        ).scalar() or 0
        
        trial_count = session.query(func.count(ClinicalTrial.trial_id)).filter(
            ClinicalTrial.deleted_at.is_(None)
        ).scalar() or 0
        
        report_lines.append("| Relationship Type | Count | Avg per Trial |")
        report_lines.append("|-------------------|-------|---------------|")
        
        if trial_count > 0:
            report_lines.append(f"| Trial Sponsors | {sponsor_count:,} | {sponsor_count/trial_count:.1f} |")
            report_lines.append(f"| Trial Drugs | {drug_count:,} | {drug_count/trial_count:.1f} |")
            report_lines.append(f"| Trial Diseases | {disease_count:,} | {disease_count/trial_count:.1f} |")
        else:
            report_lines.append(f"| Trial Sponsors | {sponsor_count:,} | N/A |")
            report_lines.append(f"| Trial Drugs | {drug_count:,} | N/A |")
            report_lines.append(f"| Trial Diseases | {disease_count:,} | N/A |")
        
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Processing errors analysis
        report_lines.append("## Processing Errors Analysis")
        report_lines.append("")
        
        records_with_errors = session.query(func.count(StagingRawData.staging_id)).filter(
            StagingRawData.processing_errors.isnot(None),
            StagingRawData.deleted_at.is_(None)
        ).scalar() or 0
        
        failed_processing_logs = session.query(func.count(SourceProcessingLog.log_id)).filter(
            SourceProcessingLog.processing_status == 'failed',
            SourceProcessingLog.deleted_at.is_(None)
        ).scalar() or 0
        
        report_lines.append(f"- **Staging Records with Processing Errors:** {records_with_errors:,}")
        report_lines.append(f"- **Failed Processing Logs:** {failed_processing_logs:,}")
        report_lines.append("")
        
        if records_with_errors > 0 or failed_processing_logs > 0:
            report_lines.append("### Error Breakdown by Source")
            report_lines.append("")
            report_lines.append("| Source | Staging Errors | Failed Processing Logs |")
            report_lines.append("|--------|----------------|----------------------|")
            
            for source in set(key_sources['companies'] + key_sources['drugs'] + key_sources['trials']):
                staging_errors = session.query(func.count(StagingRawData.staging_id)).filter(
                    StagingRawData.source_system == source,
                    StagingRawData.processing_errors.isnot(None),
                    StagingRawData.deleted_at.is_(None)
                ).scalar() or 0
                
                failed_logs = session.query(func.count(SourceProcessingLog.log_id)).filter(
                    SourceProcessingLog.source_name == source,
                    SourceProcessingLog.processing_status == 'failed',
                    SourceProcessingLog.deleted_at.is_(None)
                ).scalar() or 0
                
                if staging_errors > 0 or failed_logs > 0:
                    report_lines.append(f"| {source} | {staging_errors:,} | {failed_logs:,} |")
        else:
            report_lines.append("✅ No processing errors found.")
        
        report_lines.append("")
    
    return "\n".join(report_lines)


def generate_entity_resolution_coverage_report() -> str:
    """Generate Entity Resolution Coverage Report."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Entity Resolution Coverage Report")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("This report shows entity resolution coverage metrics and identifies unresolved records.")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        # Define entity types and their models
        entity_types = {
            'company': {
                'model': Company,
                'id_col': Company.company_id,
                'table': 'companies',
            },
            'drug': {
                'model': Drug,
                'id_col': Drug.drug_id,
                'table': 'drugs',
            },
            'disease': {
                'model': Disease,
                'id_col': Disease.disease_id,
                'table': 'diseases',
            },
            'trial': {
                'model': ClinicalTrial,
                'id_col': ClinicalTrial.trial_id,
                'table': 'clinical_trials',
            },
            'institution': {
                'model': Institution,
                'id_col': Institution.institution_id,
                'table': 'institutions',
            },
        }
        
        report_lines.append("## Overall Resolution Statistics")
        report_lines.append("")
        
        # Total entities by type
        total_entities = {}
        entities_with_aliases = {}
        entities_in_lineage = {}
        
        for entity_type, config in entity_types.items():
            model = config['model']
            total = session.query(func.count(config['id_col'])).filter(
                model.deleted_at.is_(None)
            ).scalar() or 0
            total_entities[entity_type] = total
            
            # Count entities with aliases
            with_aliases = session.query(func.count(func.distinct(EntityAlias.entity_id))).filter(
                EntityAlias.entity_type == entity_type,
                EntityAlias.deleted_at.is_(None)
            ).scalar() or 0
            entities_with_aliases[entity_type] = with_aliases
            
            # Count entities tracked in lineage
            in_lineage = session.query(func.count(func.distinct(DataLineage.record_id))).filter(
                DataLineage.table_name == config['table'],
                DataLineage.deleted_at.is_(None)
            ).scalar() or 0
            entities_in_lineage[entity_type] = in_lineage
        
        # Match candidates needing review
        match_candidates_count = session.query(func.count(EntityMatchCandidate.candidate_id)).filter(
            EntityMatchCandidate.deleted_at.is_(None)
        ).scalar() or 0
        
        review_queue_count = session.query(func.count(MatchingReviewQueue.queue_id)).filter(
            MatchingReviewQueue.deleted_at.is_(None)
        ).scalar() or 0
        
        report_lines.append(f"- **Total Entities:** {sum(total_entities.values()):,}")
        report_lines.append(f"- **Entities with Aliases:** {sum(entities_with_aliases.values()):,}")
        report_lines.append(f"- **Entities Tracked in Lineage:** {sum(entities_in_lineage.values()):,}")
        report_lines.append(f"- **Match Candidates:** {match_candidates_count:,}")
        report_lines.append(f"- **In Review Queue:** {review_queue_count:,}")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Coverage by entity type
        report_lines.append("## Coverage by Entity Type")
        report_lines.append("")
        report_lines.append("| Entity Type | Total Entities | With Aliases | In Lineage | Alias Coverage | Lineage Coverage |")
        report_lines.append("|-------------|----------------|--------------|------------|----------------|------------------|")
        
        for entity_type, config in entity_types.items():
            total = total_entities[entity_type]
            with_aliases = entities_with_aliases[entity_type]
            in_lineage = entities_in_lineage[entity_type]
            
            alias_coverage = (with_aliases / total * 100) if total > 0 else 0
            lineage_coverage = (in_lineage / total * 100) if total > 0 else 0
            
            report_lines.append(f"| {entity_type} | {total:,} | {with_aliases:,} | {in_lineage:,} | {alias_coverage:.1f}% | {lineage_coverage:.1f}% |")
        
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Resolution success rate from processing logs
        report_lines.append("## Resolution Success Rate from Processing")
        report_lines.append("")
        
        # Get processing statistics
        total_processed = session.query(func.count(SourceProcessingLog.log_id)).filter(
            SourceProcessingLog.deleted_at.is_(None)
        ).scalar() or 0
        
        successful_processing = session.query(func.count(SourceProcessingLog.log_id)).filter(
            SourceProcessingLog.processing_status == 'success',
            SourceProcessingLog.deleted_at.is_(None)
        ).scalar() or 0
        
        failed_processing = session.query(func.count(SourceProcessingLog.log_id)).filter(
            SourceProcessingLog.processing_status == 'failed',
            SourceProcessingLog.deleted_at.is_(None)
        ).scalar() or 0
        
        needs_review_processing = session.query(func.count(SourceProcessingLog.log_id)).filter(
            SourceProcessingLog.processing_status == 'needs_review',
            SourceProcessingLog.deleted_at.is_(None)
        ).scalar() or 0
        
        # Aggregate entity extraction stats
        total_extracted = session.query(func.sum(SourceProcessingLog.entities_extracted)).filter(
            SourceProcessingLog.deleted_at.is_(None)
        ).scalar() or 0
        
        total_matched = session.query(func.sum(SourceProcessingLog.entities_matched)).filter(
            SourceProcessingLog.deleted_at.is_(None)
        ).scalar() or 0
        
        total_created = session.query(func.sum(SourceProcessingLog.entities_created)).filter(
            SourceProcessingLog.deleted_at.is_(None)
        ).scalar() or 0
        
        report_lines.append("### Processing Status")
        report_lines.append("")
        report_lines.append("| Status | Count | Percentage |")
        report_lines.append("|--------|-------|------------|")
        
        if total_processed > 0:
            report_lines.append(f"| Success | {successful_processing:,} | {successful_processing/total_processed*100:.1f}% |")
            report_lines.append(f"| Failed | {failed_processing:,} | {failed_processing/total_processed*100:.1f}% |")
            report_lines.append(f"| Needs Review | {needs_review_processing:,} | {needs_review_processing/total_processed*100:.1f}% |")
        else:
            report_lines.append("| No processing logs found |")
        
        report_lines.append("")
        report_lines.append("### Entity Extraction & Resolution")
        report_lines.append("")
        report_lines.append("| Metric | Count |")
        report_lines.append("|--------|-------|")
        report_lines.append(f"| Total Entities Extracted | {total_extracted:,} |")
        report_lines.append(f"| Entities Matched (Existing) | {total_matched:,} |")
        report_lines.append(f"| Entities Created (New) | {total_created:,} |")
        
        if total_extracted > 0:
            match_rate = (total_matched / total_extracted) * 100
            create_rate = (total_created / total_extracted) * 100
            report_lines.append("")
            report_lines.append(f"- **Match Rate:** {match_rate:.1f}%")
            report_lines.append(f"- **Creation Rate:** {create_rate:.1f}%")
            report_lines.append(f"- **Total Resolution Rate:** {(match_rate + create_rate):.1f}%")
        
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Failed resolution reasons
        report_lines.append("## Failed Resolution Analysis")
        report_lines.append("")
        
        # Get failed processing logs with errors
        failed_logs = session.query(SourceProcessingLog).filter(
            SourceProcessingLog.processing_status == 'failed',
            SourceProcessingLog.deleted_at.is_(None)
        ).order_by(SourceProcessingLog.processing_started_at.desc()).limit(20).all()
        
        if failed_logs:
            report_lines.append(f"### Recent Failed Processing Logs ({len(failed_logs)} shown)")
            report_lines.append("")
            report_lines.append("| Source | Record ID | Date | Errors |")
            report_lines.append("|--------|-----------|------|--------|")
            
            for log in failed_logs[:10]:  # Show top 10
                errors_str = "; ".join(log.errors[:2]) if log.errors else "No error details"
                errors_str = errors_str[:100] + "..." if len(errors_str) > 100 else errors_str
                date_str = log.processing_started_at.strftime('%Y-%m-%d') if log.processing_started_at else "N/A"
                report_lines.append(f"| {log.source_name} | {log.source_identifier[:30]}... | {date_str} | {errors_str} |")
        else:
            report_lines.append("✅ No failed processing logs found.")
        
        report_lines.append("")
        
        # Match candidates analysis
        if match_candidates_count > 0:
            report_lines.append("### Match Candidates by Entity Type")
            report_lines.append("")
            report_lines.append("| Entity Type | Count |")
            report_lines.append("|-------------|-------|")
            
            for entity_type in entity_types.keys():
                count = session.query(func.count(EntityMatchCandidate.candidate_id)).filter(
                    EntityMatchCandidate.entity_type == entity_type,
                    EntityMatchCandidate.deleted_at.is_(None)
                ).scalar() or 0
                if count > 0:
                    report_lines.append(f"| {entity_type} | {count:,} |")
        else:
            report_lines.append("✅ No match candidates requiring review.")
        
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Examples of unresolved records
        report_lines.append("## Examples of Unresolved Records")
        report_lines.append("")
        
        # Get match candidates as examples
        candidates = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.deleted_at.is_(None)
        ).order_by(EntityMatchCandidate.created_at.desc()).limit(10).all()
        
        if candidates:
            report_lines.append("### Match Candidates (Needs Review)")
            report_lines.append("")
            
            for i, candidate in enumerate(candidates[:5], 1):  # Show top 5
                report_lines.append(f"#### Example {i}: {candidate.entity_type}")
                report_lines.append("")
                report_lines.append(f"- **Extracted Text:** {candidate.extracted_text[:100]}")
                report_lines.append(f"- **Source:** {candidate.source_name}")
                report_lines.append(f"- **Source Identifier:** {candidate.source_identifier[:50]}")
                if candidate.potential_matches:
                    matches_count = len(candidate.potential_matches) if isinstance(candidate.potential_matches, list) else 0
                    report_lines.append(f"- **Potential Matches Found:** {matches_count}")
                if candidate.status:
                    report_lines.append(f"- **Status:** {candidate.status}")
                if candidate.match_confidence:
                    report_lines.append(f"- **Match Confidence:** {float(candidate.match_confidence):.2f}")
                report_lines.append("")
        else:
            report_lines.append("✅ No unresolved match candidates found.")
        
        # Get staging records that failed processing
        failed_staging = session.query(StagingRawData).filter(
            StagingRawData.processing_errors.isnot(None),
            StagingRawData.deleted_at.is_(None)
        ).order_by(StagingRawData.ingested_at.desc()).limit(10).all()
        
        if failed_staging:
            report_lines.append("### Staging Records with Processing Errors")
            report_lines.append("")
            
            for i, record in enumerate(failed_staging[:5], 1):  # Show top 5
                report_lines.append(f"#### Example {i}: {record.source_system}")
                report_lines.append("")
                report_lines.append(f"- **Record ID:** {record.source_record_id[:50]}")
                report_lines.append(f"- **Ingested:** {record.ingested_at.strftime('%Y-%m-%d %H:%M') if record.ingested_at else 'N/A'}")
                error_preview = record.processing_errors[:200] + "..." if record.processing_errors and len(record.processing_errors) > 200 else (record.processing_errors or "No error details")
                report_lines.append(f"- **Error:** {error_preview}")
                report_lines.append("")
        else:
            report_lines.append("✅ No staging records with processing errors found.")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Resolution quality metrics
        report_lines.append("## Resolution Quality Metrics")
        report_lines.append("")
        
        # Average confidence scores from potential_matches if available
        # EntityMatchCandidate stores confidence in potential_matches JSONB field
        # For now, we'll skip detailed confidence analysis if the field structure is complex
        if match_candidates_count > 0:
            report_lines.append(f"- **Total Match Candidates:** {match_candidates_count:,}")
            report_lines.append("  - Note: Confidence scores are stored in potential_matches JSONB field")
        
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Aliases statistics
        report_lines.append("## Entity Aliases Statistics")
        report_lines.append("")
        
        total_aliases = session.query(func.count(EntityAlias.alias_id)).filter(
            EntityAlias.deleted_at.is_(None)
        ).scalar() or 0
        
        aliases_by_type = {}
        for entity_type in entity_types.keys():
            count = session.query(func.count(EntityAlias.alias_id)).filter(
                EntityAlias.entity_type == entity_type,
                EntityAlias.deleted_at.is_(None)
            ).scalar() or 0
            aliases_by_type[entity_type] = count
        
        report_lines.append(f"- **Total Aliases:** {total_aliases:,}")
        report_lines.append("")
        report_lines.append("### Aliases by Entity Type")
        report_lines.append("")
        report_lines.append("| Entity Type | Alias Count | Avg per Entity |")
        report_lines.append("|-------------|-------------|----------------|")
        
        for entity_type, count in aliases_by_type.items():
            total_ents = total_entities[entity_type]
            avg = (count / total_ents) if total_ents > 0 else 0
            report_lines.append(f"| {entity_type} | {count:,} | {avg:.1f} |")
        
        report_lines.append("")
    
    return "\n".join(report_lines)


def generate_scoring_system_report() -> str:
    """Generate Scoring System Report."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Scoring System Report")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("This report documents the scoring system implementation and current score distribution.")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        # Scoring system location and structure
        report_lines.append("## Scoring System Location")
        report_lines.append("")
        report_lines.append("### Primary Implementation")
        report_lines.append("")
        report_lines.append("- **File:** `src/services/company_risk_service.py`")
        report_lines.append("- **Class:** `CompanyRiskService`")
        report_lines.append("- **Main Function:** `calculate_company_risk_score(company_id: UUID)`")
        report_lines.append("")
        report_lines.append("### Supporting Files")
        report_lines.append("")
        report_lines.append("- **API Routes:** `src/api/routes/company_risk.py`")
        report_lines.append("- **Data Models:** `src/api/models/company_risk.py`")
        report_lines.append("- **Cache Configuration:** `src/services/cache_config.py`")
        report_lines.append("- **Database View:** `database/migrations/versions/f1a2b3c4d5e6_add_company_risk_metrics_view.py`")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Scoring algorithm details
        report_lines.append("## Scoring Algorithm")
        report_lines.append("")
        report_lines.append("### Score Range")
        report_lines.append("- **Range:** 0-100")
        report_lines.append("- **Higher score = Higher risk**")
        report_lines.append("")
        report_lines.append("### Component Weights")
        report_lines.append("")
        report_lines.append("| Component | Weight | Description |")
        report_lines.append("|-----------|--------|-------------|")
        report_lines.append("| Failure Rate | 40 points | Historical trial termination rate |")
        report_lines.append("| Recent Failures | 30 points | Failures in last 12 months |")
        report_lines.append("| Pipeline Stagnation | 20 points | Days since last pipeline update |")
        report_lines.append("| Warning Signals | 10 points | Early warning indicators |")
        report_lines.append("| **Total** | **100 points** | |")
        report_lines.append("")
        report_lines.append("### Risk Categories")
        report_lines.append("")
        report_lines.append("| Category | Score Range |")
        report_lines.append("|----------|-------------|")
        report_lines.append("| LOW | 0-25 |")
        report_lines.append("| MODERATE | 25-50 |")
        report_lines.append("| HIGH | 50-75 |")
        report_lines.append("| CRITICAL | 75-100 |")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Inputs
        report_lines.append("## Scoring System Inputs")
        report_lines.append("")
        report_lines.append("The scoring system uses the following data sources:")
        report_lines.append("")
        report_lines.append("### 1. Company Metrics (from `get_company_metrics()`)")
        report_lines.append("")
        report_lines.append("- **Source:** `CompanyRiskService.get_company_metrics()`")
        report_lines.append("- **Data Sources:**")
        report_lines.append("  - `companies` table - Company information")
        report_lines.append("  - `clinical_trials` table - Trial records")
        report_lines.append("  - `trial_sponsors` table - Company-trial relationships")
        report_lines.append("  - `events` table - Pipeline events")
        report_lines.append("")
        report_lines.append("- **Metrics Calculated:**")
        report_lines.append("  - Total trials count")
        report_lines.append("  - Active trials count")
        report_lines.append("  - Terminated trials count")
        report_lines.append("  - Success rates by phase (Phase 1, 2, 3)")
        report_lines.append("  - Pipeline velocity (new programs per year)")
        report_lines.append("  - Days since last pipeline update")
        report_lines.append("  - Failure clustering patterns")
        report_lines.append("")
        report_lines.append("### 2. Recent Failure Events")
        report_lines.append("")
        report_lines.append("- **Source:** `FailureAnalysisService.get_program_events()`")
        report_lines.append("- **Data Source:** `events` table")
        report_lines.append("- **Event Types Tracked:**")
        report_lines.append("  - `trial.status.terminated`")
        report_lines.append("  - `trial.status.withdrawn`")
        report_lines.append("  - `regulatory.clinical_hold`")
        report_lines.append("- **Time Window:** Last 12 months")
        report_lines.append("")
        report_lines.append("### 3. Warning Signals")
        report_lines.append("")
        report_lines.append("- **Source:** `CompanyRiskService._get_warning_signals()`")
        report_lines.append("- **Signals Detected:**")
        report_lines.append("  - Layoff announcements")
        report_lines.append("  - Clinical holds")
        report_lines.append("  - Regulatory warnings")
        report_lines.append("  - Pipeline stagnation")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Outputs
        report_lines.append("## Scoring System Outputs")
        report_lines.append("")
        report_lines.append("The scoring system produces the following outputs:")
        report_lines.append("")
        report_lines.append("### Primary Output: Risk Score")
        report_lines.append("")
        report_lines.append("- **Field:** `risk_score`")
        report_lines.append("- **Type:** `float`")
        report_lines.append("- **Range:** 0.0 - 100.0")
        report_lines.append("- **Description:** Composite risk score calculated from all components")
        report_lines.append("")
        report_lines.append("### Secondary Outputs")
        report_lines.append("")
        report_lines.append("1. **Risk Category** (`risk_category`)")
        report_lines.append("   - Values: `LOW`, `MODERATE`, `HIGH`, `CRITICAL`")
        report_lines.append("   - Derived from risk score range")
        report_lines.append("")
        report_lines.append("2. **Component Breakdown** (`components`)")
        report_lines.append("   - `failure_rate`: Score, weight, and details")
        report_lines.append("   - `recent_failures`: Score, weight, and details")
        report_lines.append("   - `pipeline_stagnation`: Score, weight, and details")
        report_lines.append("   - `warning_signals`: Score, weight, and details")
        report_lines.append("")
        report_lines.append("3. **Metadata**")
        report_lines.append("   - `company_id`: Company UUID")
        report_lines.append("   - `company_name`: Company name")
        report_lines.append("   - `calculated_at`: ISO timestamp of calculation")
        report_lines.append("")
        report_lines.append("### Storage")
        report_lines.append("")
        report_lines.append("- **Primary Storage:** Calculated on-demand (not stored in database)")
        report_lines.append("- **Caching:** Redis cache with key `risk_score:{company_id}`")
        report_lines.append("- **Cache TTL:** 1 hour (configurable via `CacheTTL.RISK_SCORE`)")
        report_lines.append("- **Materialized View:** `company_risk_metrics` (contains metrics, not scores)")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Calculate scores for all companies
        report_lines.append("## Current Score Distribution")
        report_lines.append("")
        report_lines.append("Calculating risk scores for all companies...")
        report_lines.append("")
        
        # Get all companies
        all_companies = session.query(Company).filter(
            Company.deleted_at.is_(None)
        ).all()
        
        risk_service = CompanyRiskService(session)
        
        scores = []
        scores_by_category = {
            'LOW': [],
            'MODERATE': [],
            'HIGH': [],
            'CRITICAL': []
        }
        
        companies_with_scores = 0
        companies_with_errors = 0
        
        for company in all_companies:
            try:
                result = risk_service.calculate_company_risk_score(company.company_id)
                
                if 'error' in result:
                    companies_with_errors += 1
                    continue
                
                score = result.get('risk_score', 0)
                category = result.get('risk_category', 'LOW')
                
                scores.append(score)
                scores_by_category[category].append(score)
                companies_with_scores += 1
                
            except Exception as e:
                companies_with_errors += 1
                continue
        
        total_companies = len(all_companies)
        
        report_lines.append(f"- **Total Companies:** {total_companies:,}")
        report_lines.append(f"- **Companies with Scores:** {companies_with_scores:,} ({companies_with_scores/total_companies*100:.1f}%)" if total_companies > 0 else "- **Companies with Scores:** 0")
        report_lines.append(f"- **Companies with Errors:** {companies_with_errors:,}")
        report_lines.append("")
        
        if scores:
            min_score = min(scores)
            max_score = max(scores)
            avg_score = sum(scores) / len(scores)
            median_score = sorted(scores)[len(scores) // 2] if scores else 0
            
            report_lines.append("### Score Statistics")
            report_lines.append("")
            report_lines.append("| Metric | Value |")
            report_lines.append("|--------|-------|")
            report_lines.append(f"| Minimum | {min_score:.2f} |")
            report_lines.append(f"| Maximum | {max_score:.2f} |")
            report_lines.append(f"| Average | {avg_score:.2f} |")
            report_lines.append(f"| Median | {median_score:.2f} |")
            report_lines.append("")
            
            # Distribution by category
            report_lines.append("### Distribution by Risk Category")
            report_lines.append("")
            report_lines.append("| Category | Count | Percentage | Avg Score | Min Score | Max Score |")
            report_lines.append("|----------|-------|------------|-----------|------------|----------|")
            
            for category in ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']:
                cat_scores = scores_by_category[category]
                if cat_scores:
                    count = len(cat_scores)
                    pct = (count / companies_with_scores) * 100 if companies_with_scores > 0 else 0
                    avg = sum(cat_scores) / len(cat_scores)
                    min_cat = min(cat_scores)
                    max_cat = max(cat_scores)
                    report_lines.append(f"| {category} | {count:,} | {pct:.1f}% | {avg:.2f} | {min_cat:.2f} | {max_cat:.2f} |")
                else:
                    report_lines.append(f"| {category} | 0 | 0.0% | N/A | N/A | N/A |")
            
            report_lines.append("")
            
            # Score distribution histogram
            report_lines.append("### Score Distribution (Histogram)")
            report_lines.append("")
            report_lines.append("| Score Range | Count | Percentage |")
            report_lines.append("|-------------|-------|------------|")
            
            ranges = [
                (0, 10, "0-10"),
                (10, 20, "10-20"),
                (20, 30, "20-30"),
                (30, 40, "30-40"),
                (40, 50, "40-50"),
                (50, 60, "50-60"),
                (60, 70, "60-70"),
                (70, 80, "70-80"),
                (80, 90, "80-90"),
                (90, 100, "90-100"),
            ]
            
            for min_val, max_val, label in ranges:
                count = len([s for s in scores if min_val <= s < max_val])
                pct = (count / companies_with_scores) * 100 if companies_with_scores > 0 else 0
                report_lines.append(f"| {label} | {count:,} | {pct:.1f}% |")
            
            report_lines.append("")
        else:
            report_lines.append("⚠️ No scores calculated. This may indicate:")
            report_lines.append("- Companies have no trial data")
            report_lines.append("- Errors in score calculation")
            report_lines.append("- Database connectivity issues")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Implementation details
        report_lines.append("## Implementation Details")
        report_lines.append("")
        report_lines.append("### Calculation Flow")
        report_lines.append("")
        report_lines.append("1. **Check Cache:** Look for cached score in Redis")
        report_lines.append("2. **Get Metrics:** Call `get_company_metrics()` to gather company data")
        report_lines.append("3. **Calculate Components:**")
        report_lines.append("   - Failure Rate: `terminated_count / total_trials * 40`")
        report_lines.append("   - Recent Failures: Based on failures in last 12 months (0-30 points)")
        report_lines.append("   - Pipeline Stagnation: Based on days since last update (0-20 points)")
        report_lines.append("   - Warning Signals: Based on signal count (0-10 points)")
        report_lines.append("4. **Sum Components:** Total = failure_score + recent_score + stagnation_score + warning_score")
        report_lines.append("5. **Determine Category:** Map score to risk category")
        report_lines.append("6. **Cache Result:** Store in Redis with 1-hour TTL")
        report_lines.append("7. **Return Result:** Return dictionary with score, category, and components")
        report_lines.append("")
        report_lines.append("### Key Functions")
        report_lines.append("")
        report_lines.append("- `calculate_company_risk_score(company_id)` - Main scoring function")
        report_lines.append("- `get_company_metrics(company_id)` - Gathers company metrics")
        report_lines.append("- `_get_warning_signals(company_id)` - Detects warning signals")
        report_lines.append("- `_get_risk_category(score)` - Maps score to category")
        report_lines.append("- `_calculate_phase_success_rate(trials)` - Calculates phase success rates")
        report_lines.append("- `_calculate_pipeline_velocity(company_id, trials)` - Calculates pipeline velocity")
        report_lines.append("- `_get_days_since_last_update(company_id)` - Gets days since last update")
        report_lines.append("- `_detect_failure_clustering(company_id)` - Detects failure patterns")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
    
    return "\n".join(report_lines)


def generate_dashboard_ui_report() -> str:
    """Generate Dashboard/UI Report."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Dashboard/UI Report")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("This report documents the dashboard views, pages, and their database queries.")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        # Dashboard structure
        report_lines.append("## Dashboard Structure")
        report_lines.append("")
        report_lines.append("### Technology Stack")
        report_lines.append("")
        report_lines.append("- **Frontend Framework:** React with TypeScript")
        report_lines.append("- **Routing:** React Router v6")
        report_lines.append("- **API Client:** Axios")
        report_lines.append("- **Styling:** Tailwind CSS")
        report_lines.append("- **Charts:** Recharts")
        report_lines.append("- **Backend API:** FastAPI (Python)")
        report_lines.append("")
        report_lines.append("### Application Entry Point")
        report_lines.append("")
        report_lines.append("- **File:** `frontend/src/App.tsx`")
        report_lines.append("- **Routes:**")
        report_lines.append("  - `/` - Company Risk Dashboard (default)")
        report_lines.append("  - `/company/:companyId` - Company Risk Dashboard (with company selected)")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Views/Pages
        report_lines.append("## Views and Pages")
        report_lines.append("")
        
        report_lines.append("### 1. Company Risk Dashboard (Primary View)")
        report_lines.append("")
        report_lines.append("- **File:** `frontend/src/pages/CompanyRiskDashboard.tsx`")
        report_lines.append("- **Route:** `/` or `/company/:companyId`")
        report_lines.append("- **Description:** Main dashboard showing company risk profiles and metrics")
        report_lines.append("")
        report_lines.append("**Two Display Modes:**")
        report_lines.append("")
        report_lines.append("1. **List View (Default):** Shows recent failed trials")
        report_lines.append("   - Component: `FailedTrialsList`")
        report_lines.append("   - Displays: Recent high-risk and failed trials with company risk scores")
        report_lines.append("")
        report_lines.append("2. **Detail View:** Shows detailed company risk profile")
        report_lines.append("   - Components:")
        report_lines.append("     - `RiskScoreCard` - Risk score visualization")
        report_lines.append("     - `MetricsCards` - Company metrics cards")
        report_lines.append("     - `TimelineVisualization` - Event timeline chart")
        report_lines.append("")
        report_lines.append("**Components Used:**")
        report_lines.append("")
        report_lines.append("- `CompanySearchBar` - Company search with autocomplete")
        report_lines.append("- `FailedTrialsList` - List of recent failures")
        report_lines.append("- `RiskScoreCard` - Risk score gauge and component breakdown")
        report_lines.append("- `MetricsCards` - Grid of metric cards")
        report_lines.append("- `TimelineVisualization` - Event timeline chart and list")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Data queries by view
        report_lines.append("## Data Queries by View")
        report_lines.append("")
        
        report_lines.append("### Company Risk Dashboard - Detail View")
        report_lines.append("")
        report_lines.append("When a company is selected, the dashboard makes **3 parallel API calls:**")
        report_lines.append("")
        report_lines.append("#### 1. Risk Profile Query")
        report_lines.append("")
        report_lines.append("- **API Endpoint:** `GET /api/companies/{company_id}/risk-profile`")
        report_lines.append("- **Backend Route:** `src/api/routes/company_risk.py::get_company_risk_profile()`")
        report_lines.append("- **Service Method:** `CompanyRiskService.calculate_company_risk_score()`")
        report_lines.append("- **Database Queries:**")
        report_lines.append("  - `companies` table - Get company information")
        report_lines.append("  - `clinical_trials` + `trial_sponsors` - Get all trials for company")
        report_lines.append("  - `events` table - Get recent failure events (last 12 months)")
        report_lines.append("  - Calculates: Failure rate, recent failures, pipeline stagnation, warning signals")
        report_lines.append("- **Returns:** Risk score (0-100), risk category, component breakdown")
        report_lines.append("")
        report_lines.append("#### 2. Company Metrics Query")
        report_lines.append("")
        report_lines.append("- **API Endpoint:** `GET /api/companies/{company_id}/metrics`")
        report_lines.append("- **Backend Route:** `src/api/routes/company_risk.py::get_company_metrics()`")
        report_lines.append("- **Service Method:** `CompanyRiskService.get_company_metrics()`")
        report_lines.append("- **Database Queries:**")
        report_lines.append("  - `companies` table - Company info")
        report_lines.append("  - `clinical_trials` + `trial_sponsors` - All company trials")
        report_lines.append("  - `events` table - Pipeline events for last update calculation")
        report_lines.append("  - Calculates:")
        report_lines.append("    - Total trials, active trials, terminated count")
        report_lines.append("    - Success rates by phase (Phase 1, 2, 3)")
        report_lines.append("    - Pipeline velocity (new programs per year)")
        report_lines.append("    - Days since last pipeline update")
        report_lines.append("    - Failure clustering patterns")
        report_lines.append("- **Returns:** All company metrics")
        report_lines.append("")
        report_lines.append("#### 3. Company Timeline Query")
        report_lines.append("")
        report_lines.append("- **API Endpoint:** `GET /api/companies/{company_id}/timeline`")
        report_lines.append("- **Backend Route:** `src/api/routes/company_risk.py::get_company_timeline()`")
        report_lines.append("- **Service Method:** `CompanyRiskService.get_company_timeline()`")
        report_lines.append("- **Database Queries:**")
        report_lines.append("  - `events` table - Events where company is in `entities_involved` array")
        report_lines.append("  - `company_drugs` table - Related drugs (if include_related=True)")
        report_lines.append("  - `trial_sponsors` table - Related trials (if include_related=True)")
        report_lines.append("  - Uses PostgreSQL array query: `array_position(entities_involved, company_id) != NULL`")
        report_lines.append("  - Filters: Optional date range, optional event types")
        report_lines.append("- **Returns:** Chronological list of events")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        report_lines.append("### Company Risk Dashboard - List View (Failed Trials)")
        report_lines.append("")
        report_lines.append("#### Recent Failures Query")
        report_lines.append("")
        report_lines.append("- **API Endpoint:** `GET /api/failures/recent?days=90&limit=50`")
        report_lines.append("- **Backend Route:** `src/api/routes/company_risk.py::get_recent_failures()`")
        report_lines.append("- **Service Method:** `FailureTracker.get_recent_failures()`")
        report_lines.append("- **Database Queries:**")
        report_lines.append("  - `events` table - Filter by event types:")
        report_lines.append("    - `trial.status.terminated`")
        report_lines.append("    - `trial.status.withdrawn`")
        report_lines.append("    - `program.milestone.rejected`")
        report_lines.append("    - `regulatory.rejection`")
        report_lines.append("  - Filters: Last N days (default 30, UI uses 90)")
        report_lines.append("  - Enriches with entity details (companies, trials, drugs, diseases)")
        report_lines.append("- **Additional Queries:**")
        report_lines.append("  - For each failure, loads company risk profile to show risk score")
        report_lines.append("  - API: `GET /api/companies/{company_id}/risk-profile` (called per company)")
        report_lines.append("- **Returns:** List of failure events with enriched entity details and risk scores")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        report_lines.append("### Company Search")
        report_lines.append("")
        report_lines.append("#### Company Search Query")
        report_lines.append("")
        report_lines.append("- **Component:** `CompanySearchBar`")
        report_lines.append("- **API Endpoint:** `GET /api/companies/search`")
        report_lines.append("- **Backend Route:** `src/api/routes/company_risk.py::search_companies()`")
        report_lines.append("- **Database Queries:**")
        report_lines.append("  - `companies` table - Base query with name search (ILIKE)")
        report_lines.append("  - Optional joins:")
        report_lines.append("    - `trial_sponsors` + `trial_diseases` + `diseases` - For therapeutic area filter")
        report_lines.append("    - Subquery for trial counts - For min_programs filter")
        report_lines.append("  - For each result:")
        report_lines.append("    - Calls `calculate_company_risk_score()` - Risk score calculation")
        report_lines.append("    - Calls `get_company_metrics()` - Basic metrics")
        report_lines.append("- **Filters Supported:**")
        report_lines.append("  - `q` - Company name search (ILIKE)")
        report_lines.append("  - `risk_category` - Filter by risk category")
        report_lines.append("  - `therapeutic_area` - Filter by disease area")
        report_lines.append("  - `min_programs` - Minimum number of trials")
        report_lines.append("  - `limit` / `offset` - Pagination")
        report_lines.append("- **Returns:** List of companies with risk scores and basic metrics")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Primary company risk view
        report_lines.append("## Primary Company Risk View")
        report_lines.append("")
        report_lines.append("The primary view is the **Company Risk Dashboard Detail View**, which displays:")
        report_lines.append("")
        report_lines.append("### 1. Risk Score Card")
        report_lines.append("")
        report_lines.append("- **Component:** `RiskScoreCard`")
        report_lines.append("- **Data Source:** Risk Profile API response")
        report_lines.append("- **Displays:**")
        report_lines.append("  - Risk score gauge (0-100, semicircle visualization)")
        report_lines.append("  - Risk category badge (LOW, MODERATE, HIGH, CRITICAL)")
        report_lines.append("  - Component breakdown with progress bars:")
        report_lines.append("    - Failure Rate (40 points max)")
        report_lines.append("    - Recent Failures (30 points max)")
        report_lines.append("    - Pipeline Stagnation (20 points max)")
        report_lines.append("    - Warning Signals (10 points max)")
        report_lines.append("")
        report_lines.append("### 2. Metrics Cards")
        report_lines.append("")
        report_lines.append("- **Component:** `MetricsCards`")
        report_lines.append("- **Data Source:** Company Metrics API response")
        report_lines.append("- **Displays (8 cards):**")
        report_lines.append("  - Total Trials")
        report_lines.append("  - Active Trials")
        report_lines.append("  - Terminated Count")
        report_lines.append("  - Pipeline Velocity (programs/year)")
        report_lines.append("  - Phase 1 Success Rate (%)")
        report_lines.append("  - Phase 2 Success Rate (%)")
        report_lines.append("  - Phase 3 Success Rate (%)")
        report_lines.append("  - Days Since Last Update")
        report_lines.append("")
        report_lines.append("### 3. Timeline Visualization")
        report_lines.append("")
        report_lines.append("- **Component:** `TimelineVisualization`")
        report_lines.append("- **Data Source:** Company Timeline API response")
        report_lines.append("- **Displays:**")
        report_lines.append("  - Line chart showing event counts over time by significance level")
        report_lines.append("  - List of recent events (up to 20) with significance indicators")
        report_lines.append("  - Event types and dates")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Database query patterns
        report_lines.append("## Database Query Patterns")
        report_lines.append("")
        report_lines.append("### How the Dashboard Queries the Database")
        report_lines.append("")
        report_lines.append("#### 1. Company Risk Score Calculation")
        report_lines.append("")
        report_lines.append("**Query Pattern:** Multi-step aggregation")
        report_lines.append("")
        report_lines.append("```sql")
        report_lines.append("-- Step 1: Get company trials")
        report_lines.append("SELECT t.* FROM clinical_trials t")
        report_lines.append("JOIN trial_sponsors ts ON t.trial_id = ts.trial_id")
        report_lines.append("WHERE ts.entity_id = :company_id")
        report_lines.append("  AND ts.entity_type = 'company'")
        report_lines.append("  AND ts.deleted_at IS NULL")
        report_lines.append("  AND t.deleted_at IS NULL")
        report_lines.append("")
        report_lines.append("-- Step 2: Get recent failure events")
        report_lines.append("SELECT * FROM events")
        report_lines.append("WHERE array_position(entities_involved, :company_id) IS NOT NULL")
        report_lines.append("  AND event_type IN ('trial.status.terminated', 'trial.status.withdrawn', 'regulatory.clinical_hold')")
        report_lines.append("  AND event_date >= :twelve_months_ago")
        report_lines.append("  AND deleted_at IS NULL")
        report_lines.append("")
        report_lines.append("-- Step 3: Get warning signals (from events)")
        report_lines.append("SELECT * FROM events")
        report_lines.append("WHERE array_position(entities_involved, :company_id) IS NOT NULL")
        report_lines.append("  AND event_type IN ('corporate.layoff', 'regulatory.warning_letter', ...)")
        report_lines.append("  AND deleted_at IS NULL")
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("**Calculation:**")
        report_lines.append("- Failure Rate: `terminated_count / total_trials * 40`")
        report_lines.append("- Recent Failures: Based on count in last 12 months (0-30 points)")
        report_lines.append("- Pipeline Stagnation: Based on days since last event (0-20 points)")
        report_lines.append("- Warning Signals: Based on signal count (0-10 points)")
        report_lines.append("")
        report_lines.append("#### 2. Company Metrics Query")
        report_lines.append("")
        report_lines.append("**Query Pattern:** JOIN with aggregations")
        report_lines.append("")
        report_lines.append("```sql")
        report_lines.append("SELECT")
        report_lines.append("  COUNT(DISTINCT t.trial_id) as total_trials,")
        report_lines.append("  COUNT(DISTINCT CASE WHEN t.status IN ('ACTIVE', 'RECRUITING') THEN t.trial_id END) as active_trials,")
        report_lines.append("  COUNT(DISTINCT CASE WHEN t.status IN ('TERMINATED', 'WITHDRAWN') THEN t.trial_id END) as terminated_count,")
        report_lines.append("  -- Phase success rates calculated in Python")
        report_lines.append("  MAX(t.registration_date) as last_trial_registration_date,")
        report_lines.append("  MAX(e.event_date) as last_pipeline_update_date")
        report_lines.append("FROM companies c")
        report_lines.append("LEFT JOIN trial_sponsors ts ON c.company_id = ts.entity_id")
        report_lines.append("LEFT JOIN clinical_trials t ON ts.trial_id = t.trial_id")
        report_lines.append("LEFT JOIN events e ON e.entities_involved @> ARRAY[c.company_id]::uuid[]")
        report_lines.append("WHERE c.company_id = :company_id")
        report_lines.append("  AND c.deleted_at IS NULL")
        report_lines.append("GROUP BY c.company_id")
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("#### 3. Timeline Query")
        report_lines.append("")
        report_lines.append("**Query Pattern:** Array containment query")
        report_lines.append("")
        report_lines.append("```sql")
        report_lines.append("-- Primary query")
        report_lines.append("SELECT * FROM events")
        report_lines.append("WHERE array_position(entities_involved, :company_id) IS NOT NULL")
        report_lines.append("  AND deleted_at IS NULL")
        report_lines.append("ORDER BY event_date DESC")
        report_lines.append("")
        report_lines.append("-- If include_related=True, also query related entities")
        report_lines.append("SELECT drug_id FROM company_drugs WHERE company_id = :company_id")
        report_lines.append("SELECT trial_id FROM trial_sponsors WHERE entity_id = :company_id")
        report_lines.append("-- Then query events for those related entities")
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("#### 4. Recent Failures Query")
        report_lines.append("")
        report_lines.append("**Query Pattern:** Event filtering with entity enrichment")
        report_lines.append("")
        report_lines.append("```sql")
        report_lines.append("SELECT * FROM events")
        report_lines.append("WHERE event_type IN ('trial.status.terminated', 'trial.status.withdrawn', ...)")
        report_lines.append("  AND event_date >= :start_date")
        report_lines.append("  AND deleted_at IS NULL")
        report_lines.append("ORDER BY event_date DESC")
        report_lines.append("LIMIT :limit")
        report_lines.append("")
        report_lines.append("-- Then enrich with entity details (companies, trials, drugs, diseases)")
        report_lines.append("-- by querying entities_involved array")
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("#### 5. Company Search Query")
        report_lines.append("")
        report_lines.append("**Query Pattern:** Conditional JOINs with filters")
        report_lines.append("")
        report_lines.append("```sql")
        report_lines.append("SELECT c.* FROM companies c")
        report_lines.append("WHERE c.name ILIKE '%:query%'")
        report_lines.append("  AND c.deleted_at IS NULL")
        report_lines.append("")
        report_lines.append("-- If therapeutic_area filter:")
        report_lines.append("JOIN trial_sponsors ts ON c.company_id = ts.entity_id")
        report_lines.append("JOIN trial_diseases td ON ts.trial_id = td.trial_id")
        report_lines.append("JOIN diseases d ON td.disease_id = d.disease_id")
        report_lines.append("WHERE d.disease_name ILIKE '%:therapeutic_area%'")
        report_lines.append("")
        report_lines.append("-- If min_programs filter:")
        report_lines.append("JOIN (")
        report_lines.append("  SELECT entity_id, COUNT(trial_id) as trial_count")
        report_lines.append("  FROM trial_sponsors")
        report_lines.append("  WHERE entity_type = 'company'")
        report_lines.append("  GROUP BY entity_id")
        report_lines.append(") tc ON c.company_id = tc.entity_id")
        report_lines.append("WHERE tc.trial_count >= :min_programs")
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Query performance considerations
        report_lines.append("## Query Performance Considerations")
        report_lines.append("")
        report_lines.append("### Caching Strategy")
        report_lines.append("")
        report_lines.append("- **Risk Scores:** Cached in Redis with 1-hour TTL")
        report_lines.append("  - Cache key: `risk_score:{company_id}`")
        report_lines.append("- **Company Metrics:** Cached in Redis with 30-minute TTL")
        report_lines.append("  - Cache key: `company_metrics:{company_id}`")
        report_lines.append("- **Timelines:** Cached in Redis with 15-minute TTL")
        report_lines.append("  - Cache key: `company_timeline:{company_id}:{filters}`")
        report_lines.append("")
        report_lines.append("### Database Indexes Used")
        report_lines.append("")
        report_lines.append("- `companies.company_id` - Primary key")
        report_lines.append("- `trial_sponsors.entity_id` - For company-trial joins")
        report_lines.append("- `trial_sponsors.trial_id` - For trial lookups")
        report_lines.append("- `events.entities_involved` - Array column (GIN index recommended)")
        report_lines.append("- `events.event_date` - For date filtering")
        report_lines.append("- `events.event_type` - For event type filtering")
        report_lines.append("")
        report_lines.append("### Potential Performance Issues")
        report_lines.append("")
        report_lines.append("1. **Array Queries:** `array_position(entities_involved, company_id)`")
        report_lines.append("   - May be slow without GIN index on `entities_involved`")
        report_lines.append("   - Consider: `CREATE INDEX idx_events_entities_gin ON events USING GIN(entities_involved);`")
        report_lines.append("")
        report_lines.append("2. **N+1 Queries in Search:**")
        report_lines.append("   - Company search calculates risk score for each company")
        report_lines.append("   - Could be optimized with batch processing or materialized view")
        report_lines.append("")
        report_lines.append("3. **Timeline with Related Entities:**")
        report_lines.append("   - When `include_related=True`, queries multiple entity types")
        report_lines.append("   - May benefit from denormalized event table or materialized view")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # API endpoints summary
        report_lines.append("## API Endpoints Summary")
        report_lines.append("")
        report_lines.append("| Endpoint | Method | Purpose | Database Tables Queried |")
        report_lines.append("|----------|--------|---------|------------------------|")
        report_lines.append("| `/api/companies/{id}/risk-profile` | GET | Get risk score | companies, clinical_trials, trial_sponsors, events |")
        report_lines.append("| `/api/companies/{id}/metrics` | GET | Get company metrics | companies, clinical_trials, trial_sponsors, events |")
        report_lines.append("| `/api/companies/{id}/timeline` | GET | Get event timeline | events, company_drugs, trial_sponsors (optional) |")
        report_lines.append("| `/api/companies/search` | GET | Search companies | companies, trial_sponsors, trial_diseases, diseases |")
        report_lines.append("| `/api/failures/recent` | GET | Get recent failures | events, companies, clinical_trials, drugs, diseases |")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
    
    return "\n".join(report_lines)


def main():
    """Main entry point."""
    print("Generating Source Inventory Report...")
    
    source_report = generate_report()
    
    print("Generating Database Schema Report...")
    schema_report = generate_database_schema_report()
    
    print("Generating Data Pipeline Flow Report...")
    pipeline_report = generate_pipeline_flow_report()
    
    print("Generating Entity Resolution Coverage Report...")
    resolution_report = generate_entity_resolution_coverage_report()
    
    print("Generating Scoring System Report...")
    scoring_report = generate_scoring_system_report()
    
    print("Generating Dashboard/UI Report...")
    dashboard_report = generate_dashboard_ui_report()
    
    # Combine reports
    full_report = source_report + schema_report + pipeline_report + resolution_report + scoring_report + dashboard_report
    
    # Write to file
    output_file = Path(__file__).parent.parent / "SOURCE_INVENTORY_REPORT.md"
    with open(output_file, 'w') as f:
        f.write(full_report)
    
    print(f"Report generated: {output_file}")
    print("\n" + "="*80)
    print("Report sections generated:")
    print("  - Source Inventory Report")
    print("  - Database Schema Report")
    print("  - Data Pipeline Flow Report")
    print("  - Entity Resolution Coverage Report")
    print("  - Scoring System Report")
    print("  - Dashboard/UI Report")
    print("="*80)


if __name__ == "__main__":
    main()

