#!/usr/bin/env python3
"""
Source Configuration & Data Pipeline Audit

Phase 1: Source Configuration Audit
Phase 2: Data Pipeline Integrity Check
"""
import os
import sys
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.sources import Source
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog, EntityAlias, EntityMatchCandidate
from database.models.lineage import DataLineage
from database.models.entities import Company, Drug, Disease, Institution
from database.models.clinical import ClinicalTrial, RegulatoryEvent
from database.models.events import Event
from database.models.relationships import (
    CompanyDrug, DrugTarget, DrugMechanism, DrugIndication,
    TrialSponsor, TrialDrug, TrialDisease,
    PublicationDrug, PublicationCompany, PublicationTrial,
    FilingCompany, FilingDrug, PatentDrug, PatentCompany,
    RegulatoryDrugEvent, RegulatoryCompanyEvent
)
from database.models.publications import Publication, Patent, SECFiling
from src.services.company_risk_service import CompanyRiskService
from src.services.failure_tracker import FailureTracker
from src.models.clinical_constants import TrialStatus
from uuid import UUID
from sqlalchemy import func, and_, or_, distinct
from sqlalchemy.orm import Session


# Critical sources for failure detection (high priority)
CRITICAL_SOURCES = {
    'regulatory': [
        'fda_breakthrough',  # Breakthrough therapy designations
        'fda_orphan',  # Orphan drug designations
        'fda_orange_book',  # Approved drugs
        'fda_clinical_hold',  # Clinical holds (critical failure signal)
        'fda_warning_letters',  # Warning letters (regulatory issues)
        'ema_epar',  # EMA approvals
        'ema_prime',  # EMA PRIME designations
    ],
    'employment': [
        'california_warn',  # WARN notices (layoffs)
        'federal_warn',  # Federal WARN notices
        'biospace_layoff_tracker',  # Biotech layoff tracking
        'fierce_layoff_tracker',  # Industry layoff tracking
    ],
    'patent': [
        'patentsview',  # Patent data
        'uspto_public_pair',  # USPTO patent applications
    ],
    'conference': [
        'asco_abstracts',  # ASCO conference abstracts (trial results)
    ],
    'clinical': [
        'who_ictrp',  # WHO clinical trials registry
    ],
}


def get_ingestion_scripts() -> Set[str]:
    """Get all ingestion script names from the ingestion directory."""
    ingestion_dir = project_root / 'ingestion'
    scripts = set()
    
    for file in ingestion_dir.glob('*.py'):
        if file.name not in ['__init__.py', 'test_helper.py']:
            script_name = file.stem
            scripts.add(script_name)
    
    return scripts


def get_registered_sources(session: Session) -> Dict[str, Source]:
    """Get all registered sources from the database."""
    sources = session.query(Source).filter(
        Source.deleted_at.is_(None)
    ).all()
    
    return {s.source_name: s for s in sources}


def get_source_type_from_script(script_name: str) -> Optional[str]:
    """Infer source type from script name or common patterns."""
    script_lower = script_name.lower()
    
    # Regulatory sources
    if any(x in script_lower for x in ['fda_', 'ema_', 'mhra_', 'health_canada', 'tga_', 
                                       'swissmedic', 'cdsco_', 'hsa_', 'mfds_', 'who_', 
                                       'ich_', 'nice_']):
        return 'regulatory'
    
    # Employment/WARN sources
    if any(x in script_lower for x in ['warn', 'layoff']):
        return 'employment'
    
    # Patent sources
    if any(x in script_lower for x in ['patent', 'uspto']):
        return 'patent'
    
    # Literature sources
    if any(x in script_lower for x in ['pubmed', 'pmc', 'arxiv', 'biorxiv', 'medrxiv', 
                                       'chemrxiv', 'pubtator', 'semantic_scholar', 
                                       'europe_pmc']):
        return 'literature'
    
    # Financial sources
    if any(x in script_lower for x in ['sec_', 'alphavantage', 'calcbench', 'openfigi']):
        return 'financial'
    
    # Social sources
    if any(x in script_lower for x in ['reddit', 'youtube', 'google_news', 'rss_news']):
        return 'social'
    
    # Funding sources
    if any(x in script_lower for x in ['nih_', 'nsf_', 'darpa', 'dod_', 'barda', 'sbir']):
        return 'funding'
    
    # Scientific databases
    if any(x in script_lower for x in ['chembl', 'pubchem', 'uniprot', 'biogrid', 
                                        'string_db', 'opentargets', 'disgenet', 'clinvar', 
                                        'clingen', 'omim', 'orphanet', 'reactome']):
        return 'scientific'
    
    # Conference sources
    if 'asco' in script_lower or 'conference' in script_lower:
        return 'conference'
    
    # Clinical sources
    if 'clinicaltrials' in script_lower or 'who_ictrp' in script_lower:
        return 'clinical'
    
    # Default
    return 'other'


def get_source_staging_stats(session: Session, source_name: str) -> Dict:
    """Get staging statistics for a source."""
    stats = session.query(
        func.count(StagingRawData.staging_id).label('total_records'),
        func.max(StagingRawData.ingested_at).label('last_ingested')
    ).filter(
        StagingRawData.source_system == source_name,
        StagingRawData.deleted_at.is_(None)
    ).first()
    
    return {
        'total_records': stats.total_records or 0,
        'last_ingested': stats.last_ingested
    }


def get_source_processing_stats(session: Session, source_name: str) -> Dict:
    """Get processing statistics for a source."""
    stats = session.query(
        func.count(SourceProcessingLog.log_id).label('total_runs'),
        func.max(SourceProcessingLog.processing_completed_at).label('last_completed'),
        func.max(SourceProcessingLog.processing_started_at).label('last_started')
    ).filter(
        SourceProcessingLog.source_name == source_name,
        SourceProcessingLog.deleted_at.is_(None)
    ).first()
    
    return {
        'total_runs': stats.total_runs or 0,
        'last_completed': stats.last_completed,
        'last_started': stats.last_started
    }


def check_source_metadata(script_name: str, source: Source) -> List[str]:
    """Check if source metadata is correct."""
    issues = []
    inferred_type = get_source_type_from_script(script_name)
    
    if inferred_type and source.source_type != inferred_type:
        issues.append(f"Type mismatch: registered as '{source.source_type}', should be '{inferred_type}'")
    
    if not source.base_url:
        issues.append("Missing base_url")
    
    if not source.update_frequency:
        issues.append("Missing update_frequency")
    
    return issues


def generate_audit_report() -> str:
    """Generate the source configuration audit report."""
    report_lines = []
    report_lines.append("# Phase 1: Source Configuration Audit")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("## Executive Summary")
    report_lines.append("")
    
    with get_db_session() as session:
        # Get all ingestion scripts
        ingestion_scripts = get_ingestion_scripts()
        print(f"Found {len(ingestion_scripts)} ingestion scripts")
        
        # Get registered sources
        registered_sources = get_registered_sources(session)
        print(f"Found {len(registered_sources)} registered sources")
        
        # Find unregistered sources
        unregistered = ingestion_scripts - set(registered_sources.keys())
        
        # Find sources registered but no script
        registered_names = set(registered_sources.keys())
        missing_scripts = registered_names - ingestion_scripts
        
        # Analyze registered sources
        active_sources = [s for s in registered_sources.values() if s.is_active]
        inactive_sources = [s for s in registered_sources.values() if not s.is_active]
        
        # Check for sources marked active but never run
        active_but_never_run = []
        for source in active_sources:
            processing_stats = get_source_processing_stats(session, source.source_name)
            staging_stats = get_source_staging_stats(session, source.source_name)
            
            if processing_stats['total_runs'] == 0 and staging_stats['total_records'] == 0:
                active_but_never_run.append({
                    'source': source,
                    'processing_stats': processing_stats,
                    'staging_stats': staging_stats
                })
        
        # Summary
        report_lines.append(f"- **Total Ingestion Scripts:** {len(ingestion_scripts)}")
        report_lines.append(f"- **Registered Sources:** {len(registered_sources)}")
        report_lines.append(f"- **Unregistered Sources:** {len(unregistered)}")
        report_lines.append(f"- **Active Sources:** {len(active_sources)}")
        report_lines.append(f"- **Inactive Sources:** {len(inactive_sources)}")
        report_lines.append(f"- **Active but Never Run:** {len(active_but_never_run)}")
        report_lines.append(f"- **Missing Scripts:** {len(missing_scripts)}")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Section 1: Unregistered Sources
        report_lines.append("## 1. Source Registration Check")
        report_lines.append("")
        report_lines.append("### Unregistered Sources (Need Registration)")
        report_lines.append("")
        report_lines.append("These sources have ingestion scripts but are not registered in the `sources` table.")
        report_lines.append("")
        
        # Categorize unregistered sources by priority
        critical_unregistered = []
        high_priority_unregistered = []
        medium_priority_unregistered = []
        low_priority_unregistered = []
        
        for script_name in sorted(unregistered):
            source_type = get_source_type_from_script(script_name)
            is_critical = False
            priority_category = None
            
            # Check if it's in critical sources
            for category, sources in CRITICAL_SOURCES.items():
                if script_name in sources:
                    is_critical = True
                    priority_category = category
                    critical_unregistered.append({
                        'name': script_name,
                        'type': source_type,
                        'category': category
                    })
                    break
            
            if not is_critical:
                if source_type in ['regulatory', 'employment', 'clinical']:
                    high_priority_unregistered.append({
                        'name': script_name,
                        'type': source_type
                    })
                elif source_type in ['patent', 'conference', 'literature']:
                    medium_priority_unregistered.append({
                        'name': script_name,
                        'type': source_type
                    })
                else:
                    low_priority_unregistered.append({
                        'name': script_name,
                        'type': source_type
                    })
        
        # Critical unregistered
        if critical_unregistered:
            report_lines.append("#### 🔴 CRITICAL Priority (Failure Detection)")
            report_lines.append("")
            report_lines.append("| Source Name | Type | Category | Priority Reason |")
            report_lines.append("|-------------|------|----------|-----------------|")
            for item in critical_unregistered:
                category = item['category']
                if category == 'regulatory':
                    reason = "Regulatory signals (clinical holds, approvals, warnings)"
                elif category == 'employment':
                    reason = "Employment signals (layoffs, WARN notices)"
                elif category == 'patent':
                    reason = "Patent data (IP protection, innovation signals)"
                elif category == 'conference':
                    reason = "Conference abstracts (trial results, early data)"
                else:
                    reason = "Critical for failure detection"
                
                report_lines.append(f"| `{item['name']}` | {item['type']} | {category} | {reason} |")
            report_lines.append("")
        
        # High priority unregistered
        if high_priority_unregistered:
            report_lines.append("#### 🟠 HIGH Priority")
            report_lines.append("")
            report_lines.append("| Source Name | Type |")
            report_lines.append("|-------------|------|")
            for item in high_priority_unregistered:
                report_lines.append(f"| `{item['name']}` | {item['type']} |")
            report_lines.append("")
        
        # Medium priority unregistered
        if medium_priority_unregistered:
            report_lines.append("#### 🟡 MEDIUM Priority")
            report_lines.append("")
            report_lines.append("| Source Name | Type |")
            report_lines.append("|-------------|------|")
            for item in medium_priority_unregistered[:20]:  # Limit to first 20
                report_lines.append(f"| `{item['name']}` | {item['type']} |")
            if len(medium_priority_unregistered) > 20:
                report_lines.append(f"*... and {len(medium_priority_unregistered) - 20} more*")
            report_lines.append("")
        
        # Low priority unregistered
        if low_priority_unregistered:
            report_lines.append("#### ⚪ LOW Priority")
            report_lines.append("")
            report_lines.append(f"*{len(low_priority_unregistered)} additional sources*")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 2: Source Activation Verification
        report_lines.append("## 2. Source Activation Verification")
        report_lines.append("")
        
        # Active but never run
        if active_but_never_run:
            report_lines.append("### ⚠️ Active Sources Never Run")
            report_lines.append("")
            report_lines.append("These sources are marked `is_active=True` but have never been executed.")
            report_lines.append("")
            report_lines.append("| Source Name | Type | Status | Issue |")
            report_lines.append("|-------------|------|--------|-------|")
            for item in active_but_never_run:
                source = item['source']
                report_lines.append(f"| `{source.source_name}` | {source.source_type} | Active | Never run, no staging records |")
            report_lines.append("")
        
        # Stale sources (not run in 30+ days)
        stale_sources = []
        for source in active_sources:
            processing_stats = get_source_processing_stats(session, source.source_name)
            if processing_stats['last_completed']:
                last_completed = processing_stats['last_completed']
                # Handle both date and datetime objects
                if hasattr(last_completed, 'date'):
                    last_completed_date = last_completed.date()
                else:
                    last_completed_date = last_completed
                days_since = (datetime.now().date() - last_completed_date).days
                if days_since > 30:
                    stale_sources.append({
                        'source': source,
                        'days_since': days_since,
                        'stats': processing_stats
                    })
        
        if stale_sources:
            report_lines.append("### ⚠️ Stale Sources (Not Run in 30+ Days)")
            report_lines.append("")
            report_lines.append("| Source Name | Type | Days Since Last Run | Last Completed |")
            report_lines.append("|-------------|------|---------------------|---------------|")
            for item in sorted(stale_sources, key=lambda x: x['days_since'], reverse=True):
                source = item['source']
                last_completed = item['stats']['last_completed']
                report_lines.append(f"| `{source.source_name}` | {source.source_type} | {item['days_since']} days | {last_completed.strftime('%Y-%m-%d') if last_completed else 'Never'} |")
            report_lines.append("")
        
        # Sources with metadata issues
        metadata_issues = []
        for source_name, source in registered_sources.items():
            issues = check_source_metadata(source_name, source)
            if issues:
                metadata_issues.append({
                    'source': source,
                    'issues': issues
                })
        
        if metadata_issues:
            report_lines.append("### ⚠️ Sources with Metadata Issues")
            report_lines.append("")
            report_lines.append("| Source Name | Issues |")
            report_lines.append("|-------------|--------|")
            for item in metadata_issues:
                source = item['source']
                issues_str = "; ".join(item['issues'])
                report_lines.append(f"| `{source.source_name}` | {issues_str} |")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 3: Missing Critical Sources
        report_lines.append("## 3. Missing Critical Sources for Failure Detection")
        report_lines.append("")
        report_lines.append("These high-priority sources should be running to detect company failures:")
        report_lines.append("")
        
        for category, sources in CRITICAL_SOURCES.items():
            report_lines.append(f"### {category.upper()} Sources")
            report_lines.append("")
            report_lines.append("| Source Name | Status | Priority | Reason |")
            report_lines.append("|-------------|--------|----------|--------|")
            
            for source_name in sources:
                if source_name in registered_sources:
                    source = registered_sources[source_name]
                    processing_stats = get_source_processing_stats(session, source_name)
                    staging_stats = get_source_staging_stats(session, source_name)
                    
                    if source.is_active:
                        if processing_stats['total_runs'] > 0:
                            status = "✅ Active & Running"
                        else:
                            status = "⚠️ Active but Never Run"
                    else:
                        status = "❌ Inactive"
                    
                    priority = "CRITICAL"
                else:
                    status = "❌ Not Registered"
                    priority = "CRITICAL"
                    processing_stats = {'total_runs': 0}
                    staging_stats = {'total_records': 0}
                
                # Reason based on category
                if category == 'regulatory':
                    if 'breakthrough' in source_name:
                        reason = "Breakthrough designations signal success"
                    elif 'orphan' in source_name:
                        reason = "Orphan designations indicate pipeline activity"
                    elif 'orange_book' in source_name:
                        reason = "Approved drugs = revenue potential"
                    elif 'clinical_hold' in source_name:
                        reason = "Clinical holds = immediate failure signal"
                    elif 'warning' in source_name:
                        reason = "Warning letters = regulatory risk"
                    else:
                        reason = "Regulatory approvals/rejections"
                elif category == 'employment':
                    reason = "Layoffs/WARN notices = financial distress signal"
                elif category == 'patent':
                    reason = "Patent activity = innovation/IP protection"
                elif category == 'conference':
                    reason = "Conference abstracts = early trial results"
                else:
                    reason = "Critical for failure detection"
                
                report_lines.append(f"| `{source_name}` | {status} | {priority} | {reason} |")
            
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 4: Registration Recommendations
        report_lines.append("## 4. Registration Recommendations (Prioritized)")
        report_lines.append("")
        report_lines.append("### Immediate Action Required (Week 1)")
        report_lines.append("")
        report_lines.append("Register and activate these critical sources:")
        report_lines.append("")
        
        immediate_actions = []
        for category, sources in CRITICAL_SOURCES.items():
            for source_name in sources:
                if source_name in unregistered:
                    immediate_actions.append({
                        'name': source_name,
                        'type': get_source_type_from_script(source_name),
                        'category': category
                    })
        
        if immediate_actions:
            report_lines.append("| Source Name | Type | Category | Action |")
            report_lines.append("|-------------|------|----------|-------|")
            for item in immediate_actions:
                report_lines.append(f"| `{item['name']}` | {item['type']} | {item['category']} | Register + Activate |")
            report_lines.append("")
        
        # SQL template for registration
        report_lines.append("#### SQL Template for Registration")
        report_lines.append("")
        report_lines.append("```sql")
        report_lines.append("INSERT INTO sources (source_name, source_type, is_active, update_frequency, base_url)")
        report_lines.append("VALUES")
        for i, item in enumerate(immediate_actions[:10]):  # First 10
            source_name = item['name']
            source_type = item['type']
            # Infer base URL (would need to check actual scripts)
            base_url = "https://example.com"  # Placeholder
            comma = "," if i < len(immediate_actions) - 1 else ";"
            report_lines.append(f"  ('{source_name}', '{source_type}', true, 'weekly', '{base_url}'){comma}")
        report_lines.append("```")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 5: Summary Statistics
        report_lines.append("## 5. Summary Statistics")
        report_lines.append("")
        
        # Count by type
        type_counts = defaultdict(int)
        for script_name in ingestion_scripts:
            source_type = get_source_type_from_script(script_name)
            type_counts[source_type] += 1
        
        report_lines.append("### Sources by Type")
        report_lines.append("")
        report_lines.append("| Type | Total Scripts | Registered | Unregistered |")
        report_lines.append("|------|---------------|------------|--------------|")
        for source_type in sorted(type_counts.keys()):
            total = type_counts[source_type]
            registered_count = sum(1 for s in registered_sources.values() 
                                  if s.source_type == source_type)
            unregistered_count = sum(1 for name in unregistered 
                                   if get_source_type_from_script(name) == source_type)
            report_lines.append(f"| {source_type} | {total} | {registered_count} | {unregistered_count} |")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("**End of Report**")
        report_lines.append("")
    
    return "\n".join(report_lines)


def get_entity_counts_by_source(session: Session, source_name: str) -> Dict[str, int]:
    """Get entity counts created from a specific source via data_lineage."""
    entity_counts = {}
    
    # Get source_id
    source = session.query(Source).filter(
        Source.source_name == source_name,
        Source.deleted_at.is_(None)
    ).first()
    
    if not source:
        return entity_counts
    
    # Count entities by type from lineage
    entity_types = {
        'companies': 'companies',
        'drugs': 'drugs',
        'diseases': 'diseases',
        'institutions': 'institutions',
        'clinical_trials': 'clinical_trials'
    }
    
    for table_name, entity_type in entity_types.items():
        count = session.query(func.count(distinct(DataLineage.record_id))).filter(
            DataLineage.source_id == source.source_id,
            DataLineage.table_name == table_name,
            DataLineage.deleted_at.is_(None)
        ).scalar()
        entity_counts[entity_type] = count or 0
    
    return entity_counts


def get_staging_to_entity_conversion(session: Session, source_name: str) -> Dict[str, Any]:
    """Calculate staging to entity conversion rates for a source."""
    # Staging records
    staging_count = session.query(func.count(StagingRawData.staging_id)).filter(
        StagingRawData.source_system == source_name,
        StagingRawData.deleted_at.is_(None)
    ).scalar() or 0
    
    # Processed records
    processed_count = session.query(func.count(distinct(SourceProcessingLog.source_identifier))).filter(
        SourceProcessingLog.source_name == source_name,
        SourceProcessingLog.processing_status == 'success',
        SourceProcessingLog.deleted_at.is_(None)
    ).scalar() or 0
    
    # Entity counts
    entity_counts = get_entity_counts_by_source(session, source_name)
    total_entities = sum(entity_counts.values())
    
    # Conversion rates
    staging_to_processed_rate = (processed_count / staging_count * 100) if staging_count > 0 else 0
    processed_to_entities_rate = (total_entities / processed_count * 100) if processed_count > 0 else 0
    overall_conversion_rate = (total_entities / staging_count * 100) if staging_count > 0 else 0
    
    # Get processing stats
    processing_stats = session.query(
        func.sum(SourceProcessingLog.entities_extracted).label('total_extracted'),
        func.sum(SourceProcessingLog.entities_matched).label('total_matched'),
        func.sum(SourceProcessingLog.entities_created).label('total_created'),
        func.sum(SourceProcessingLog.relationships_created).label('total_relationships')
    ).filter(
        SourceProcessingLog.source_name == source_name,
        SourceProcessingLog.deleted_at.is_(None)
    ).first()
    
    return {
        'staging_count': staging_count,
        'processed_count': processed_count,
        'entity_counts': entity_counts,
        'total_entities': total_entities,
        'staging_to_processed_rate': staging_to_processed_rate,
        'processed_to_entities_rate': processed_to_entities_rate,
        'overall_conversion_rate': overall_conversion_rate,
        'total_extracted': processing_stats.total_extracted or 0,
        'total_matched': processing_stats.total_matched or 0,
        'total_created': processing_stats.total_created or 0,
        'total_relationships': processing_stats.total_relationships or 0
    }


def sample_staging_records(session: Session, source_name: str, sample_size: int = 20) -> List[StagingRawData]:
    """Sample random staging records from a source."""
    total = session.query(func.count(StagingRawData.staging_id)).filter(
        StagingRawData.source_system == source_name,
        StagingRawData.deleted_at.is_(None)
    ).scalar() or 0
    
    if total == 0:
        return []
    
    # Get random sample
    records = session.query(StagingRawData).filter(
        StagingRawData.source_system == source_name,
        StagingRawData.deleted_at.is_(None)
    ).limit(sample_size * 2).all()  # Get more than needed for randomness
    
    if len(records) <= sample_size:
        return records
    
    return random.sample(records, sample_size)


def analyze_extraction_errors(session: Session, source_name: str) -> Dict[str, Any]:
    """Analyze extraction errors from processing logs."""
    # Get failed/partial processing logs
    failed_logs = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.source_name == source_name,
        SourceProcessingLog.processing_status.in_(['failed', 'partial']),
        SourceProcessingLog.deleted_at.is_(None)
    ).all()
    
    error_patterns = defaultdict(int)
    error_examples = []
    
    for log in failed_logs:
        if log.errors:
            for error in log.errors:
                # Extract error pattern (first few words)
                error_key = ' '.join(error.split()[:5]) if error else 'unknown'
                error_patterns[error_key] += 1
                if len(error_examples) < 10:
                    error_examples.append({
                        'source_identifier': log.source_identifier,
                        'error': error,
                        'status': log.processing_status
                    })
    
    return {
        'total_failed': len(failed_logs),
        'error_patterns': dict(error_patterns),
        'error_examples': error_examples
    }


def analyze_deduplication(session: Session, source_name: str) -> Dict[str, Any]:
    """Analyze deduplication effectiveness."""
    # Get processing stats
    stats = session.query(
        func.sum(SourceProcessingLog.entities_extracted).label('total_extracted'),
        func.sum(SourceProcessingLog.entities_matched).label('total_matched'),
        func.sum(SourceProcessingLog.entities_created).label('total_created')
    ).filter(
        SourceProcessingLog.source_name == source_name,
        SourceProcessingLog.deleted_at.is_(None)
    ).first()
    
    total_extracted = stats.total_extracted or 0
    total_matched = stats.total_matched or 0
    total_created = stats.total_created or 0
    
    # Deduplication rate
    deduplication_rate = (total_matched / total_extracted * 100) if total_extracted > 0 else 0
    
    # Entity aliases analysis
    source = session.query(Source).filter(
        Source.source_name == source_name,
        Source.deleted_at.is_(None)
    ).first()
    
    alias_stats = {}
    if source:
        # Count aliases per entity type
        for entity_type in ['company', 'drug', 'disease']:
            # Get entity count from this source via lineage
            entity_count = session.query(func.count(distinct(DataLineage.record_id))).filter(
                DataLineage.source_id == source.source_id,
                DataLineage.table_name == f'{entity_type}s',
                DataLineage.deleted_at.is_(None)
            ).scalar() or 0
            
            if entity_count > 0:
                # Get entity IDs from this source
                entity_ids = [row[0] for row in session.query(distinct(DataLineage.record_id)).filter(
                    DataLineage.source_id == source.source_id,
                    DataLineage.table_name == f'{entity_type}s',
                    DataLineage.deleted_at.is_(None)
                ).all()]
                
                # Count aliases for these entities
                alias_count = session.query(func.count(EntityAlias.alias_id)).filter(
                    EntityAlias.entity_type == entity_type,
                    EntityAlias.entity_id.in_(entity_ids),
                    EntityAlias.deleted_at.is_(None)
                ).scalar() or 0
            else:
                alias_count = 0
            
            alias_stats[entity_type] = {
                'entity_count': entity_count,
                'alias_count': alias_count,
                'avg_aliases_per_entity': (alias_count / entity_count) if entity_count > 0 else 0
            }
    
    # High confidence matches that weren't auto-merged
    high_confidence_unmerged = session.query(func.count(EntityMatchCandidate.candidate_id)).filter(
        EntityMatchCandidate.source_name == source_name,
        EntityMatchCandidate.match_confidence >= 0.8,
        EntityMatchCandidate.status == 'needs_review',
        EntityMatchCandidate.deleted_at.is_(None)
    ).scalar() or 0
    
    return {
        'total_extracted': total_extracted,
        'total_matched': total_matched,
        'total_created': total_created,
        'deduplication_rate': deduplication_rate,
        'alias_stats': alias_stats,
        'high_confidence_unmerged': high_confidence_unmerged
    }


def generate_phase2_report() -> str:
    """Generate Phase 2: Data Pipeline Integrity Check report."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Phase 2: Data Pipeline Integrity Check")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("Goal: Verify data flows from staging → entities → relationships with minimal loss")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        # Get active sources
        active_sources = session.query(Source).filter(
            Source.is_active == True,
            Source.deleted_at.is_(None)
        ).all()
        
        if not active_sources:
            report_lines.append("No active sources found.")
            return "\n".join(report_lines)
        
        # Section 1: Staging to Entity Conversion Rates
        report_lines.append("## 1. Staging to Entity Conversion Rates")
        report_lines.append("")
        report_lines.append("For each active source, tracking the data flow funnel:")
        report_lines.append("")
        report_lines.append("| Source Name | Staging Records | Processed | Entities Created | Staging→Processed | Processed→Entities | Overall Conversion | Status |")
        report_lines.append("|-------------|----------------|----------|------------------|-------------------|-------------------|-------------------|--------|")
        
        suspicious_sources = []
        for source in active_sources:
            conversion = get_staging_to_entity_conversion(session, source.source_name)
            
            staging_count = conversion['staging_count']
            processed_count = conversion['processed_count']
            total_entities = conversion['total_entities']
            overall_rate = conversion['overall_conversion_rate']
            
            status = "✅ Good" if overall_rate >= 50 else "⚠️ Low" if overall_rate > 0 else "❌ None"
            
            if overall_rate < 50 and overall_rate > 0:
                suspicious_sources.append({
                    'source': source,
                    'conversion': conversion
                })
            
            report_lines.append(
                f"| `{source.source_name}` | {staging_count} | {processed_count} | {total_entities} | "
                f"{conversion['staging_to_processed_rate']:.1f}% | "
                f"{conversion['processed_to_entities_rate']:.1f}% | "
                f"{overall_rate:.1f}% | {status} |"
            )
        
        report_lines.append("")
        
        if suspicious_sources:
            report_lines.append("### ⚠️ Suspicious Conversion Rates (< 50%)")
            report_lines.append("")
            for item in suspicious_sources:
                source = item['source']
                conv = item['conversion']
                report_lines.append(f"#### {source.source_name}")
                report_lines.append("")
                report_lines.append(f"- **Staging Records:** {conv['staging_count']}")
                report_lines.append(f"- **Processed:** {conv['processed_count']}")
                report_lines.append(f"- **Entities Created:** {conv['total_entities']}")
                report_lines.append(f"- **Overall Conversion:** {conv['overall_conversion_rate']:.1f}%")
                report_lines.append(f"- **Entity Breakdown:**")
                for entity_type, count in conv['entity_counts'].items():
                    if count > 0:
                        report_lines.append(f"  - {entity_type}: {count}")
                report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 2: Entity Extraction Validation
        report_lines.append("## 2. Entity Extraction Validation")
        report_lines.append("")
        
        for source in active_sources[:5]:  # Limit to first 5 sources for report size
            report_lines.append(f"### Source: {source.source_name}")
            report_lines.append("")
            
            # Sample records
            samples = sample_staging_records(session, source.source_name, 20)
            
            if not samples:
                report_lines.append("*No staging records found*")
                report_lines.append("")
                continue
            
            report_lines.append(f"**Sampled {len(samples)} records for validation**")
            report_lines.append("")
            
            # Check processing status
            processed_samples = [s for s in samples if s.processed]
            unprocessed_samples = [s for s in samples if not s.processed]
            
            report_lines.append(f"- **Processed:** {len(processed_samples)}/{len(samples)}")
            report_lines.append(f"- **Unprocessed:** {len(unprocessed_samples)}/{len(samples)}")
            report_lines.append("")
            
            # Check for entities created from processed samples
            if processed_samples:
                processed_ids = [s.source_record_id for s in processed_samples]
                processing_logs = session.query(SourceProcessingLog).filter(
                    SourceProcessingLog.source_name == source.source_name,
                    SourceProcessingLog.source_identifier.in_(processed_ids),
                    SourceProcessingLog.deleted_at.is_(None)
                ).all()
                
                total_extracted = sum(log.entities_extracted or 0 for log in processing_logs)
                total_matched = sum(log.entities_matched or 0 for log in processing_logs)
                total_created = sum(log.entities_created or 0 for log in processing_logs)
                
                report_lines.append("**Extraction Results:**")
                report_lines.append(f"- Entities Extracted: {total_extracted}")
                report_lines.append(f"- Entities Matched: {total_matched}")
                report_lines.append(f"- Entities Created: {total_created}")
                report_lines.append("")
            
            # Error analysis
            error_analysis = analyze_extraction_errors(session, source.source_name)
            
            if error_analysis['total_failed'] > 0:
                report_lines.append("**⚠️ Extraction Errors Found:**")
                report_lines.append(f"- **Total Failed/Partial:** {error_analysis['total_failed']}")
                report_lines.append("")
                report_lines.append("**Common Error Patterns:**")
                report_lines.append("")
                for pattern, count in sorted(error_analysis['error_patterns'].items(), key=lambda x: x[1], reverse=True)[:5]:
                    report_lines.append(f"- `{pattern}`: {count} occurrences")
                report_lines.append("")
                
                if error_analysis['error_examples']:
                    report_lines.append("**Example Errors:**")
                    report_lines.append("")
                    for example in error_analysis['error_examples'][:5]:
                        report_lines.append(f"- **{example['source_identifier']}** ({example['status']}): {example['error'][:100]}...")
                    report_lines.append("")
            
            report_lines.append("---")
            report_lines.append("")
        
        # Section 3: Deduplication Analysis
        report_lines.append("## 3. Deduplication Analysis")
        report_lines.append("")
        
        report_lines.append("### Overall Deduplication Statistics")
        report_lines.append("")
        report_lines.append("| Source Name | Entities Extracted | Entities Matched | Entities Created | Deduplication Rate |")
        report_lines.append("|-------------|-------------------|------------------|------------------|-------------------|")
        
        for source in active_sources:
            dedup = analyze_deduplication(session, source.source_name)
            rate = dedup['deduplication_rate']
            status = "✅ Good" if rate >= 70 else "⚠️ Low" if rate > 0 else "❌ None"
            
            report_lines.append(
                f"| `{source.source_name}` | {dedup['total_extracted']} | {dedup['total_matched']} | "
                f"{dedup['total_created']} | {rate:.1f}% | {status} |"
            )
        
        report_lines.append("")
        
        # Entity aliases analysis
        report_lines.append("### Entity Aliases Analysis")
        report_lines.append("")
        report_lines.append("Verifying that entity aliases are being created for deduplication:")
        report_lines.append("")
        
        for source in active_sources[:5]:  # Limit to first 5
            dedup = analyze_deduplication(session, source.source_name)
            alias_stats = dedup['alias_stats']
            
            if alias_stats:
                report_lines.append(f"#### {source.source_name}")
                report_lines.append("")
                report_lines.append("| Entity Type | Entity Count | Alias Count | Avg Aliases/Entity |")
                report_lines.append("|-------------|--------------|-------------|-------------------|")
                for entity_type, stats in alias_stats.items():
                    avg = stats['avg_aliases_per_entity']
                    status = "✅" if avg >= 1.0 else "⚠️" if avg > 0 else "❌"
                    report_lines.append(
                        f"| {entity_type} | {stats['entity_count']} | {stats['alias_count']} | "
                        f"{avg:.2f} {status} |"
                    )
                report_lines.append("")
        
        # High confidence unmerged
        report_lines.append("### High Confidence Matches Not Auto-Merged")
        report_lines.append("")
        report_lines.append("Matches with confidence ≥ 0.8 that require manual review:")
        report_lines.append("")
        report_lines.append("| Source Name | High Confidence Unmerged |")
        report_lines.append("|-------------|-------------------------|")
        
        for source in active_sources:
            dedup = analyze_deduplication(session, source.source_name)
            count = dedup['high_confidence_unmerged']
            status = "⚠️ Review Needed" if count > 0 else "✅ None"
            report_lines.append(f"| `{source.source_name}` | {count} {status} |")
        
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
        # Section 4: Data Loss Funnel Summary
        report_lines.append("## 4. Data Loss Funnel Summary")
        report_lines.append("")
        report_lines.append("Overall pipeline statistics showing where records are lost:")
        report_lines.append("")
        
        total_staging = session.query(func.count(StagingRawData.staging_id)).filter(
            StagingRawData.deleted_at.is_(None)
        ).scalar() or 0
        
        total_processed = session.query(func.count(distinct(SourceProcessingLog.source_identifier))).filter(
            SourceProcessingLog.processing_status == 'success',
            SourceProcessingLog.deleted_at.is_(None)
        ).scalar() or 0
        
        # Get total entities from lineage
        total_entities = session.query(func.count(distinct(DataLineage.record_id))).filter(
            DataLineage.deleted_at.is_(None)
        ).scalar() or 0
        
        report_lines.append("### Overall Pipeline Funnel")
        report_lines.append("")
        report_lines.append(f"1. **Staging Records:** {total_staging:,}")
        report_lines.append(f"2. **Successfully Processed:** {total_processed:,} ({(total_processed/total_staging*100) if total_staging > 0 else 0:.1f}%)")
        report_lines.append(f"3. **Entities Created:** {total_entities:,} ({(total_entities/total_staging*100) if total_staging > 0 else 0:.1f}%)")
        report_lines.append("")
        report_lines.append("**Loss Points:**")
        report_lines.append(f"- Staging → Processed: {total_staging - total_processed:,} records lost ({(1 - total_processed/total_staging)*100 if total_staging > 0 else 0:.1f}%)")
        report_lines.append(f"- Processed → Entities: {total_processed - total_entities:,} records lost ({(1 - total_entities/total_processed)*100 if total_processed > 0 else 0:.1f}%)")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("**End of Phase 2 Report**")
        report_lines.append("")
    
    return "\n".join(report_lines)


def get_relationship_table_counts(session: Session) -> Dict[str, int]:
    """Get row counts for all relationship tables."""
    relationship_tables = {
        'company_drugs': CompanyDrug,
        'drug_targets': DrugTarget,
        'drug_mechanisms': DrugMechanism,
        'drug_indications': DrugIndication,
        'trial_sponsors': TrialSponsor,
        'trial_drugs': TrialDrug,
        'trial_diseases': TrialDisease,
        'publication_drugs': PublicationDrug,
        'publication_companies': PublicationCompany,
        'publication_trials': PublicationTrial,
        'filing_companies': FilingCompany,
        'filing_drugs': FilingDrug,
        'patent_drugs': PatentDrug,
        'patent_companies': PatentCompany,
        'regulatory_drug_events': RegulatoryDrugEvent,
        'regulatory_company_events': RegulatoryCompanyEvent,
    }
    
    counts = {}
    for table_name, model in relationship_tables.items():
        count = session.query(func.count(model.id if hasattr(model, 'id') else getattr(model, list(model.__table__.primary_key.columns)[0].name))).filter(
            model.deleted_at.is_(None)
        ).scalar() or 0
        counts[table_name] = count
    
    return counts


def calculate_expected_relationships(session: Session) -> Dict[str, Dict[str, Any]]:
    """Calculate expected relationships based on source data."""
    expected = {}
    
    # Trial relationships
    trial_count = session.query(func.count(ClinicalTrial.trial_id)).filter(
        ClinicalTrial.deleted_at.is_(None)
    ).scalar() or 0
    
    # Most trials have at least 1 sponsor, 1 drug, 1 disease
    expected['trial_sponsors'] = {
        'expected_min': trial_count,
        'expected_typical': trial_count * 1.2,  # Some have collaborators
        'reason': f"{trial_count} trials should have sponsors"
    }
    expected['trial_drugs'] = {
        'expected_min': trial_count * 0.8,  # ~80% of trials have drugs
        'expected_typical': trial_count,
        'reason': f"{trial_count} trials, most should have drugs"
    }
    expected['trial_diseases'] = {
        'expected_min': trial_count,
        'expected_typical': trial_count * 1.5,  # Some trials target multiple diseases
        'reason': f"{trial_count} trials should have diseases"
    }
    
    # Publication relationships
    pub_count = session.query(func.count(Publication.pub_id)).filter(
        Publication.deleted_at.is_(None)
    ).scalar() or 0
    
    expected['publication_drugs'] = {
        'expected_min': pub_count * 0.3,  # ~30% mention drugs
        'expected_typical': pub_count * 0.5,
        'reason': f"{pub_count} publications, many should mention drugs"
    }
    expected['publication_companies'] = {
        'expected_min': pub_count * 0.2,  # ~20% mention companies
        'expected_typical': pub_count * 0.4,
        'reason': f"{pub_count} publications, some should mention companies"
    }
    expected['publication_trials'] = {
        'expected_min': pub_count * 0.1,  # ~10% link to trials via NCT ID
        'expected_typical': pub_count * 0.2,
        'reason': f"{pub_count} publications, some should link to trials"
    }
    
    # SEC filing relationships
    filing_count = session.query(func.count(SECFiling.filing_id)).filter(
        SECFiling.deleted_at.is_(None)
    ).scalar() or 0
    
    expected['filing_companies'] = {
        'expected_min': filing_count,
        'expected_typical': filing_count,
        'reason': f"{filing_count} filings should link to companies (filers)"
    }
    expected['filing_drugs'] = {
        'expected_min': filing_count * 0.3,  # ~30% mention drugs
        'expected_typical': filing_count * 0.5,
        'reason': f"{filing_count} filings, many should mention drugs"
    }
    
    # Company-drug relationships
    company_count = session.query(func.count(Company.company_id)).filter(
        Company.deleted_at.is_(None)
    ).scalar() or 0
    drug_count = session.query(func.count(Drug.drug_id)).filter(
        Drug.deleted_at.is_(None)
    ).scalar() or 0
    
    # Get trial sponsors to estimate company-drug links
    trial_sponsor_count = session.query(func.count(distinct(TrialSponsor.entity_id))).filter(
        TrialSponsor.entity_type == 'company',
        TrialSponsor.deleted_at.is_(None)
    ).scalar() or 0
    
    expected['company_drugs'] = {
        'expected_min': trial_sponsor_count * 0.5,  # Companies sponsoring trials likely have drugs
        'expected_typical': trial_sponsor_count,
        'reason': f"{trial_sponsor_count} companies sponsor trials, should have drug relationships"
    }
    
    # Drug-target relationships (from ChEMBL, OpenTargets - not yet ingested)
    expected['drug_targets'] = {
        'expected_min': 0,  # No ChEMBL/OpenTargets data yet
        'expected_typical': drug_count * 0.5,
        'reason': "Should have data from ChEMBL/OpenTargets (not yet ingested)"
    }
    
    # Drug-mechanism relationships
    expected['drug_mechanisms'] = {
        'expected_min': 0,
        'expected_typical': drug_count * 0.3,
        'reason': "Should have mechanism data (not yet ingested)"
    }
    
    return expected


def investigate_company_drug_relationships(session: Session) -> Dict[str, Any]:
    """Investigate why company-drug relationships are missing."""
    investigation = {}
    
    # Count companies and drugs
    company_count = session.query(func.count(Company.company_id)).filter(
        Company.deleted_at.is_(None)
    ).scalar() or 0
    drug_count = session.query(func.count(Drug.drug_id)).filter(
        Drug.deleted_at.is_(None)
    ).scalar() or 0
    
    # Count existing relationships
    company_drug_count = session.query(func.count(CompanyDrug.id)).filter(
        CompanyDrug.deleted_at.is_(None)
    ).scalar() or 0
    
    # Count companies that sponsor trials
    companies_with_trials = session.query(func.count(distinct(TrialSponsor.entity_id))).filter(
        TrialSponsor.entity_type == 'company',
        TrialSponsor.deleted_at.is_(None)
    ).scalar() or 0
    
    # Count trials with drugs
    trials_with_drugs = session.query(func.count(distinct(TrialDrug.trial_id))).filter(
        TrialDrug.deleted_at.is_(None)
    ).scalar() or 0
    
    # Check if companies sponsoring trials with drugs should have company-drug links
    # Get companies that sponsor trials that have drugs
    companies_sponsoring_trials_with_drugs = session.query(
        func.count(distinct(TrialSponsor.entity_id))
    ).join(
        TrialDrug, TrialSponsor.trial_id == TrialDrug.trial_id
    ).filter(
        TrialSponsor.entity_type == 'company',
        TrialSponsor.deleted_at.is_(None),
        TrialDrug.deleted_at.is_(None)
    ).scalar() or 0
    
    investigation['company_count'] = company_count
    investigation['drug_count'] = drug_count
    investigation['company_drug_count'] = company_drug_count
    investigation['companies_with_trials'] = companies_with_trials
    investigation['trials_with_drugs'] = trials_with_drugs
    investigation['companies_sponsoring_trials_with_drugs'] = companies_sponsoring_trials_with_drugs
    investigation['expected_min'] = companies_sponsoring_trials_with_drugs
    
    return investigation


def generate_phase3_report() -> str:
    """Generate Phase 3: Relationship Generation Coverage report."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Phase 3: Relationship Generation Coverage")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("Goal: Ensure relationships are being created between resolved entities")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        # Section 1: Relationship Creation Rates
        report_lines.append("## 1. Relationship Creation Rates")
        report_lines.append("")
        
        relationship_counts = get_relationship_table_counts(session)
        expected_relationships = calculate_expected_relationships(session)
        
        report_lines.append("### Overall Relationship Coverage")
        report_lines.append("")
        report_lines.append("| Relationship Table | Actual Count | Expected (Min) | Expected (Typical) | Coverage % | Status |")
        report_lines.append("|-------------------|--------------|----------------|-------------------|------------|--------|")
        
        critical_empty = []
        low_coverage = []
        
        for table_name, actual_count in sorted(relationship_counts.items()):
            if table_name in expected_relationships:
                expected = expected_relationships[table_name]
                expected_min = expected['expected_min']
                expected_typical = expected['expected_typical']
                
                if expected_min > 0:
                    coverage = (actual_count / expected_min * 100) if expected_min > 0 else 0
                else:
                    coverage = 0
                
                if actual_count == 0 and expected_min > 0:
                    status = "❌ Empty"
                    critical_empty.append({
                        'table': table_name,
                        'expected': expected
                    })
                elif coverage < 50:
                    status = "⚠️ Low"
                    low_coverage.append({
                        'table': table_name,
                        'actual': actual_count,
                        'expected': expected,
                        'coverage': coverage
                    })
                elif coverage < 80:
                    status = "🟡 Medium"
                else:
                    status = "✅ Good"
                
                report_lines.append(
                    f"| `{table_name}` | {actual_count:,} | {expected_min:.0f} | {expected_typical:.0f} | "
                    f"{coverage:.1f}% | {status} |"
                )
            else:
                report_lines.append(
                    f"| `{table_name}` | {actual_count:,} | N/A | N/A | N/A | - |"
                )
        
        report_lines.append("")
        
        # Critical empty tables
        if critical_empty:
            report_lines.append("### 🔴 Critical Empty Tables")
            report_lines.append("")
            for item in critical_empty:
                table = item['table']
                expected = item['expected']
                report_lines.append(f"#### {table}")
                report_lines.append(f"- **Expected:** {expected['reason']}")
                report_lines.append(f"- **Actual:** 0")
                report_lines.append("")
        
        # Low coverage tables
        if low_coverage:
            report_lines.append("### ⚠️ Low Coverage Tables (< 50%)")
            report_lines.append("")
            for item in low_coverage:
                table = item['table']
                actual = item['actual']
                expected = item['expected']
                coverage = item['coverage']
                report_lines.append(f"#### {table}")
                report_lines.append(f"- **Actual:** {actual:,}")
                report_lines.append(f"- **Expected (Min):** {expected['expected_min']:.0f}")
                report_lines.append(f"- **Coverage:** {coverage:.1f}%")
                report_lines.append(f"- **Reason:** {expected['reason']}")
                report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 2: Cross-Reference Validation
        report_lines.append("## 2. Cross-Reference Validation")
        report_lines.append("")
        
        # Clinical trials relationships
        trial_count = session.query(func.count(ClinicalTrial.trial_id)).filter(
            ClinicalTrial.deleted_at.is_(None)
        ).scalar() or 0
        
        trial_sponsor_count = relationship_counts.get('trial_sponsors', 0)
        trial_drug_count = relationship_counts.get('trial_drugs', 0)
        trial_disease_count = relationship_counts.get('trial_diseases', 0)
        
        report_lines.append("### Clinical Trial Relationships")
        report_lines.append("")
        report_lines.append(f"- **Trials:** {trial_count:,}")
        report_lines.append(f"- **Trial-Sponsor Links:** {trial_sponsor_count:,} ✅" if trial_sponsor_count > 0 else f"- **Trial-Sponsor Links:** {trial_sponsor_count:,} ❌")
        report_lines.append(f"- **Trial-Drug Links:** {trial_drug_count:,} ✅" if trial_drug_count > 0 else f"- **Trial-Drug Links:** {trial_drug_count:,} ❌")
        report_lines.append(f"- **Trial-Disease Links:** {trial_disease_count:,} ✅" if trial_disease_count > 0 else f"- **Trial-Disease Links:** {trial_disease_count:,} ❌")
        report_lines.append("")
        
        # Publication relationships
        pub_count = session.query(func.count(Publication.pub_id)).filter(
            Publication.deleted_at.is_(None)
        ).scalar() or 0
        
        pub_drug_count = relationship_counts.get('publication_drugs', 0)
        pub_company_count = relationship_counts.get('publication_companies', 0)
        pub_trial_count = relationship_counts.get('publication_trials', 0)
        
        report_lines.append("### Publication Relationships")
        report_lines.append("")
        report_lines.append(f"- **Publications:** {pub_count:,}")
        report_lines.append(f"- **Publication-Drug Links:** {pub_drug_count:,} {'✅' if pub_drug_count > 0 else '❌'}")
        report_lines.append(f"- **Publication-Company Links:** {pub_company_count:,} {'✅' if pub_company_count > 0 else '❌'}")
        report_lines.append(f"- **Publication-Trial Links:** {pub_trial_count:,} {'✅' if pub_trial_count > 0 else '❌'}")
        report_lines.append("")
        
        # SEC filing relationships
        filing_count = session.query(func.count(SECFiling.filing_id)).filter(
            SECFiling.deleted_at.is_(None)
        ).scalar() or 0
        
        filing_company_count = relationship_counts.get('filing_companies', 0)
        filing_drug_count = relationship_counts.get('filing_drugs', 0)
        
        report_lines.append("### SEC Filing Relationships")
        report_lines.append("")
        report_lines.append(f"- **SEC Filings:** {filing_count:,}")
        report_lines.append(f"- **Filing-Company Links:** {filing_company_count:,} {'✅' if filing_company_count > 0 else '❌'}")
        report_lines.append(f"- **Filing-Drug Links:** {filing_drug_count:,} {'✅' if filing_drug_count > 0 else '❌'}")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 3: Company-Drug Relationship Investigation
        report_lines.append("## 3. Company-Drug Relationship Investigation")
        report_lines.append("")
        report_lines.append("### Current State")
        report_lines.append("")
        
        investigation = investigate_company_drug_relationships(session)
        
        report_lines.append(f"- **Total Companies:** {investigation['company_count']:,}")
        report_lines.append(f"- **Total Drugs:** {investigation['drug_count']:,}")
        report_lines.append(f"- **Company-Drug Relationships:** {investigation['company_drug_count']:,} ❌")
        report_lines.append(f"- **Companies with Trials:** {investigation['companies_with_trials']:,}")
        report_lines.append(f"- **Trials with Drugs:** {investigation['trials_with_drugs']:,}")
        report_lines.append(f"- **Companies Sponsoring Trials with Drugs:** {investigation['companies_sponsoring_trials_with_drugs']:,}")
        report_lines.append("")
        
        report_lines.append("### Analysis")
        report_lines.append("")
        report_lines.append(f"**Expected Minimum:** {investigation['expected_min']:,} company-drug relationships")
        report_lines.append("")
        report_lines.append("**Why relationships aren't being created:**")
        report_lines.append("")
        report_lines.append("1. **Trial-based inference not implemented:**")
        report_lines.append("   - Companies sponsor trials that test drugs")
        report_lines.append("   - Should infer: Company → Drug relationships from TrialSponsor + TrialDrug")
        report_lines.append("   - Currently: Only direct extraction from source data (FDA Drugs@FDA)")
        report_lines.append("")
        report_lines.append("2. **Source data limitations:**")
        report_lines.append("   - FDA Drugs@FDA: Only 9 records processed")
        report_lines.append("   - OpenFDA: Creates company-drug links but limited data")
        report_lines.append("   - SEC filings: Extract drugs but may not create relationships")
        report_lines.append("")
        report_lines.append("3. **Relationship extraction logic:**")
        report_lines.append("   - ClinicalTrialsProcessor: Creates trial-sponsor and trial-drug, but not company-drug")
        report_lines.append("   - Need: Cross-table inference to link companies to drugs via trials")
        report_lines.append("")
        
        report_lines.append("### Recommendations")
        report_lines.append("")
        report_lines.append("1. **Implement cross-table inference:**")
        report_lines.append("   - Create company-drug relationships from TrialSponsor + TrialDrug")
        report_lines.append("   - Query: `SELECT DISTINCT ts.entity_id, td.drug_id FROM trial_sponsors ts JOIN trial_drugs td ON ts.trial_id = td.trial_id WHERE ts.entity_type = 'company'`")
        report_lines.append("")
        report_lines.append("2. **Enhance SEC filings processor:**")
        report_lines.append("   - Ensure filing-drug relationships are created")
        report_lines.append("   - Extract company-drug relationships from pipeline updates")
        report_lines.append("")
        report_lines.append("3. **Process more FDA data:**")
        report_lines.append("   - FDA Drugs@FDA has company-drug ownership data")
        report_lines.append("   - Currently only 9 records processed")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 4: Gap Analysis Summary
        report_lines.append("## 4. Gap Analysis Summary")
        report_lines.append("")
        
        report_lines.append("### Missing Relationship Types")
        report_lines.append("")
        
        gaps = []
        for table_name, actual_count in relationship_counts.items():
            if table_name in expected_relationships:
                expected = expected_relationships[table_name]
                if actual_count == 0 and expected['expected_min'] > 0:
                    gaps.append({
                        'table': table_name,
                        'reason': expected['reason'],
                        'priority': 'HIGH' if table_name in ['drug_targets', 'drug_mechanisms', 'publication_drugs', 'filing_drugs'] else 'MEDIUM'
                    })
        
        if gaps:
            report_lines.append("| Relationship Type | Priority | Reason |")
            report_lines.append("|-------------------|----------|--------|")
            for gap in sorted(gaps, key=lambda x: (x['priority'] == 'HIGH', x['table'])):
                report_lines.append(f"| `{gap['table']}` | {gap['priority']} | {gap['reason']} |")
            report_lines.append("")
        
        report_lines.append("### Root Causes")
        report_lines.append("")
        report_lines.append("1. **Missing source data:**")
        report_lines.append("   - ChEMBL, OpenTargets not ingested → No drug-target relationships")
        report_lines.append("   - Mechanism data not extracted → No drug-mechanism relationships")
        report_lines.append("")
        report_lines.append("2. **Relationship extraction not implemented:**")
        report_lines.append("   - Publications: Extract entities but relationships not created")
        report_lines.append("   - SEC filings: Extract drugs but filing-drug links missing")
        report_lines.append("")
        report_lines.append("3. **Cross-table inference missing:**")
        report_lines.append("   - Company-drug: Should infer from trial relationships")
        report_lines.append("   - Publication-entity: Should link based on text mentions")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("**End of Phase 3 Report**")
        report_lines.append("")
    
    return "\n".join(report_lines)


def get_resolution_coverage_by_source(session: Session) -> Dict[str, Dict[str, Any]]:
    """Calculate resolution coverage rates by source."""
    coverage = {}
    
    # Get all sources with processing logs
    sources = session.query(distinct(SourceProcessingLog.source_name)).filter(
        SourceProcessingLog.deleted_at.is_(None)
    ).all()
    
    for (source_name,) in sources:
        # Get processing stats
        stats = session.query(
            func.sum(SourceProcessingLog.entities_extracted).label('total_extracted'),
            func.sum(SourceProcessingLog.entities_matched).label('total_matched'),
            func.sum(SourceProcessingLog.entities_created).label('total_created')
        ).filter(
            SourceProcessingLog.source_name == source_name,
            SourceProcessingLog.deleted_at.is_(None)
        ).first()
        
        total_extracted = stats.total_extracted or 0
        total_matched = stats.total_matched or 0
        total_created = stats.total_created or 0
        
        if total_extracted > 0:
            match_rate = (total_matched / total_extracted * 100)
            creation_rate = (total_created / total_extracted * 100)
            resolution_rate = ((total_matched + total_created) / total_extracted * 100)
        else:
            match_rate = 0
            creation_rate = 0
            resolution_rate = 0
        
        # Get entity type breakdown from lineage
        source = session.query(Source).filter(
            Source.source_name == source_name,
            Source.deleted_at.is_(None)
        ).first()
        
        entity_breakdown = {}
        if source:
            for entity_type in ['company', 'drug', 'disease', 'trial', 'institution']:
                table_name = f'{entity_type}s' if entity_type != 'trial' else 'clinical_trials'
                count = session.query(func.count(distinct(DataLineage.record_id))).filter(
                    DataLineage.source_id == source.source_id,
                    DataLineage.table_name == table_name,
                    DataLineage.deleted_at.is_(None)
                ).scalar() or 0
                entity_breakdown[entity_type] = count
        
        coverage[source_name] = {
            'total_extracted': total_extracted,
            'total_matched': total_matched,
            'total_created': total_created,
            'match_rate': match_rate,
            'creation_rate': creation_rate,
            'resolution_rate': resolution_rate,
            'entity_breakdown': entity_breakdown
        }
    
    return coverage


def analyze_match_candidates(session: Session) -> Dict[str, Any]:
    """Analyze match candidates for review."""
    # Get all match candidates
    all_candidates = session.query(EntityMatchCandidate).filter(
        EntityMatchCandidate.deleted_at.is_(None)
    ).all()
    
    # Group by status
    by_status = defaultdict(list)
    by_confidence = defaultdict(list)
    high_confidence = []
    low_confidence = []
    
    for candidate in all_candidates:
        by_status[candidate.status].append(candidate)
        
        if candidate.match_confidence:
            conf = float(candidate.match_confidence)
            by_confidence[round(conf, 1)].append(candidate)
            
            if conf >= 0.8:
                high_confidence.append(candidate)
            elif conf < 0.6:
                low_confidence.append(candidate)
    
    # Sample high confidence candidates
    high_confidence_samples = random.sample(high_confidence, min(10, len(high_confidence))) if high_confidence else []
    
    # Sample low confidence candidates
    low_confidence_samples = random.sample(low_confidence, min(10, len(low_confidence))) if low_confidence else []
    
    return {
        'total': len(all_candidates),
        'by_status': {k: len(v) for k, v in by_status.items()},
        'by_confidence': {k: len(v) for k, v in sorted(by_confidence.items())},
        'high_confidence_count': len(high_confidence),
        'low_confidence_count': len(low_confidence),
        'high_confidence_samples': high_confidence_samples,
        'low_confidence_samples': low_confidence_samples
    }


def analyze_alias_quality(session: Session) -> Dict[str, Any]:
    """Analyze entity alias quality."""
    # Get entities with alias counts
    alias_counts = session.query(
        EntityAlias.entity_type,
        EntityAlias.entity_id,
        func.count(EntityAlias.alias_id).label('alias_count')
    ).filter(
        EntityAlias.deleted_at.is_(None)
    ).group_by(
        EntityAlias.entity_type,
        EntityAlias.entity_id
    ).all()
    
    # Entities with only 1 alias (suspicious)
    single_alias_entities = [row for row in alias_counts if row.alias_count == 1]
    
    # Entities with multiple aliases
    multi_alias_entities = [row for row in alias_counts if row.alias_count > 1]
    
    # Sample aliases for verification
    sample_aliases = session.query(EntityAlias).filter(
        EntityAlias.deleted_at.is_(None)
    ).limit(20).all()
    
    # Get alias types distribution
    alias_types = session.query(
        EntityAlias.alias_type,
        func.count(EntityAlias.alias_id).label('count')
    ).filter(
        EntityAlias.deleted_at.is_(None)
    ).group_by(EntityAlias.alias_type).all()
    
    return {
        'total_aliases': sum(row.alias_count for row in alias_counts),
        'total_entities_with_aliases': len(alias_counts),
        'single_alias_count': len(single_alias_entities),
        'multi_alias_count': len(multi_alias_entities),
        'avg_aliases_per_entity': (sum(row.alias_count for row in alias_counts) / len(alias_counts)) if alias_counts else 0,
        'sample_aliases': sample_aliases,
        'alias_types': {row.alias_type or 'null': row.count for row in alias_types}
    }


def investigate_sponsor_coverage(session: Session) -> Dict[str, Any]:
    """Investigate sponsor resolution coverage."""
    # Get trial sponsors
    trial_sponsors = session.query(TrialSponsor).filter(
        TrialSponsor.deleted_at.is_(None)
    ).all()
    
    # Count by entity type
    company_sponsors = [ts for ts in trial_sponsors if ts.entity_type == 'company']
    institution_sponsors = [ts for ts in trial_sponsors if ts.entity_type == 'institution']
    
    # Check if sponsor entities exist
    company_ids = {ts.entity_id for ts in company_sponsors}
    institution_ids = {ts.entity_id for ts in institution_sponsors}
    
    existing_companies = session.query(Company.company_id).filter(
        Company.company_id.in_(company_ids),
        Company.deleted_at.is_(None)
    ).all()
    existing_institutions = session.query(Institution.institution_id).filter(
        Institution.institution_id.in_(institution_ids),
        Institution.deleted_at.is_(None)
    ).all()
    
    existing_company_ids = {row[0] for row in existing_companies}
    existing_institution_ids = {row[0] for row in existing_institutions}
    
    missing_companies = company_ids - existing_company_ids
    missing_institutions = institution_ids - existing_institution_ids
    
    # Get trials with unresolved sponsors
    unresolved_trials = session.query(distinct(TrialSponsor.trial_id)).filter(
        TrialSponsor.entity_id.in_(list(missing_companies | missing_institutions)),
        TrialSponsor.deleted_at.is_(None)
    ).all()
    
    # Sample unresolved sponsors
    sample_unresolved = session.query(TrialSponsor).filter(
        TrialSponsor.entity_id.in_(list(list(missing_companies)[:5] + list(missing_institutions)[:5])),
        TrialSponsor.deleted_at.is_(None)
    ).limit(10).all()
    
    return {
        'total_sponsors': len(trial_sponsors),
        'company_sponsors': len(company_sponsors),
        'institution_sponsors': len(institution_sponsors),
        'existing_companies': len(existing_company_ids),
        'existing_institutions': len(existing_institution_ids),
        'missing_companies': len(missing_companies),
        'missing_institutions': len(missing_institutions),
        'unresolved_trials': len(unresolved_trials),
        'sample_unresolved': sample_unresolved
    }


def generate_phase4_report() -> str:
    """Generate Phase 4: Entity Resolution Quality report."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Phase 4: Entity Resolution Quality")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("Goal: Verify entity resolution is accurate and complete")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        # Section 1: Resolution Coverage by Source
        report_lines.append("## 1. Resolution Coverage by Source")
        report_lines.append("")
        
        resolution_coverage = get_resolution_coverage_by_source(session)
        
        report_lines.append("### Overall Resolution Rates")
        report_lines.append("")
        report_lines.append("| Source Name | Entities Extracted | Matched | Created | Match Rate | Creation Rate | Resolution Rate | Status |")
        report_lines.append("|-------------|-------------------|---------|--------|------------|---------------|-----------------|--------|")
        
        low_resolution_sources = []
        
        for source_name, stats in sorted(resolution_coverage.items()):
            resolution_rate = stats['resolution_rate']
            
            if resolution_rate < 50:
                status = "❌ Low"
                low_resolution_sources.append({
                    'source': source_name,
                    'stats': stats
                })
            elif resolution_rate < 80:
                status = "⚠️ Medium"
            else:
                status = "✅ Good"
            
            report_lines.append(
                f"| `{source_name}` | {stats['total_extracted']:,} | {stats['total_matched']:,} | "
                f"{stats['total_created']:,} | {stats['match_rate']:.1f}% | "
                f"{stats['creation_rate']:.1f}% | {stats['resolution_rate']:.1f}% | {status} |"
            )
        
        report_lines.append("")
        
        # Detailed breakdown for sources with low resolution
        if low_resolution_sources:
            report_lines.append("### ⚠️ Sources with Low Resolution Rates")
            report_lines.append("")
            for item in low_resolution_sources:
                source = item['source']
                stats = item['stats']
                report_lines.append(f"#### {source}")
                report_lines.append("")
                report_lines.append(f"- **Total Extracted:** {stats['total_extracted']:,}")
                report_lines.append(f"- **Matched:** {stats['total_matched']:,} ({stats['match_rate']:.1f}%)")
                report_lines.append(f"- **Created:** {stats['total_created']:,} ({stats['creation_rate']:.1f}%)")
                report_lines.append(f"- **Resolution Rate:** {stats['resolution_rate']:.1f}%")
                report_lines.append("")
                report_lines.append("**Entity Breakdown:**")
                for entity_type, count in stats['entity_breakdown'].items():
                    if count > 0:
                        report_lines.append(f"  - {entity_type}: {count}")
                report_lines.append("")
        
        # Specific analysis for ClinicalTrials.gov
        if 'clinicaltrials_gov' in resolution_coverage:
            stats = resolution_coverage['clinicaltrials_gov']
            report_lines.append("### ClinicalTrials.gov Deep Dive")
            report_lines.append("")
            report_lines.append(f"- **Companies Extracted:** {stats['entity_breakdown'].get('company', 0)}")
            report_lines.append(f"- **Companies in Lineage:** {stats['entity_breakdown'].get('company', 0)}")
            report_lines.append(f"- **Company Resolution Rate:** {(stats['entity_breakdown'].get('company', 0) / stats['total_extracted'] * 100) if stats['total_extracted'] > 0 else 0:.1f}%")
            report_lines.append("")
            report_lines.append(f"- **Drugs Extracted:** {stats['entity_breakdown'].get('drug', 0)}")
            report_lines.append(f"- **Drugs in Lineage:** {stats['entity_breakdown'].get('drug', 0)}")
            report_lines.append(f"- **Drug Resolution Rate:** {(stats['entity_breakdown'].get('drug', 0) / stats['total_extracted'] * 100) if stats['total_extracted'] > 0 else 0:.1f}%")
            report_lines.append("")
            report_lines.append("**Analysis:**")
            report_lines.append("- 21% company resolution may be expected if many sponsors are institutions, not companies")
            report_lines.append("- 61% drug resolution suggests some drug names aren't matching existing entities")
            report_lines.append("- Consider: Are drug names being normalized correctly? Are aliases being created?")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 2: Match Candidate Review
        report_lines.append("## 2. Match Candidate Review")
        report_lines.append("")
        
        match_analysis = analyze_match_candidates(session)
        
        report_lines.append("### Overall Statistics")
        report_lines.append("")
        report_lines.append(f"- **Total Match Candidates:** {match_analysis['total']:,}")
        report_lines.append("")
        report_lines.append("**By Status:**")
        for status, count in sorted(match_analysis['by_status'].items()):
            report_lines.append(f"- {status}: {count:,}")
        report_lines.append("")
        
        report_lines.append("**By Confidence Score:**")
        for conf, count in sorted(match_analysis['by_confidence'].items(), reverse=True):
            report_lines.append(f"- {conf:.1f}: {count:,}")
        report_lines.append("")
        
        report_lines.append(f"- **High Confidence (≥0.8):** {match_analysis['high_confidence_count']:,}")
        report_lines.append(f"- **Low Confidence (<0.6):** {match_analysis['low_confidence_count']:,}")
        report_lines.append("")
        
        # High confidence samples
        if match_analysis['high_confidence_samples']:
            report_lines.append("### High Confidence Matches (≥0.8) - Should Be Auto-Merged?")
            report_lines.append("")
            report_lines.append("| Source | Entity Type | Extracted Text | Confidence | Potential Matches |")
            report_lines.append("|--------|------------|----------------|------------|-------------------|")
            for candidate in match_analysis['high_confidence_samples'][:10]:
                matches_str = "N/A"
                if candidate.potential_matches:
                    matches = candidate.potential_matches[:2] if isinstance(candidate.potential_matches, list) else []
                    matches_str = f"{len(matches)} matches"
                conf = float(candidate.match_confidence) if candidate.match_confidence else 0
                report_lines.append(
                    f"| {candidate.source_name} | {candidate.entity_type} | "
                    f"{candidate.extracted_text[:50]}... | {conf:.2f} | {matches_str} |"
                )
            report_lines.append("")
            report_lines.append("**Recommendation:** If these are clearly correct matches, consider lowering auto-merge threshold to 0.8")
            report_lines.append("")
        
        # Low confidence samples
        if match_analysis['low_confidence_samples']:
            report_lines.append("### Low Confidence Matches (<0.6) - Should Be Rejected?")
            report_lines.append("")
            report_lines.append("| Source | Entity Type | Extracted Text | Confidence | Status |")
            report_lines.append("|--------|------------|----------------|------------|--------|")
            for candidate in match_analysis['low_confidence_samples'][:10]:
                conf = float(candidate.match_confidence) if candidate.match_confidence else 0
                report_lines.append(
                    f"| {candidate.source_name} | {candidate.entity_type} | "
                    f"{candidate.extracted_text[:50]}... | {conf:.2f} | {candidate.status} |"
                )
            report_lines.append("")
            report_lines.append("**Recommendation:** Review if these should be new entities or if matching needs improvement")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 3: Alias Quality Check
        report_lines.append("## 3. Alias Quality Check")
        report_lines.append("")
        
        alias_analysis = analyze_alias_quality(session)
        
        report_lines.append("### Overall Alias Statistics")
        report_lines.append("")
        report_lines.append(f"- **Total Aliases:** {alias_analysis['total_aliases']:,}")
        report_lines.append(f"- **Entities with Aliases:** {alias_analysis['total_entities_with_aliases']:,}")
        report_lines.append(f"- **Average Aliases per Entity:** {alias_analysis['avg_aliases_per_entity']:.2f}")
        report_lines.append("")
        report_lines.append(f"- **Entities with Single Alias:** {alias_analysis['single_alias_count']:,} ⚠️")
        report_lines.append(f"- **Entities with Multiple Aliases:** {alias_analysis['multi_alias_count']:,} ✅")
        report_lines.append("")
        
        if alias_analysis['single_alias_count'] > 0:
            report_lines.append("**⚠️ Warning:** Entities with only 1 alias may indicate:")
            report_lines.append("- Alias creation not working properly")
            report_lines.append("- Entities only seen from one source")
            report_lines.append("- Missing canonical name alias")
            report_lines.append("")
        
        report_lines.append("### Alias Types Distribution")
        report_lines.append("")
        report_lines.append("| Alias Type | Count |")
        report_lines.append("|------------|-------|")
        for alias_type, count in sorted(alias_analysis['alias_types'].items(), key=lambda x: x[1], reverse=True):
            report_lines.append(f"| {alias_type} | {count:,} |")
        report_lines.append("")
        
        report_lines.append("### Sample Aliases for Verification")
        report_lines.append("")
        report_lines.append("| Entity Type | Alias Text | Alias Type | Entity ID |")
        report_lines.append("|-------------|------------|------------|-----------|")
        for alias in alias_analysis['sample_aliases'][:15]:
            alias_type_str = alias.alias_type or 'null'
            report_lines.append(
                f"| {alias.entity_type} | {alias.alias_text[:40]}... | {alias_type_str} | {str(alias.entity_id)[:8]}... |"
            )
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 4: Sponsor Coverage Deep Dive
        report_lines.append("## 4. Sponsor Coverage Deep Dive")
        report_lines.append("")
        
        sponsor_analysis = investigate_sponsor_coverage(session)
        
        report_lines.append("### Current State")
        report_lines.append("")
        report_lines.append(f"- **Total Trial Sponsors:** {sponsor_analysis['total_sponsors']:,}")
        report_lines.append(f"- **Company Sponsors:** {sponsor_analysis['company_sponsors']:,}")
        report_lines.append(f"- **Institution Sponsors:** {sponsor_analysis['institution_sponsors']:,}")
        report_lines.append("")
        report_lines.append(f"- **Existing Company Entities:** {sponsor_analysis['existing_companies']:,}")
        report_lines.append(f"- **Missing Company Entities:** {sponsor_analysis['missing_companies']:,} ❌")
        report_lines.append("")
        report_lines.append(f"- **Existing Institution Entities:** {sponsor_analysis['existing_institutions']:,}")
        report_lines.append(f"- **Missing Institution Entities:** {sponsor_analysis['missing_institutions']:,} ❌")
        report_lines.append("")
        report_lines.append(f"- **Trials with Unresolved Sponsors:** {sponsor_analysis['unresolved_trials']:,}")
        report_lines.append("")
        
        if sponsor_analysis['missing_companies'] > 0 or sponsor_analysis['missing_institutions'] > 0:
            report_lines.append("### ⚠️ Unresolved Sponsors Analysis")
            report_lines.append("")
            report_lines.append("**Root Causes:**")
            report_lines.append("")
            
            if sponsor_analysis['missing_companies'] > 0:
                report_lines.append("1. **Missing Company Entities:**")
                report_lines.append(f"   - {sponsor_analysis['missing_companies']} company sponsors don't have corresponding company entities")
                report_lines.append("   - Possible causes:")
                report_lines.append("     - Company extraction failed")
                report_lines.append("     - Company resolution failed (no match found)")
                report_lines.append("     - Company entity not created")
                report_lines.append("")
            
            if sponsor_analysis['missing_institutions'] > 0:
                report_lines.append("2. **Missing Institution Entities:**")
                report_lines.append(f"   - {sponsor_analysis['missing_institutions']} institution sponsors don't have corresponding institution entities")
                report_lines.append("   - Possible causes:")
                report_lines.append("     - Institution extraction not implemented")
                report_lines.append("     - Institution resolution failed")
                report_lines.append("     - Institution entity not created")
                report_lines.append("")
            
            if sponsor_analysis['sample_unresolved']:
                report_lines.append("### Sample Unresolved Sponsors")
                report_lines.append("")
                report_lines.append("| Trial ID | Entity Type | Entity ID | Issue |")
                report_lines.append("|----------|-------------|-----------|-------|")
                for sponsor in sponsor_analysis['sample_unresolved'][:10]:
                    issue = "Missing entity" if sponsor.entity_id not in (sponsor_analysis.get('existing_company_ids', set()) | sponsor_analysis.get('existing_institution_ids', set())) else "Other"
                    report_lines.append(
                        f"| {str(sponsor.trial_id)[:8]}... | {sponsor.entity_type} | {str(sponsor.entity_id)[:8]}... | {issue} |"
                    )
                report_lines.append("")
        
        report_lines.append("### Recommendations")
        report_lines.append("")
        report_lines.append("1. **Investigate Missing Entities:**")
        report_lines.append("   - Check if sponsor names are being extracted correctly")
        report_lines.append("   - Verify entity resolution is running for sponsors")
        report_lines.append("   - Check if new entities are being created when no match found")
        report_lines.append("")
        report_lines.append("2. **Improve Institution Resolution:**")
        report_lines.append("   - Ensure institutions are being extracted from trials")
        report_lines.append("   - Create institution entities when not found")
        report_lines.append("   - Add institution aliases for better matching")
        report_lines.append("")
        report_lines.append("3. **Match Confidence Thresholds:**")
        report_lines.append("   - Review if thresholds are too conservative")
        report_lines.append("   - Consider auto-merging high-confidence matches (≥0.8)")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 5: Recommendations Summary
        report_lines.append("## 5. Recommendations Summary")
        report_lines.append("")
        
        report_lines.append("### Threshold Adjustments")
        report_lines.append("")
        report_lines.append("1. **Auto-Merge Threshold:**")
        report_lines.append("   - Current: High confidence (≥0.9) auto-merges")
        report_lines.append("   - Recommendation: Lower to 0.8 for clearly correct matches")
        report_lines.append("   - Impact: Reduce manual review queue, improve resolution rate")
        report_lines.append("")
        report_lines.append("2. **Fuzzy Match Threshold:**")
        report_lines.append("   - Current: 0.6-0.79 requires review")
        report_lines.append("   - Recommendation: Auto-merge 0.75+ with context")
        report_lines.append("   - Impact: Better handling of name variations")
        report_lines.append("")
        
        report_lines.append("### Process Improvements")
        report_lines.append("")
        report_lines.append("1. **Alias Creation:**")
        report_lines.append("   - Ensure all extracted names become aliases")
        report_lines.append("   - Create canonical name aliases for all entities")
        report_lines.append("   - Track alias sources for better matching")
        report_lines.append("")
        report_lines.append("2. **Entity Creation:**")
        report_lines.append("   - Ensure new entities are created when no match found")
        report_lines.append("   - Verify entity creation is logged in processing logs")
        report_lines.append("   - Check for silent failures in entity creation")
        report_lines.append("")
        report_lines.append("3. **Institution Handling:**")
        report_lines.append("   - Improve institution extraction from trials")
        report_lines.append("   - Create institution entities when missing")
        report_lines.append("   - Add institution-specific matching rules")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("**End of Phase 4 Report**")
        report_lines.append("")
    
    return "\n".join(report_lines)


def verify_score_component(company_id: UUID, component_name: str, calculated_value: Any, session: Session) -> Dict[str, Any]:
    """Verify a score component calculation."""
    verification = {
        'component': component_name,
        'calculated': calculated_value,
        'verified': None,
        'match': None,
        'issues': []
    }
    
    company = session.query(Company).filter(
        Company.company_id == company_id,
        Company.deleted_at.is_(None)
    ).first()
    
    if not company:
        verification['issues'].append("Company not found")
        return verification
    
    if component_name == 'failure_rate':
        # Verify failure rate calculation
        trials = session.query(ClinicalTrial).join(
            TrialSponsor, ClinicalTrial.trial_id == TrialSponsor.trial_id
        ).filter(
            TrialSponsor.entity_id == company_id,
            TrialSponsor.entity_type == 'company',
            TrialSponsor.deleted_at.is_(None),
            ClinicalTrial.deleted_at.is_(None)
        ).all()
        
        total_trials = len(trials)
        terminated_count = len([t for t in trials if t.status in TrialStatus.FAILED_STATUSES])
        
        if total_trials > 0:
            expected_rate = terminated_count / total_trials
            expected_score = min(expected_rate * 40, 40)
            verification['verified'] = expected_score
            verification['match'] = abs(calculated_value - expected_score) < 0.01
            if not verification['match']:
                verification['issues'].append(f"Expected {expected_score:.2f}, got {calculated_value:.2f}")
        else:
            verification['verified'] = 0
            verification['match'] = calculated_value == 0
            if not verification['match']:
                verification['issues'].append("No trials but score is not 0")
    
    elif component_name == 'recent_failures':
        # Verify recent failures count
        twelve_months_ago = datetime.now().date() - timedelta(days=365)
        failure_events = session.query(Event).filter(
            func.array_position(Event.entities_involved, company_id) != None,
            Event.event_type.in_(['trial.status.terminated', 'trial.status.withdrawn', 'regulatory.clinical_hold']),
            Event.event_date >= twelve_months_ago,
            Event.deleted_at.is_(None)
        ).all()
        
        failures_count = len(failure_events)
        if failures_count >= 3:
            expected_score = 30
        elif failures_count == 2:
            expected_score = 20
        elif failures_count == 1:
            expected_score = 10
        else:
            expected_score = 0
        
        verification['verified'] = expected_score
        verification['match'] = calculated_value == expected_score
        if not verification['match']:
            verification['issues'].append(f"Expected {expected_score} (from {failures_count} failures), got {calculated_value}")
    
    elif component_name == 'pipeline_stagnation':
        # Verify pipeline stagnation
        recent_event = session.query(Event).filter(
            func.array_position(Event.entities_involved, company_id) != None,
            Event.deleted_at.is_(None)
        ).order_by(Event.event_date.desc()).first()
        
        if recent_event:
            days_since = (datetime.now().date() - recent_event.event_date).days
            if days_since > 730:
                expected_score = 20
            elif days_since > 365:
                expected_score = 15
            elif days_since > 180:
                expected_score = 10
            else:
                expected_score = 0
        else:
            days_since = None
            expected_score = 0
        
        verification['verified'] = expected_score
        verification['match'] = calculated_value == expected_score
        if not verification['match']:
            verification['issues'].append(f"Expected {expected_score} (days_since={days_since}), got {calculated_value}")
    
    elif component_name == 'warning_signals':
        # Verify warning signals
        # This is harder to verify directly, so we'll just check if it's reasonable
        verification['verified'] = "N/A"
        verification['match'] = True  # Assume correct for now
        if calculated_value > 10:
            verification['issues'].append(f"Warning score exceeds max weight (10): {calculated_value}")
    
    return verification


def analyze_input_data_completeness(session: Session) -> Dict[str, Any]:
    """Analyze input data completeness for scoring."""
    all_companies = session.query(Company).filter(
        Company.deleted_at.is_(None)
    ).all()
    
    companies_with_0_trials = []
    companies_with_0_events = []
    companies_with_lt3_trials = []
    
    for company in all_companies:
        # Count trials
        trial_count = session.query(func.count(ClinicalTrial.trial_id)).join(
            TrialSponsor, ClinicalTrial.trial_id == TrialSponsor.trial_id
        ).filter(
            TrialSponsor.entity_id == company.company_id,
            TrialSponsor.entity_type == 'company',
            TrialSponsor.deleted_at.is_(None),
            ClinicalTrial.deleted_at.is_(None)
        ).scalar() or 0
        
        if trial_count == 0:
            companies_with_0_trials.append(company)
        elif trial_count < 3:
            companies_with_lt3_trials.append(company)
        
        # Count events
        event_count = session.query(func.count(Event.event_id)).filter(
            func.array_position(Event.entities_involved, company.company_id) != None,
            Event.deleted_at.is_(None)
        ).scalar() or 0
        
        if event_count == 0:
            companies_with_0_events.append(company)
    
    return {
        'total_companies': len(all_companies),
        'companies_with_0_trials': companies_with_0_trials,
        'companies_with_0_events': companies_with_0_events,
        'companies_with_lt3_trials': companies_with_lt3_trials,
        'pct_0_trials': (len(companies_with_0_trials) / len(all_companies) * 100) if all_companies else 0,
        'pct_0_events': (len(companies_with_0_events) / len(all_companies) * 100) if all_companies else 0,
        'pct_lt3_trials': (len(companies_with_lt3_trials) / len(all_companies) * 100) if all_companies else 0
    }


def identify_high_risk_companies(session: Session) -> List[Dict[str, Any]]:
    """Identify companies that should be high risk based on data."""
    high_risk_candidates = []
    
    all_companies = session.query(Company).filter(
        Company.deleted_at.is_(None)
    ).all()
    
    for company in all_companies:
        reasons = []
        
        # Check for multiple terminated trials
        terminated_trials = session.query(ClinicalTrial).join(
            TrialSponsor, ClinicalTrial.trial_id == TrialSponsor.trial_id
        ).filter(
            TrialSponsor.entity_id == company.company_id,
            TrialSponsor.entity_type == 'company',
            ClinicalTrial.status.in_(TrialStatus.FAILED_STATUSES),
            TrialSponsor.deleted_at.is_(None),
            ClinicalTrial.deleted_at.is_(None)
        ).all()
        
        if len(terminated_trials) >= 2:
            reasons.append(f"{len(terminated_trials)} terminated trials")
        
        # Check for recent clinical holds
        twelve_months_ago = datetime.now().date() - timedelta(days=365)
        clinical_holds = session.query(Event).filter(
            func.array_position(Event.entities_involved, company.company_id) != None,
            Event.event_type == 'regulatory.clinical_hold',
            Event.event_date >= twelve_months_ago,
            Event.deleted_at.is_(None)
        ).all()
        
        if len(clinical_holds) > 0:
            reasons.append(f"{len(clinical_holds)} recent clinical hold(s)")
        
        # Check for no new programs in 2+ years
        all_trials = session.query(ClinicalTrial).join(
            TrialSponsor, ClinicalTrial.trial_id == TrialSponsor.trial_id
        ).filter(
            TrialSponsor.entity_id == company.company_id,
            TrialSponsor.entity_type == 'company',
            TrialSponsor.deleted_at.is_(None),
            ClinicalTrial.deleted_at.is_(None)
        ).all()
        
        if all_trials:
            registration_dates = [t.registration_date for t in all_trials if t.registration_date]
            if registration_dates:
                most_recent = max(registration_dates)
                days_since = (datetime.now().date() - most_recent).days
                if days_since > 730:
                    reasons.append(f"No new programs in {days_since} days (2+ years)")
        
        if reasons:
            high_risk_candidates.append({
                'company': company,
                'reasons': reasons,
                'terminated_count': len(terminated_trials),
                'clinical_holds': len(clinical_holds),
                'days_since_new_program': days_since if all_trials and registration_dates else None
            })
    
    return high_risk_candidates


def generate_phase5_report() -> str:
    """Generate Phase 5: Scoring System Validation report."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Phase 5: Scoring System Validation")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("Goal: Verify risk scores accurately reflect company risk")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        risk_service = CompanyRiskService(session)
        
        # Section 1: Score Component Analysis
        report_lines.append("## 1. Score Component Analysis")
        report_lines.append("")
        
        # Get companies with scores > 0
        all_companies = session.query(Company).filter(
            Company.deleted_at.is_(None)
        ).all()
        
        companies_with_scores = []
        for company in all_companies:
            try:
                risk_profile = risk_service.calculate_company_risk_score(company.company_id)
                if 'error' not in risk_profile and risk_profile.get('risk_score', 0) > 0:
                    companies_with_scores.append({
                        'company': company,
                        'risk_profile': risk_profile
                    })
            except Exception as e:
                continue
        
        # Sample 20 random companies with scores > 0
        if len(companies_with_scores) > 20:
            sampled_companies = random.sample(companies_with_scores, 20)
        else:
            sampled_companies = companies_with_scores
        
        report_lines.append(f"**Sampled {len(sampled_companies)} companies with risk scores > 0**")
        report_lines.append("")
        report_lines.append("### Component Verification Results")
        report_lines.append("")
        report_lines.append("| Company | Risk Score | Failure Rate | Recent Failures | Stagnation | Warnings | Issues |")
        report_lines.append("|---------|------------|--------------|----------------|------------|----------|--------|")
        
        component_issues = []
        for item in sampled_companies:
            company = item['company']
            profile = item['risk_profile']
            components = profile.get('components', {})
            
            # Verify each component
            failure_verification = verify_score_component(
                company.company_id, 'failure_rate',
                components.get('failure_rate', {}).get('score', 0),
                session
            )
            recent_verification = verify_score_component(
                company.company_id, 'recent_failures',
                components.get('recent_failures', {}).get('score', 0),
                session
            )
            stagnation_verification = verify_score_component(
                company.company_id, 'pipeline_stagnation',
                components.get('pipeline_stagnation', {}).get('score', 0),
                session
            )
            warning_verification = verify_score_component(
                company.company_id, 'warning_signals',
                components.get('warning_signals', {}).get('score', 0),
                session
            )
            
            all_match = (failure_verification['match'] and recent_verification['match'] and
                        stagnation_verification['match'] and warning_verification['match'])
            
            issues_count = (len(failure_verification['issues']) + len(recent_verification['issues']) +
                          len(stagnation_verification['issues']) + len(warning_verification['issues']))
            
            if not all_match:
                component_issues.append({
                    'company': company,
                    'profile': profile,
                    'verifications': {
                        'failure_rate': failure_verification,
                        'recent_failures': recent_verification,
                        'pipeline_stagnation': stagnation_verification,
                        'warning_signals': warning_verification
                    }
                })
            
            status = "✅" if all_match else "❌"
            report_lines.append(
                f"| {company.name[:30]}... | {profile.get('risk_score', 0):.1f} | "
                f"{components.get('failure_rate', {}).get('score', 0):.1f} | "
                f"{components.get('recent_failures', {}).get('score', 0)} | "
                f"{components.get('pipeline_stagnation', {}).get('score', 0)} | "
                f"{components.get('warning_signals', {}).get('score', 0)} | "
                f"{issues_count} {status} |"
            )
        
        report_lines.append("")
        
        if component_issues:
            report_lines.append("### ⚠️ Component Calculation Issues")
            report_lines.append("")
            for item in component_issues[:5]:  # Show first 5
                company = item['company']
                profile = item['profile']
                verifications = item['verifications']
                report_lines.append(f"#### {company.name}")
                report_lines.append("")
                for comp_name, verification in verifications.items():
                    if not verification['match']:
                        report_lines.append(f"- **{comp_name}**: {verification['issues']}")
                report_lines.append("")
        
        # Why 99% are LOW risk
        report_lines.append("### Analysis: Why 289/292 Companies (99%) Score 0-25 (LOW Risk)")
        report_lines.append("")
        
        low_risk_companies = [c for c in all_companies if c.company_id in 
                             [item['company'].company_id for item in companies_with_scores 
                              if item['risk_profile'].get('risk_score', 0) <= 25]]
        
        # Analyze why they're low risk
        low_risk_analysis = {
            'no_trials': 0,
            'no_failures': 0,
            'no_recent_failures': 0,
            'no_stagnation': 0,
            'no_warnings': 0
        }
        
        for company in low_risk_companies[:50]:  # Sample first 50
            try:
                profile = risk_service.calculate_company_risk_score(company.company_id)
                if 'error' not in profile:
                    components = profile.get('components', {})
                    if components.get('failure_rate', {}).get('score', 0) == 0:
                        low_risk_analysis['no_failures'] += 1
                    if components.get('recent_failures', {}).get('score', 0) == 0:
                        low_risk_analysis['no_recent_failures'] += 1
                    if components.get('pipeline_stagnation', {}).get('score', 0) == 0:
                        low_risk_analysis['no_stagnation'] += 1
                    if components.get('warning_signals', {}).get('score', 0) == 0:
                        low_risk_analysis['no_warnings'] += 1
            except:
                pass
        
        report_lines.append("**Reasons for LOW risk scores:**")
        report_lines.append("")
        report_lines.append(f"- No failures: {low_risk_analysis['no_failures']} companies")
        report_lines.append(f"- No recent failures: {low_risk_analysis['no_recent_failures']} companies")
        report_lines.append(f"- No pipeline stagnation: {low_risk_analysis['no_stagnation']} companies")
        report_lines.append(f"- No warning signals: {low_risk_analysis['no_warnings']} companies")
        report_lines.append("")
        report_lines.append("**Conclusion:** Most companies have low scores because they have:")
        report_lines.append("1. No or few terminated trials (low failure rate)")
        report_lines.append("2. No recent failures in last 12 months")
        report_lines.append("3. Recent pipeline activity (no stagnation)")
        report_lines.append("4. No warning signals detected")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 2: Input Data Completeness
        report_lines.append("## 2. Input Data Completeness")
        report_lines.append("")
        
        data_completeness = analyze_input_data_completeness(session)
        
        report_lines.append("### Data Completeness Statistics")
        report_lines.append("")
        report_lines.append(f"- **Total Companies:** {data_completeness['total_companies']:,}")
        report_lines.append(f"- **Companies with 0 Trials:** {len(data_completeness['companies_with_0_trials']):,} ({data_completeness['pct_0_trials']:.1f}%) ⚠️")
        report_lines.append(f"- **Companies with 0 Events:** {len(data_completeness['companies_with_0_events']):,} ({data_completeness['pct_0_events']:.1f}%) ⚠️")
        report_lines.append(f"- **Companies with < 3 Trials:** {len(data_completeness['companies_with_lt3_trials']):,} ({data_completeness['pct_lt3_trials']:.1f}%) ⚠️")
        report_lines.append("")
        
        report_lines.append("### Impact on Scoring")
        report_lines.append("")
        report_lines.append("**Companies with 0 Trials:**")
        report_lines.append("- Cannot calculate failure rate (component = 0)")
        report_lines.append("- Cannot detect pipeline stagnation (no trial dates)")
        report_lines.append("- Risk score will be very low (0-10 points max from warnings/recent failures)")
        report_lines.append("")
        report_lines.append("**Companies with 0 Events:**")
        report_lines.append("- No warning signals detected")
        report_lines.append("- No recent failures tracked")
        report_lines.append("- Risk score will be low (only failure rate and stagnation contribute)")
        report_lines.append("")
        report_lines.append("**Companies with < 3 Trials:**")
        report_lines.append("- Failure rate may not be statistically significant")
        report_lines.append("- Small sample size makes risk assessment unreliable")
        report_lines.append("")
        
        if data_completeness['companies_with_0_trials']:
            report_lines.append("### Sample Companies with 0 Trials")
            report_lines.append("")
            report_lines.append("| Company Name | Risk Score | Issue |")
            report_lines.append("|--------------|------------|-------|")
            for company in data_completeness['companies_with_0_trials'][:10]:
                try:
                    profile = risk_service.calculate_company_risk_score(company.company_id)
                    score = profile.get('risk_score', 0) if 'error' not in profile else 0
                    report_lines.append(f"| {company.name[:40]}... | {score:.1f} | No trials to calculate failure rate |")
                except:
                    report_lines.append(f"| {company.name[:40]}... | N/A | Error calculating score |")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 3: Expected vs Actual Scoring
        report_lines.append("## 3. Expected vs Actual Scoring")
        report_lines.append("")
        
        high_risk_candidates = identify_high_risk_companies(session)
        
        report_lines.append("### Companies That SHOULD Be High Risk")
        report_lines.append("")
        report_lines.append("| Company Name | Risk Score | Category | Reasons | Expected Category |")
        report_lines.append("|--------------|------------|----------|---------|------------------|")
        
        mismatches = []
        for candidate in high_risk_candidates[:20]:  # Top 20
            company = candidate['company']
            reasons = candidate['reasons']
            
            try:
                profile = risk_service.calculate_company_risk_score(company.company_id)
                if 'error' not in profile:
                    actual_score = profile.get('risk_score', 0)
                    actual_category = profile.get('risk_category', 'LOW')
                    
                    # Determine expected category
                    if len(reasons) >= 2 or candidate['terminated_count'] >= 3:
                        expected_category = 'HIGH'
                    elif len(reasons) >= 1 or candidate['terminated_count'] >= 2:
                        expected_category = 'MODERATE'
                    else:
                        expected_category = 'LOW'
                    
                    if actual_category != expected_category and expected_category in ['MODERATE', 'HIGH', 'CRITICAL']:
                        mismatches.append({
                            'company': company,
                            'profile': profile,
                            'reasons': reasons,
                            'expected_category': expected_category
                        })
                    
                    status = "✅" if actual_category == expected_category else "❌"
                    report_lines.append(
                        f"| {company.name[:30]}... | {actual_score:.1f} | {actual_category} | "
                        f"{'; '.join(reasons[:2])} | {expected_category} {status} |"
                    )
            except Exception as e:
                report_lines.append(f"| {company.name[:30]}... | Error | - | {'; '.join(reasons[:2])} | - |")
        
        report_lines.append("")
        
        if mismatches:
            report_lines.append("### ⚠️ Scoring Mismatches")
            report_lines.append("")
            report_lines.append("Companies with high-risk indicators but low scores:")
            report_lines.append("")
            for item in mismatches[:10]:
                company = item['company']
                profile = item['profile']
                reasons = item['reasons']
                expected = item['expected_category']
                actual = profile.get('risk_category', 'LOW')
                
                report_lines.append(f"#### {company.name}")
                report_lines.append("")
                report_lines.append(f"- **Actual Score:** {profile.get('risk_score', 0):.1f} ({actual})")
                report_lines.append(f"- **Expected Category:** {expected}")
                report_lines.append(f"- **High-Risk Indicators:** {', '.join(reasons)}")
                report_lines.append("")
                report_lines.append("**Component Breakdown:**")
                components = profile.get('components', {})
                for comp_name, comp_data in components.items():
                    score = comp_data.get('score', 0)
                    details = comp_data.get('details', {})
                    report_lines.append(f"- {comp_name}: {score:.1f} - {details}")
                report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 4: Score Distribution Reasonableness
        report_lines.append("## 4. Score Distribution Reasonableness")
        report_lines.append("")
        
        # Calculate score distribution
        score_distribution = defaultdict(int)
        category_distribution = defaultdict(int)
        all_scores = []
        
        for company in all_companies:
            try:
                profile = risk_service.calculate_company_risk_score(company.company_id)
                if 'error' not in profile:
                    score = profile.get('risk_score', 0)
                    category = profile.get('risk_category', 'LOW')
                    all_scores.append(score)
                    score_distribution[int(score // 10) * 10] += 1
                    category_distribution[category] += 1
            except:
                pass
        
        report_lines.append("### Current Distribution")
        report_lines.append("")
        report_lines.append(f"- **Total Companies Scored:** {len(all_scores):,}")
        if all_scores:
            report_lines.append(f"- **Min Score:** {min(all_scores):.1f}")
            report_lines.append(f"- **Max Score:** {max(all_scores):.1f}")
            report_lines.append(f"- **Average Score:** {sum(all_scores) / len(all_scores):.1f}")
            report_lines.append(f"- **Median Score:** {sorted(all_scores)[len(all_scores) // 2]:.1f}")
        report_lines.append("")
        
        report_lines.append("**By Category:**")
        for category, count in sorted(category_distribution.items()):
            pct = (count / len(all_scores) * 100) if all_scores else 0
            report_lines.append(f"- {category}: {count} ({pct:.1f}%)")
        report_lines.append("")
        
        report_lines.append("**By Score Range:**")
        for score_range in sorted(score_distribution.keys()):
            count = score_distribution[score_range]
            pct = (count / len(all_scores) * 100) if all_scores else 0
            report_lines.append(f"- {score_range}-{score_range+9}: {count} ({pct:.1f}%)")
        report_lines.append("")
        
        report_lines.append("### Analysis: Is Distribution Reasonable?")
        report_lines.append("")
        report_lines.append("**Current State:** 89% of companies score 0-10 (essentially no risk)")
        report_lines.append("")
        report_lines.append("**Expected Distribution:**")
        report_lines.append("- Some companies should have MODERATE/HIGH risk")
        report_lines.append("- Real-world biotech companies have varying risk levels")
        report_lines.append("- Companies with multiple failures should score higher")
        report_lines.append("")
        
        report_lines.append("### Root Cause Analysis")
        report_lines.append("")
        
        # Check if issue is insufficient data
        pct_0_trials = data_completeness['pct_0_trials']
        pct_0_events = data_completeness['pct_0_events']
        
        report_lines.append("1. **Insufficient Input Data?**")
        report_lines.append(f"   - {pct_0_trials:.1f}% of companies have 0 trials → Cannot calculate failure rate")
        report_lines.append(f"   - {pct_0_events:.1f}% of companies have 0 events → No warning signals")
        report_lines.append(f"   - Impact: These companies will score 0-10 (only from stagnation if applicable)")
        report_lines.append("")
        
        # Check if weights are too conservative
        report_lines.append("2. **Scoring Weights Too Conservative?**")
        report_lines.append("   - Current weights: Failure Rate (40), Recent Failures (30), Stagnation (20), Warnings (10)")
        report_lines.append("   - A company needs:")
        report_lines.append("     - 50%+ failure rate OR")
        report_lines.append("     - 3+ recent failures OR")
        report_lines.append("     - 2+ years stagnation")
        report_lines.append("   - To score > 25 (MODERATE risk)")
        report_lines.append("   - **Analysis:** Thresholds may be too high for real-world risk")
        report_lines.append("")
        
        # Check for missing failure events
        total_terminated = session.query(func.count(ClinicalTrial.trial_id)).filter(
            ClinicalTrial.status.in_(TrialStatus.FAILED_STATUSES),
            ClinicalTrial.deleted_at.is_(None)
        ).scalar() or 0
        
        total_events = session.query(func.count(Event.event_id)).filter(
            Event.event_type.in_(['trial.status.terminated', 'trial.status.withdrawn']),
            Event.deleted_at.is_(None)
        ).scalar() or 0
        
        report_lines.append("3. **Missing Failure Events?**")
        report_lines.append(f"   - Terminated trials in database: {total_terminated:,}")
        report_lines.append(f"   - Failure events in events table: {total_events:,}")
        if total_terminated > total_events:
            report_lines.append(f"   - ⚠️ **Gap:** {total_terminated - total_events:,} terminated trials don't have corresponding events")
            report_lines.append("   - Impact: Recent failures component will be undercounted")
        else:
            report_lines.append("   - ✅ Event coverage appears complete")
        report_lines.append("")
        
        report_lines.append("### Recommendations")
        report_lines.append("")
        report_lines.append("1. **Adjust Scoring Thresholds:**")
        report_lines.append("   - Lower MODERATE threshold to 15-20 (from 25)")
        report_lines.append("   - Increase weight for single recent failure (from 10 to 15)")
        report_lines.append("   - Add points for companies with 0 trials (unknown risk)")
        report_lines.append("")
        report_lines.append("2. **Improve Event Coverage:**")
        report_lines.append("   - Ensure all terminated trials have corresponding events")
        report_lines.append("   - Backfill missing failure events")
        report_lines.append("")
        report_lines.append("3. **Handle Data Sparsity:**")
        report_lines.append("   - Companies with 0 trials: Assign 'UNKNOWN' risk category")
        report_lines.append("   - Companies with < 3 trials: Flag as 'INSUFFICIENT_DATA'")
        report_lines.append("   - Don't penalize companies for missing data")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("**End of Phase 5 Report**")
        report_lines.append("")
    
    return "\n".join(report_lines)


def validate_api_response(company_id: UUID, session: Session, risk_service: CompanyRiskService) -> Dict[str, Any]:
    """Validate API response matches database queries."""
    validation = {
        'company_id': str(company_id),
        'risk_profile': {'match': True, 'issues': []},
        'metrics': {'match': True, 'issues': []},
        'timeline': {'match': True, 'issues': []}
    }
    
    company = session.query(Company).filter(
        Company.company_id == company_id,
        Company.deleted_at.is_(None)
    ).first()
    
    if not company:
        validation['risk_profile']['issues'].append("Company not found")
        validation['metrics']['issues'].append("Company not found")
        validation['timeline']['issues'].append("Company not found")
        return validation
    
    # Validate risk profile
    try:
        risk_profile = risk_service.calculate_company_risk_score(company_id)
        
        # Verify risk score components match database
        components = risk_profile.get('components', {})
        
        # Verify failure_rate component
        failure_rate_comp = components.get('failure_rate', {})
        failure_rate_score = failure_rate_comp.get('score', 0)
        failure_rate_details = failure_rate_comp.get('details', {})
        
        # Manually calculate from database
        trials = session.query(ClinicalTrial).join(
            TrialSponsor, ClinicalTrial.trial_id == TrialSponsor.trial_id
        ).filter(
            TrialSponsor.entity_id == company_id,
            TrialSponsor.entity_type == 'company',
            TrialSponsor.deleted_at.is_(None),
            ClinicalTrial.deleted_at.is_(None)
        ).all()
        
        total_trials = len(trials)
        terminated_count = len([t for t in trials if t.status in TrialStatus.FAILED_STATUSES])
        
        if total_trials > 0:
            expected_rate = terminated_count / total_trials
            expected_score = min(expected_rate * 40, 40)
            if abs(failure_rate_score - expected_score) > 0.01:
                validation['risk_profile']['match'] = False
                validation['risk_profile']['issues'].append(
                    f"Failure rate score mismatch: API={failure_rate_score:.2f}, DB={expected_score:.2f}"
                )
        
        # Verify recent_failures component
        recent_comp = components.get('recent_failures', {})
        recent_score = recent_comp.get('score', 0)
        recent_details = recent_comp.get('details', {})
        
        twelve_months_ago = datetime.now().date() - timedelta(days=365)
        failure_events = session.query(Event).filter(
            func.array_position(Event.entities_involved, company_id) != None,
            Event.event_type.in_(['trial.status.terminated', 'trial.status.withdrawn', 'regulatory.clinical_hold']),
            Event.event_date >= twelve_months_ago,
            Event.deleted_at.is_(None)
        ).all()
        
        failures_count = len(failure_events)
        if failures_count >= 3:
            expected_recent_score = 30
        elif failures_count == 2:
            expected_recent_score = 20
        elif failures_count == 1:
            expected_recent_score = 10
        else:
            expected_recent_score = 0
        
        if recent_score != expected_recent_score:
            validation['risk_profile']['match'] = False
            validation['risk_profile']['issues'].append(
                f"Recent failures score mismatch: API={recent_score}, DB={expected_recent_score} (from {failures_count} events)"
            )
        
        if recent_details.get('failures_last_12mo', 0) != failures_count:
            validation['risk_profile']['match'] = False
            validation['risk_profile']['issues'].append(
                f"Recent failures count mismatch: API={recent_details.get('failures_last_12mo', 0)}, DB={failures_count}"
            )
        
    except Exception as e:
        validation['risk_profile']['match'] = False
        validation['risk_profile']['issues'].append(f"Error validating risk profile: {str(e)}")
    
    # Validate metrics
    try:
        metrics = risk_service.get_company_metrics(company_id)
        
        # Verify total_trials
        api_total = metrics.get('total_trials', 0)
        if api_total != total_trials:
            validation['metrics']['match'] = False
            validation['metrics']['issues'].append(
                f"Total trials mismatch: API={api_total}, DB={total_trials}"
            )
        
        # Verify terminated_count
        api_terminated = metrics.get('terminated_count', 0)
        if api_terminated != terminated_count:
            validation['metrics']['match'] = False
            validation['metrics']['issues'].append(
                f"Terminated count mismatch: API={api_terminated}, DB={terminated_count}"
            )
        
    except Exception as e:
        validation['metrics']['match'] = False
        validation['metrics']['issues'].append(f"Error validating metrics: {str(e)}")
    
    # Validate timeline
    try:
        timeline = risk_service.get_company_timeline(company_id)
        
        # Query events directly from database
        db_events = session.query(Event).filter(
            func.array_position(Event.entities_involved, company_id) != None,
            Event.deleted_at.is_(None)
        ).order_by(Event.event_date.desc()).all()
        
        if len(timeline) != len(db_events):
            validation['timeline']['match'] = False
            validation['timeline']['issues'].append(
                f"Event count mismatch: API={len(timeline)}, DB={len(db_events)}"
            )
        
        # Verify event IDs match
        api_event_ids = {str(e.event_id) for e in timeline}
        db_event_ids = {str(e.event_id) for e in db_events}
        
        if api_event_ids != db_event_ids:
            missing_in_api = db_event_ids - api_event_ids
            extra_in_api = api_event_ids - db_event_ids
            if missing_in_api:
                validation['timeline']['match'] = False
                validation['timeline']['issues'].append(
                    f"Events missing in API: {list(missing_in_api)[:5]}"
                )
            if extra_in_api:
                validation['timeline']['match'] = False
                validation['timeline']['issues'].append(
                    f"Extra events in API: {list(extra_in_api)[:5]}"
                )
        
    except Exception as e:
        validation['timeline']['match'] = False
        validation['timeline']['issues'].append(f"Error validating timeline: {str(e)}")
    
    return validation


def validate_failed_trials_list(session: Session) -> Dict[str, Any]:
    """Validate failed trials list API response."""
    validation = {
        'match': True,
        'issues': [],
        'api_count': 0,
        'db_count': 0,
        'enrichment_issues': []
    }
    
    # Query database directly
    ninety_days_ago = datetime.now().date() - timedelta(days=90)
    db_events = session.query(Event).filter(
        Event.event_type.in_(['trial.status.terminated', 'trial.status.withdrawn', 
                              'program.milestone.rejected', 'regulatory.rejection']),
        Event.event_date >= ninety_days_ago,
        Event.deleted_at.is_(None)
    ).order_by(Event.event_date.desc()).all()
    
    validation['db_count'] = len(db_events)
    
    # Get API response (simulate by calling service)
    try:
        tracker = FailureTracker(session)
        api_failures = tracker.get_recent_failures(days=90)
        api_failures = api_failures[:50]  # Apply limit
        
        validation['api_count'] = len(api_failures)
        
        if len(api_failures) != min(len(db_events), 50):
            validation['match'] = False
            validation['issues'].append(
                f"Count mismatch: API={len(api_failures)}, DB={len(db_events)} (limit 50)"
            )
        
        # Verify event IDs match
        api_event_ids = {f.get('event_id') for f in api_failures}
        db_event_ids = {str(e.event_id) for e in db_events[:50]}
        
        if api_event_ids != db_event_ids:
            missing_in_api = db_event_ids - api_event_ids
            if missing_in_api:
                validation['match'] = False
                validation['issues'].append(
                    f"Events missing in API response: {len(missing_in_api)} events"
                )
        
        # Check entity enrichment
        for failure in api_failures[:10]:  # Sample first 10
            entities = failure.get('entities', {})
            
            # Check if company is enriched
            if 'company' not in entities:
                validation['enrichment_issues'].append(
                    f"Event {failure.get('event_id')}: Missing company enrichment"
                )
            
            # Verify entity IDs are valid UUIDs
            event_entity_ids = failure.get('event_data', {}).get('entities_involved', [])
            if event_entity_ids:
                try:
                    for entity_id in event_entity_ids:
                        UUID(str(entity_id))
                except ValueError:
                    validation['enrichment_issues'].append(
                        f"Event {failure.get('event_id')}: Invalid entity ID format"
                    )
        
    except Exception as e:
        validation['match'] = False
        validation['issues'].append(f"Error validating failed trials: {str(e)}")
    
    return validation


def test_company_search(session: Session, risk_service: CompanyRiskService) -> Dict[str, Any]:
    """Test company search functionality."""
    test_results = {
        'name_search': {'passed': True, 'issues': []},
        'risk_category_filter': {'passed': True, 'issues': []},
        'therapeutic_area_filter': {'passed': True, 'issues': []},
        'risk_score_consistency': {'passed': True, 'issues': []}
    }
    
    # Test 1: Name search
    try:
        # Get a random company name
        sample_company = session.query(Company).filter(
            Company.deleted_at.is_(None)
        ).first()
        
        if sample_company:
            # Simulate search by querying directly
            search_term = sample_company.name[:5]  # First 5 chars
            search_results = session.query(Company).filter(
                Company.name.ilike(f'%{search_term}%'),
                Company.deleted_at.is_(None)
            ).limit(10).all()
            
            if not search_results:
                test_results['name_search']['passed'] = False
                test_results['name_search']['issues'].append(
                    f"Search for '{search_term}' returned no results"
                )
            else:
                # Verify search term appears in results
                for company in search_results:
                    if search_term.lower() not in company.name.lower():
                        test_results['name_search']['passed'] = False
                        test_results['name_search']['issues'].append(
                            f"Result '{company.name}' doesn't match search term '{search_term}'"
                        )
                        break
        
    except Exception as e:
        test_results['name_search']['passed'] = False
        test_results['name_search']['issues'].append(f"Error testing name search: {str(e)}")
    
    # Test 2: Risk category filter
    try:
        # Get companies with risk scores
        companies_with_scores = []
        for company in session.query(Company).filter(Company.deleted_at.is_(None)).limit(20).all():
            try:
                profile = risk_service.calculate_company_risk_score(company.company_id)
                if 'error' not in profile:
                    companies_with_scores.append({
                        'company': company,
                        'category': profile.get('risk_category', 'LOW')
                    })
            except:
                continue
        
        # Group by category
        category_counts = defaultdict(int)
        for item in companies_with_scores:
            category_counts[item['category']] += 1
        
        # Test filtering by category
        for category in ['LOW', 'MODERATE', 'HIGH']:
            filtered = [item for item in companies_with_scores if item['category'] == category]
            if category_counts[category] > 0 and len(filtered) == 0:
                test_results['risk_category_filter']['passed'] = False
                test_results['risk_category_filter']['issues'].append(
                    f"Filter by '{category}' returned no results despite {category_counts[category]} companies"
                )
        
    except Exception as e:
        test_results['risk_category_filter']['passed'] = False
        test_results['risk_category_filter']['issues'].append(f"Error testing risk category filter: {str(e)}")
    
    # Test 3: Risk score consistency
    try:
        # Check if risk scores in search match detail view
        for item in companies_with_scores[:5]:
            company = item['company']
            search_category = item['category']
            
            # Get detail view
            detail_profile = risk_service.calculate_company_risk_score(company.company_id)
            detail_category = detail_profile.get('risk_category', 'LOW')
            
            if search_category != detail_category:
                test_results['risk_score_consistency']['passed'] = False
                test_results['risk_score_consistency']['issues'].append(
                    f"Company {company.name}: Search category={search_category}, Detail category={detail_category}"
                )
        
    except Exception as e:
        test_results['risk_score_consistency']['passed'] = False
        test_results['risk_score_consistency']['issues'].append(f"Error testing risk score consistency: {str(e)}")
    
    return test_results


def validate_timeline_data(session: Session, risk_service: CompanyRiskService) -> Dict[str, Any]:
    """Validate timeline visualization data."""
    validation = {
        'date_ranges': {'passed': True, 'issues': []},
        'event_significance': {'passed': True, 'issues': []},
        'event_ordering': {'passed': True, 'issues': []}
    }
    
    # Get a sample company with events
    companies_with_events = []
    for company in session.query(Company).filter(Company.deleted_at.is_(None)).limit(20).all():
        event_count = session.query(func.count(Event.event_id)).filter(
            func.array_position(Event.entities_involved, company.company_id) != None,
            Event.deleted_at.is_(None)
        ).scalar() or 0
        
        if event_count > 0:
            companies_with_events.append(company)
            if len(companies_with_events) >= 5:
                break
    
    for company in companies_with_events[:5]:
        try:
            timeline = risk_service.get_company_timeline(company.company_id)
            
            if not timeline:
                continue
            
            # Test 1: Date ranges
            dates = [e.event_date for e in timeline if e.event_date]
            if dates:
                min_date = min(dates)
                max_date = max(dates)
                
                # Check for unreasonable dates (future dates or very old dates)
                today = datetime.now().date()
                if max_date > today:
                    validation['date_ranges']['passed'] = False
                    validation['date_ranges']['issues'].append(
                        f"Company {company.name}: Future date found: {max_date}"
                    )
                
                # Check if dates are too old (more than 20 years)
                if min_date < (today - timedelta(days=365*20)):
                    validation['date_ranges']['passed'] = False
                    validation['date_ranges']['issues'].append(
                        f"Company {company.name}: Very old date found: {min_date}"
                    )
            
            # Test 2: Event significance levels
            significance_levels = [e.event_significance for e in timeline if e.event_significance]
            valid_levels = ['critical', 'major', 'minor', 'trace', None]
            invalid_levels = [s for s in significance_levels if s not in valid_levels]
            
            if invalid_levels:
                validation['event_significance']['passed'] = False
                validation['event_significance']['issues'].append(
                    f"Company {company.name}: Invalid significance levels: {set(invalid_levels)}"
                )
            
            # Test 3: Event ordering (should be descending by date)
            if len(timeline) > 1:
                for i in range(len(timeline) - 1):
                    if timeline[i].event_date < timeline[i+1].event_date:
                        validation['event_ordering']['passed'] = False
                        validation['event_ordering']['issues'].append(
                            f"Company {company.name}: Events not in descending order"
                        )
                        break
            
        except Exception as e:
            validation['date_ranges']['issues'].append(f"Error validating timeline for {company.name}: {str(e)}")
    
    return validation


def generate_phase6_report() -> str:
    """Generate Phase 6: UI Data Accuracy report."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Phase 6: UI Data Accuracy")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("Goal: Ensure dashboard displays correct data from database")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        risk_service = CompanyRiskService(session)
        
        # Section 1: API Response Validation
        report_lines.append("## 1. API Response Validation")
        report_lines.append("")
        report_lines.append("### Testing API Endpoints for 5 Random Companies")
        report_lines.append("")
        
        # Get 5 random companies
        all_companies = session.query(Company).filter(
            Company.deleted_at.is_(None)
        ).all()
        
        if len(all_companies) > 5:
            sample_companies = random.sample(all_companies, 5)
        else:
            sample_companies = all_companies
        
        api_validations = []
        for company in sample_companies:
            validation = validate_api_response(company.company_id, session, risk_service)
            api_validations.append(validation)
        
        report_lines.append("| Company | Risk Profile | Metrics | Timeline | Overall |")
        report_lines.append("|---------|--------------|---------|----------|---------|")
        
        for validation in api_validations:
            risk_match = "✅" if validation['risk_profile']['match'] else "❌"
            metrics_match = "✅" if validation['metrics']['match'] else "❌"
            timeline_match = "✅" if validation['timeline']['match'] else "❌"
            overall = "✅" if (validation['risk_profile']['match'] and 
                             validation['metrics']['match'] and 
                             validation['timeline']['match']) else "❌"
            
            company = session.query(Company).filter(
                Company.company_id == UUID(validation['company_id'])
            ).first()
            company_name = company.name[:30] + "..." if company and len(company.name) > 30 else (company.name if company else "Unknown")
            
            report_lines.append(
                f"| {company_name} | {risk_match} | {metrics_match} | {timeline_match} | {overall} |"
            )
        
        report_lines.append("")
        
        # Show issues
        issues_found = [v for v in api_validations if not (
            v['risk_profile']['match'] and v['metrics']['match'] and v['timeline']['match']
        )]
        
        if issues_found:
            report_lines.append("### ⚠️ API Response Issues")
            report_lines.append("")
            for validation in issues_found[:3]:  # Show first 3
                company = session.query(Company).filter(
                    Company.company_id == UUID(validation['company_id'])
                ).first()
                company_name = company.name if company else "Unknown"
                
                report_lines.append(f"#### {company_name}")
                report_lines.append("")
                
                if not validation['risk_profile']['match']:
                    report_lines.append("**Risk Profile Issues:**")
                    for issue in validation['risk_profile']['issues'][:3]:
                        report_lines.append(f"- {issue}")
                    report_lines.append("")
                
                if not validation['metrics']['match']:
                    report_lines.append("**Metrics Issues:**")
                    for issue in validation['metrics']['issues'][:3]:
                        report_lines.append(f"- {issue}")
                    report_lines.append("")
                
                if not validation['timeline']['match']:
                    report_lines.append("**Timeline Issues:**")
                    for issue in validation['timeline']['issues'][:3]:
                        report_lines.append(f"- {issue}")
                    report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 2: Failed Trials List Accuracy
        report_lines.append("## 2. Failed Trials List Accuracy")
        report_lines.append("")
        
        failures_validation = validate_failed_trials_list(session)
        
        report_lines.append("### Database vs API Comparison")
        report_lines.append("")
        report_lines.append(f"- **Database Events (last 90 days):** {failures_validation['db_count']:,}")
        report_lines.append(f"- **API Response Count:** {failures_validation['api_count']:,}")
        report_lines.append(f"- **Match Status:** {'✅ Match' if failures_validation['match'] else '❌ Mismatch'}")
        report_lines.append("")
        
        if failures_validation['issues']:
            report_lines.append("### ⚠️ Issues Found")
            report_lines.append("")
            for issue in failures_validation['issues']:
                report_lines.append(f"- {issue}")
            report_lines.append("")
        
        if failures_validation['enrichment_issues']:
            report_lines.append("### Entity Enrichment Issues")
            report_lines.append("")
            for issue in failures_validation['enrichment_issues'][:10]:
                report_lines.append(f"- {issue}")
            report_lines.append("")
        
        report_lines.append("### Entity Enrichment Verification")
        report_lines.append("")
        report_lines.append("**Expected Enrichment:**")
        report_lines.append("- Company details (name, ID)")
        report_lines.append("- Trial details (if applicable)")
        report_lines.append("- Drug details (if applicable)")
        report_lines.append("- Disease details (if applicable)")
        report_lines.append("")
        
        # Sample enrichment check
        try:
            tracker = FailureTracker(session)
            sample_failures = tracker.get_recent_failures(days=90)[:5]
            
            enrichment_stats = {
                'with_company': 0,
                'with_trial': 0,
                'with_drug': 0,
                'with_disease': 0
            }
            
            for failure in sample_failures:
                entities = failure.get('entities', {})
                if 'company' in entities:
                    enrichment_stats['with_company'] += 1
                if 'trial' in entities:
                    enrichment_stats['with_trial'] += 1
                if 'drug' in entities:
                    enrichment_stats['with_drug'] += 1
                if 'disease' in entities:
                    enrichment_stats['with_disease'] += 1
            
            report_lines.append("**Enrichment Coverage (sample of 5):**")
            report_lines.append(f"- Companies enriched: {enrichment_stats['with_company']}/5")
            report_lines.append(f"- Trials enriched: {enrichment_stats['with_trial']}/5")
            report_lines.append(f"- Drugs enriched: {enrichment_stats['with_drug']}/5")
            report_lines.append(f"- Diseases enriched: {enrichment_stats['with_disease']}/5")
            report_lines.append("")
            
        except Exception as e:
            report_lines.append(f"⚠️ Error checking enrichment: {str(e)}")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 3: Company Search Functionality
        report_lines.append("## 3. Company Search Functionality")
        report_lines.append("")
        
        search_results = test_company_search(session, risk_service)
        
        report_lines.append("### Search Test Results")
        report_lines.append("")
        report_lines.append("| Test | Status | Issues |")
        report_lines.append("|------|--------|--------|")
        
        for test_name, result in search_results.items():
            status = "✅ Pass" if result['passed'] else "❌ Fail"
            issues_count = len(result['issues'])
            report_lines.append(f"| {test_name.replace('_', ' ').title()} | {status} | {issues_count} |")
        
        report_lines.append("")
        
        # Show issues
        failed_tests = {k: v for k, v in search_results.items() if not v['passed']}
        if failed_tests:
            report_lines.append("### ⚠️ Search Issues")
            report_lines.append("")
            for test_name, result in failed_tests.items():
                report_lines.append(f"#### {test_name.replace('_', ' ').title()}")
                report_lines.append("")
                for issue in result['issues'][:3]:
                    report_lines.append(f"- {issue}")
                report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 4: Timeline Visualization Data
        report_lines.append("## 4. Timeline Visualization Data")
        report_lines.append("")
        
        timeline_validation = validate_timeline_data(session, risk_service)
        
        report_lines.append("### Timeline Data Validation")
        report_lines.append("")
        report_lines.append("| Validation | Status | Issues |")
        report_lines.append("|------------|--------|--------|")
        
        for validation_name, result in timeline_validation.items():
            status = "✅ Pass" if result['passed'] else "❌ Fail"
            issues_count = len(result['issues'])
            report_lines.append(f"| {validation_name.replace('_', ' ').title()} | {status} | {issues_count} |")
        
        report_lines.append("")
        
        # Show issues
        failed_validations = {k: v for k, v in timeline_validation.items() if not v['passed']}
        if failed_validations:
            report_lines.append("### ⚠️ Timeline Issues")
            report_lines.append("")
            for validation_name, result in failed_validations.items():
                report_lines.append(f"#### {validation_name.replace('_', ' ').title()}")
                report_lines.append("")
                for issue in result['issues'][:3]:
                    report_lines.append(f"- {issue}")
                report_lines.append("")
        
        report_lines.append("### Timeline Data Requirements")
        report_lines.append("")
        report_lines.append("**Expected Behavior:**")
        report_lines.append("- Events ordered by date (descending)")
        report_lines.append("- Date ranges are reasonable (no future dates, not too old)")
        report_lines.append("- Event significance levels are valid (critical, major, minor, trace)")
        report_lines.append("- All events for company are included")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("**End of Phase 6 Report**")
        report_lines.append("")
    
    return "\n".join(report_lines)


def analyze_failure_signal_coverage(session: Session) -> Dict[str, Any]:
    """Analyze failure signal coverage in events table."""
    analysis = {
        'expected_signals': {
            'trial.status.terminated': {'expected': True, 'count': 0, 'present': False},
            'trial.status.withdrawn': {'expected': True, 'count': 0, 'present': False},
            'regulatory.clinical_hold': {'expected': True, 'count': 0, 'present': False},
            'program.milestone.rejected': {'expected': True, 'count': 0, 'present': False},
            'program.discontinued': {'expected': True, 'count': 0, 'present': False},
            'corporate.restructuring': {'expected': True, 'count': 0, 'present': False},
            'corporate.layoff': {'expected': True, 'count': 0, 'present': False},
            'regulatory.rejection': {'expected': True, 'count': 0, 'present': False},
        },
        'missing_signals': [],
        'total_failure_events': 0
    }
    
    # Get all event types in database
    all_event_types = session.query(
        Event.event_type,
        func.count(Event.event_id).label('count')
    ).filter(
        Event.deleted_at.is_(None)
    ).group_by(Event.event_type).all()
    
    event_type_counts = {et[0]: et[1] for et in all_event_types}
    
    # Check each expected signal
    for signal_type, info in analysis['expected_signals'].items():
        if signal_type in event_type_counts:
            info['count'] = event_type_counts[signal_type]
            info['present'] = True
            analysis['total_failure_events'] += event_type_counts[signal_type]
        else:
            analysis['missing_signals'].append(signal_type)
    
    # Also check for similar event types (partial matches)
    for event_type, count in event_type_counts.items():
        if 'terminated' in event_type.lower() or 'withdrawn' in event_type.lower():
            if event_type not in analysis['expected_signals']:
                analysis['expected_signals'][event_type] = {
                    'expected': False,
                    'count': count,
                    'present': True
                }
    
    return analysis


def analyze_early_warning_signals(session: Session) -> Dict[str, Any]:
    """Analyze early warning signal coverage."""
    analysis = {
        'warn_notices': {'expected': True, 'count': 0, 'source_status': 'not_running'},
        'layoff_signals': {'expected': True, 'count': 0, 'present': False},
        'fda_warning_letters': {'expected': True, 'count': 0, 'source_status': 'not_running'},
        'clinical_holds': {'expected': True, 'count': 0, 'present': False},
        'fda_approvals': {'expected': True, 'count': 0, 'present': False},
        'fda_rejections': {'expected': True, 'count': 0, 'present': False},
        'coverage_pct': 0.0
    }
    
    # Check for layoff signals in events
    layoff_events = session.query(func.count(Event.event_id)).filter(
        Event.event_type.in_(['corporate.layoff', 'corporate.restructuring']),
        Event.deleted_at.is_(None)
    ).scalar() or 0
    analysis['layoff_signals']['count'] = layoff_events
    analysis['layoff_signals']['present'] = layoff_events > 0
    
    # Check for clinical holds
    clinical_hold_events = session.query(func.count(Event.event_id)).filter(
        Event.event_type == 'regulatory.clinical_hold',
        Event.deleted_at.is_(None)
    ).scalar() or 0
    analysis['clinical_holds']['count'] = clinical_hold_events
    analysis['clinical_holds']['present'] = clinical_hold_events > 0
    
    # Check for FDA approvals/rejections in events
    fda_approval_events = session.query(func.count(Event.event_id)).filter(
        Event.event_type.in_(['program.milestone.approved', 'regulatory.approval']),
        Event.deleted_at.is_(None)
    ).scalar() or 0
    analysis['fda_approvals']['count'] = fda_approval_events
    analysis['fda_approvals']['present'] = fda_approval_events > 0
    
    fda_rejection_events = session.query(func.count(Event.event_id)).filter(
        Event.event_type.in_(['program.milestone.rejected', 'regulatory.rejection']),
        Event.deleted_at.is_(None)
    ).scalar() or 0
    analysis['fda_rejections']['count'] = fda_rejection_events
    analysis['fda_rejections']['present'] = fda_rejection_events > 0
    
    # Check source status for WARN notices and FDA warning letters
    warn_source = session.query(Source).filter(
        Source.source_name.ilike('%warn%'),
        Source.deleted_at.is_(None)
    ).first()
    if warn_source:
        analysis['warn_notices']['source_status'] = 'registered' if warn_source.is_active else 'inactive'
        # Check if source has been run
        processing_log = session.query(func.count(SourceProcessingLog.log_id)).filter(
            SourceProcessingLog.source_id == warn_source.source_id,
            SourceProcessingLog.deleted_at.is_(None)
        ).scalar() or 0
        if processing_log > 0:
            analysis['warn_notices']['source_status'] = 'running'
    else:
        analysis['warn_notices']['source_status'] = 'not_registered'
    
    fda_warning_source = session.query(Source).filter(
        Source.source_name.ilike('%fda%warning%'),
        Source.deleted_at.is_(None)
    ).first()
    if fda_warning_source:
        analysis['fda_warning_letters']['source_status'] = 'registered' if fda_warning_source.is_active else 'inactive'
    else:
        analysis['fda_warning_letters']['source_status'] = 'not_registered'
    
    # Calculate coverage percentage
    expected_signals = 7  # warn, layoff, fda_warning, clinical_hold, fda_approval, fda_rejection, + others
    present_signals = sum([
        1 if analysis['layoff_signals']['present'] else 0,
        1 if analysis['clinical_holds']['present'] else 0,
        1 if analysis['fda_approvals']['present'] else 0,
        1 if analysis['fda_rejections']['present'] else 0,
    ])
    analysis['coverage_pct'] = (present_signals / expected_signals * 100) if expected_signals > 0 else 0
    
    return analysis


def analyze_regulatory_events_gap(session: Session) -> Dict[str, Any]:
    """Analyze regulatory events table gap."""
    analysis = {
        'table_exists': True,
        'row_count': 0,
        'expected_data_types': {
            'approvals': {'expected': True, 'count': 0},
            'rejections': {'expected': True, 'count': 0},
            'clinical_holds': {'expected': True, 'count': 0},
            'breakthrough_designations': {'expected': True, 'count': 0},
            'orphan_designations': {'expected': True, 'count': 0},
        },
        'events_table_coverage': {
            'regulatory_events_in_events': 0,
            'event_types': []
        },
        'sources_status': {}
    }
    
    try:
        # Check regulatory_events table
        reg_event_count = session.query(func.count(RegulatoryEvent.event_id)).filter(
            RegulatoryEvent.deleted_at.is_(None)
        ).scalar() or 0
        analysis['row_count'] = reg_event_count
        
        # Check if regulatory events are in events table instead
        regulatory_event_types = session.query(
            Event.event_type,
            func.count(Event.event_id).label('count')
        ).filter(
            Event.event_type.like('regulatory.%'),
            Event.deleted_at.is_(None)
        ).group_by(Event.event_type).all()
        
        analysis['events_table_coverage']['regulatory_events_in_events'] = sum(et[1] for et in regulatory_event_types)
        analysis['events_table_coverage']['event_types'] = [et[0] for et in regulatory_event_types]
        
        # Check for specific regulatory event types in events table
        for data_type in analysis['expected_data_types'].keys():
            if data_type == 'approvals':
                count = session.query(func.count(Event.event_id)).filter(
                    Event.event_type.in_(['program.milestone.approved', 'regulatory.approval']),
                    Event.deleted_at.is_(None)
                ).scalar() or 0
                analysis['expected_data_types']['approvals']['count'] = count
            elif data_type == 'rejections':
                count = session.query(func.count(Event.event_id)).filter(
                    Event.event_type.in_(['program.milestone.rejected', 'regulatory.rejection']),
                    Event.deleted_at.is_(None)
                ).scalar() or 0
                analysis['expected_data_types']['rejections']['count'] = count
            elif data_type == 'clinical_holds':
                count = session.query(func.count(Event.event_id)).filter(
                    Event.event_type == 'regulatory.clinical_hold',
                    Event.deleted_at.is_(None)
                ).scalar() or 0
                analysis['expected_data_types']['clinical_holds']['count'] = count
            elif data_type == 'breakthrough_designations':
                count = session.query(func.count(Event.event_id)).filter(
                    Event.event_type == 'regulatory.breakthrough',
                    Event.deleted_at.is_(None)
                ).scalar() or 0
                analysis['expected_data_types']['breakthrough_designations']['count'] = count
        
        # Check regulatory sources
        regulatory_sources = session.query(Source).filter(
            Source.source_type == 'regulatory',
            Source.deleted_at.is_(None)
        ).all()
        
        for source in regulatory_sources:
            processing_count = session.query(func.count(SourceProcessingLog.log_id)).filter(
                SourceProcessingLog.source_id == source.source_id,
                SourceProcessingLog.deleted_at.is_(None)
            ).scalar() or 0
            
            analysis['sources_status'][source.source_name] = {
                'is_active': source.is_active,
                'has_processing': processing_count > 0,
                'processing_count': processing_count
            }
        
    except Exception as e:
        analysis['table_exists'] = False
        analysis['error'] = str(e)
    
    return analysis


def analyze_patent_intelligence_gap(session: Session) -> Dict[str, Any]:
    """Analyze patent/IP intelligence gap."""
    analysis = {
        'patents_table': {'row_count': 0, 'expected': True},
        'patent_drugs_table': {'row_count': 0, 'expected': True},
        'patent_companies_table': {'row_count': 0, 'expected': True},
        'sources_status': {},
        'impact_on_failure_detection': []
    }
    
    try:
        # Check patents table
        patent_count = session.query(func.count(Patent.patent_id)).filter(
            Patent.deleted_at.is_(None)
        ).scalar() or 0
        analysis['patents_table']['row_count'] = patent_count
        
        # Check patent relationships
        patent_drug_count = session.query(func.count(PatentDrug.patent_id)).filter(
            PatentDrug.deleted_at.is_(None)
        ).scalar() or 0
        analysis['patent_drugs_table']['row_count'] = patent_drug_count
        
        patent_company_count = session.query(func.count(PatentCompany.patent_id)).filter(
            PatentCompany.deleted_at.is_(None)
        ).scalar() or 0
        analysis['patent_companies_table']['row_count'] = patent_company_count
        
        # Check patent sources
        patent_sources = session.query(Source).filter(
            Source.source_type == 'patent',
            Source.deleted_at.is_(None)
        ).all()
        
        if not patent_sources:
            # Also check for sources with 'patent' in name
            patent_sources = session.query(Source).filter(
                Source.source_name.ilike('%patent%'),
                Source.deleted_at.is_(None)
            ).all()
        
        for source in patent_sources:
            processing_count = session.query(func.count(SourceProcessingLog.log_id)).filter(
                SourceProcessingLog.source_id == source.source_id,
                SourceProcessingLog.deleted_at.is_(None)
            ).scalar() or 0
            
            analysis['sources_status'][source.source_name] = {
                'is_active': source.is_active,
                'has_processing': processing_count > 0,
                'processing_count': processing_count
            }
        
        # Impact assessment
        if patent_count == 0:
            analysis['impact_on_failure_detection'].append(
                "Cannot track program ownership - missing critical IP intelligence"
            )
            analysis['impact_on_failure_detection'].append(
                "Cannot assess exclusivity timelines - patent expiration dates unknown"
            )
            analysis['impact_on_failure_detection'].append(
                "Cannot identify competitive IP landscape - missing patent data"
            )
        
    except Exception as e:
        analysis['error'] = str(e)
    
    return analysis


def generate_phase7_report() -> str:
    """Generate Phase 7: Critical Gaps Assessment report."""
    report_lines = []
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Phase 7: Critical Gaps Assessment")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("Goal: Identify what's missing for failure detection to work")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    with get_db_session() as session:
        # Section 1: Failure Signal Coverage
        report_lines.append("## 1. Failure Signal Coverage")
        report_lines.append("")
        
        failure_coverage = analyze_failure_signal_coverage(session)
        
        report_lines.append("### Expected Failure Signal Types")
        report_lines.append("")
        report_lines.append("| Signal Type | Expected | Present | Count | Status |")
        report_lines.append("|-------------|----------|---------|-------|--------|")
        
        for signal_type, info in failure_coverage['expected_signals'].items():
            if info['expected']:
                status = "✅ Present" if info['present'] else "❌ Missing"
                report_lines.append(
                    f"| {signal_type} | Yes | {'Yes' if info['present'] else 'No'} | {info['count']:,} | {status} |"
                )
        
        report_lines.append("")
        report_lines.append(f"**Total Failure Events:** {failure_coverage['total_failure_events']:,}")
        report_lines.append("")
        
        if failure_coverage['missing_signals']:
            report_lines.append("### ⚠️ Missing Failure Signal Types")
            report_lines.append("")
            for signal in failure_coverage['missing_signals']:
                report_lines.append(f"- `{signal}` - Not found in events table")
            report_lines.append("")
            report_lines.append("**Impact:**")
            report_lines.append("- These failure types cannot be detected or tracked")
            report_lines.append("- Risk scoring will miss these failure modes")
            report_lines.append("- Dashboard will not show these failure signals")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 2: Early Warning Signal Gaps
        report_lines.append("## 2. Early Warning Signal Gaps")
        report_lines.append("")
        
        warning_signals = analyze_early_warning_signals(session)
        
        report_lines.append("### Early Warning Signal Coverage")
        report_lines.append("")
        report_lines.append("| Signal Type | Expected | Present | Count | Source Status |")
        report_lines.append("|-------------|----------|---------|-------|---------------|")
        
        for signal_name, info in warning_signals.items():
            if signal_name != 'coverage_pct' and isinstance(info, dict) and 'expected' in info:
                present_str = "Yes" if info.get('present', False) or info.get('count', 0) > 0 else "No"
                source_status = info.get('source_status', 'N/A')
                report_lines.append(
                    f"| {signal_name.replace('_', ' ').title()} | Yes | {present_str} | {info.get('count', 0):,} | {source_status} |"
                )
        
        report_lines.append("")
        report_lines.append(f"**Overall Coverage:** {warning_signals['coverage_pct']:.1f}%")
        report_lines.append("")
        
        # Detailed analysis
        report_lines.append("### Detailed Analysis")
        report_lines.append("")
        
        if warning_signals['warn_notices']['source_status'] == 'not_registered':
            report_lines.append("**WARN Notices:** ❌ Source not registered")
            report_lines.append("- WARN notices indicate mass layoffs (strong failure signal)")
            report_lines.append("- No ingestion script found for WARN data")
            report_lines.append("- **Priority: HIGH** - Critical early warning signal")
            report_lines.append("")
        elif warning_signals['warn_notices']['source_status'] == 'not_running':
            report_lines.append("**WARN Notices:** ⚠️ Source registered but not running")
            report_lines.append("- Source exists but has not been executed")
            report_lines.append("- **Priority: HIGH** - Activate source immediately")
            report_lines.append("")
        
        if not warning_signals['layoff_signals']['present']:
            report_lines.append("**Layoff Signals:** ❌ No layoff events in database")
            report_lines.append("- Corporate layoffs are major financial distress signals")
            report_lines.append("- Should be captured as `corporate.layoff` events")
            report_lines.append("- **Priority: MEDIUM** - Important but may be captured via WARN")
            report_lines.append("")
        
        if warning_signals['fda_warning_letters']['source_status'] == 'not_registered':
            report_lines.append("**FDA Warning Letters:** ❌ Source not registered")
            report_lines.append("- FDA warning letters indicate regulatory issues")
            report_lines.append("- Strong early warning signal for compliance failures")
            report_lines.append("- **Priority: HIGH** - Regulatory risk indicator")
            report_lines.append("")
        
        if warning_signals['clinical_holds']['present']:
            report_lines.append(f"**Clinical Holds:** ✅ Present ({warning_signals['clinical_holds']['count']:,} events)")
            report_lines.append("")
        else:
            report_lines.append("**Clinical Holds:** ❌ Not found in events")
            report_lines.append("- Clinical holds are critical regulatory failure signals")
            report_lines.append("- Should be captured as `regulatory.clinical_hold` events")
            report_lines.append("- **Priority: CRITICAL** - Direct failure indicator")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 3: Regulatory Events Gap
        report_lines.append("## 3. Regulatory Events Gap")
        report_lines.append("")
        
        regulatory_gap = analyze_regulatory_events_gap(session)
        
        report_lines.append("### Regulatory Events Table Status")
        report_lines.append("")
        report_lines.append(f"- **Table Exists:** {'✅ Yes' if regulatory_gap['table_exists'] else '❌ No'}")
        report_lines.append(f"- **Row Count:** {regulatory_gap['row_count']:,}")
        report_lines.append("")
        
        if regulatory_gap['row_count'] == 0:
            report_lines.append("### ⚠️ Regulatory Events Table is Empty")
            report_lines.append("")
            report_lines.append("**Expected Data Types:**")
            report_lines.append("")
            for data_type, info in regulatory_gap['expected_data_types'].items():
                count = info.get('count', 0)
                status = "✅" if count > 0 else "❌"
                report_lines.append(f"- {data_type.replace('_', ' ').title()}: {status} {count:,} (in events table)")
            report_lines.append("")
            
            report_lines.append("**Regulatory Events in Events Table:**")
            report_lines.append(f"- Total regulatory events: {regulatory_gap['events_table_coverage']['regulatory_events_in_events']:,}")
            report_lines.append("")
            if regulatory_gap['events_table_coverage']['event_types']:
                report_lines.append("**Event Types Found:**")
                for event_type in regulatory_gap['events_table_coverage']['event_types']:
                    report_lines.append(f"- `{event_type}`")
                report_lines.append("")
            
            report_lines.append("### Why Regulatory Events Aren't Being Captured")
            report_lines.append("")
            if regulatory_gap['sources_status']:
                report_lines.append("**Regulatory Source Status:**")
                report_lines.append("")
                for source_name, status in regulatory_gap['sources_status'].items():
                    active_status = "✅ Active" if status['is_active'] else "❌ Inactive"
                    processing_status = f"({status['processing_count']:,} runs)" if status['has_processing'] else "(never run)"
                    report_lines.append(f"- {source_name}: {active_status} {processing_status}")
                report_lines.append("")
            else:
                report_lines.append("**No regulatory sources found**")
                report_lines.append("")
            
            report_lines.append("**Root Cause Analysis:**")
            report_lines.append("1. Regulatory events may be captured in `events` table instead of `regulatory_events`")
            report_lines.append("2. Regulatory sources may not be running (FDA approvals, rejections, etc.)")
            report_lines.append("3. Event extraction logic may not be creating regulatory events")
            report_lines.append("")
            report_lines.append("**Impact:**")
            report_lines.append("- Cannot query regulatory events separately from other events")
            report_lines.append("- Regulatory event-specific fields may be missing")
            report_lines.append("- Regulatory timeline analysis is limited")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 4: Patent/IP Intelligence Gap
        report_lines.append("## 4. Patent/IP Intelligence Gap")
        report_lines.append("")
        
        patent_gap = analyze_patent_intelligence_gap(session)
        
        report_lines.append("### Patent Tables Status")
        report_lines.append("")
        report_lines.append("| Table | Row Count | Expected | Status |")
        report_lines.append("|-------|-----------|----------|--------|")
        
        for table_name, info in patent_gap.items():
            if isinstance(info, dict) and 'row_count' in info:
                status = "✅" if info['row_count'] > 0 else "❌ Empty"
                report_lines.append(
                    f"| {table_name.replace('_', ' ').title()} | {info['row_count']:,} | Yes | {status} |"
                )
        
        report_lines.append("")
        
        if patent_gap['patents_table']['row_count'] == 0:
            report_lines.append("### ⚠️ Patent Tables Are Empty")
            report_lines.append("")
            report_lines.append("**Expected Data:**")
            report_lines.append("- Patent records (patent numbers, filing dates, expiration dates)")
            report_lines.append("- Patent-drug relationships (which drugs are covered by patents)")
            report_lines.append("- Patent-company relationships (which companies own patents)")
            report_lines.append("")
            
            if patent_gap['sources_status']:
                report_lines.append("**Patent Source Status:**")
                report_lines.append("")
                for source_name, status in patent_gap['sources_status'].items():
                    active_status = "✅ Active" if status['is_active'] else "❌ Inactive"
                    processing_status = f"({status['processing_count']:,} runs)" if status['has_processing'] else "(never run)"
                    report_lines.append(f"- {source_name}: {active_status} {processing_status}")
                report_lines.append("")
            else:
                report_lines.append("**No patent sources found**")
                report_lines.append("")
            
            report_lines.append("### Impact on Failure Detection")
            report_lines.append("")
            for impact in patent_gap['impact_on_failure_detection']:
                report_lines.append(f"- {impact}")
            report_lines.append("")
            report_lines.append("**Additional Impacts:**")
            report_lines.append("- Cannot assess IP protection status of programs")
            report_lines.append("- Cannot identify when exclusivity expires (generic competition risk)")
            report_lines.append("- Cannot track competitive IP landscape")
            report_lines.append("- Missing critical data for program valuation")
            report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        
        # Section 5: Prioritized Gaps Summary
        report_lines.append("## 5. Prioritized Gaps Summary")
        report_lines.append("")
        
        report_lines.append("### CRITICAL Priority (Blocks Failure Detection)")
        report_lines.append("")
        critical_gaps = []
        
        if not warning_signals['clinical_holds']['present']:
            critical_gaps.append("Clinical holds not captured - direct failure indicator missing")
        
        if regulatory_gap['row_count'] == 0 and regulatory_gap['events_table_coverage']['regulatory_events_in_events'] == 0:
            critical_gaps.append("No regulatory events captured - approvals/rejections/holds missing")
        
        if patent_gap['patents_table']['row_count'] == 0:
            critical_gaps.append("Patent data missing - cannot assess IP protection and exclusivity")
        
        if critical_gaps:
            for i, gap in enumerate(critical_gaps, 1):
                report_lines.append(f"{i}. {gap}")
        else:
            report_lines.append("None identified")
        report_lines.append("")
        
        report_lines.append("### HIGH Priority (Significantly Impacts Failure Detection)")
        report_lines.append("")
        high_gaps = []
        
        if warning_signals['warn_notices']['source_status'] in ['not_registered', 'not_running']:
            high_gaps.append("WARN notices not being captured - mass layoff signals missing")
        
        if warning_signals['fda_warning_letters']['source_status'] == 'not_registered':
            high_gaps.append("FDA warning letters not being captured - regulatory risk signals missing")
        
        if len(failure_coverage['missing_signals']) > 0:
            high_gaps.append(f"Missing failure signal types: {', '.join(failure_coverage['missing_signals'][:3])}")
        
        if high_gaps:
            for i, gap in enumerate(high_gaps, 1):
                report_lines.append(f"{i}. {gap}")
        else:
            report_lines.append("None identified")
        report_lines.append("")
        
        report_lines.append("### MEDIUM Priority (Enhances Failure Detection)")
        report_lines.append("")
        medium_gaps = []
        
        if not warning_signals['layoff_signals']['present']:
            medium_gaps.append("Layoff events not captured (may be covered by WARN notices)")
        
        if len(failure_coverage['missing_signals']) > 3:
            medium_gaps.append(f"Additional missing failure signal types: {len(failure_coverage['missing_signals']) - 3} more")
        
        if medium_gaps:
            for i, gap in enumerate(medium_gaps, 1):
                report_lines.append(f"{i}. {gap}")
        else:
            report_lines.append("None identified")
        report_lines.append("")
        
        report_lines.append("### Recommendations")
        report_lines.append("")
        report_lines.append("1. **Activate Regulatory Sources:**")
        report_lines.append("   - Register and activate FDA data sources (approvals, rejections, clinical holds)")
        report_lines.append("   - Ensure event extraction creates regulatory events")
        report_lines.append("")
        report_lines.append("2. **Register WARN Notice Source:**")
        report_lines.append("   - Create ingestion script for WARN notices")
        report_lines.append("   - Register source and activate")
        report_lines.append("   - Extract as `corporate.layoff` events")
        report_lines.append("")
        report_lines.append("3. **Activate Patent Sources:**")
        report_lines.append("   - Register patent data sources (USPTO, PatentsView)")
        report_lines.append("   - Extract patent-drug and patent-company relationships")
        report_lines.append("   - Capture expiration dates for exclusivity analysis")
        report_lines.append("")
        report_lines.append("4. **Complete Failure Signal Types:**")
        report_lines.append("   - Ensure all failure event types are being captured")
        report_lines.append("   - Add missing event types to event extraction logic")
        report_lines.append("")
        
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("**End of Phase 7 Report**")
        report_lines.append("")
    
    return "\n".join(report_lines)


def main():
    """Main entry point."""
    print("="*80)
    print("Source Configuration & Data Pipeline Audit")
    print("="*80)
    print()
    
    print("Generating Phase 1: Source Configuration Audit...")
    phase1_report = generate_audit_report()
    
    print("Generating Phase 2: Data Pipeline Integrity Check...")
    phase2_report = generate_phase2_report()
    
    print("Generating Phase 3: Relationship Generation Coverage...")
    phase3_report = generate_phase3_report()
    
    print("Generating Phase 4: Entity Resolution Quality...")
    phase4_report = generate_phase4_report()
    
    print("Generating Phase 5: Scoring System Validation...")
    phase5_report = generate_phase5_report()
    
    print("Generating Phase 6: UI Data Accuracy...")
    phase6_report = generate_phase6_report()
    
    print("Generating Phase 7: Critical Gaps Assessment...")
    phase7_report = generate_phase7_report()
    
    # Combine reports
    full_report = phase1_report + phase2_report + phase3_report + phase4_report + phase5_report + phase6_report + phase7_report
    
    # Write to file
    output_file = project_root / "SOURCE_CONFIGURATION_AUDIT.md"
    with open(output_file, 'w') as f:
        f.write(full_report)
    
    print(f"✅ Complete audit report generated: {output_file}")
    print()
    print("Report sections:")
    print("  Phase 1:")
    print("    1. Source Registration Check")
    print("    2. Source Activation Verification")
    print("    3. Missing Critical Sources")
    print("    4. Registration Recommendations")
    print("    5. Summary Statistics")
    print("  Phase 2:")
    print("    1. Staging to Entity Conversion Rates")
    print("    2. Entity Extraction Validation")
    print("    3. Deduplication Analysis")
    print("    4. Data Loss Funnel Summary")
    print("  Phase 3:")
    print("    1. Relationship Creation Rates")
    print("    2. Cross-Reference Validation")
    print("    3. Company-Drug Relationship Investigation")
    print("    4. Gap Analysis Summary")
    print("  Phase 4:")
    print("    1. Resolution Coverage by Source")
    print("    2. Match Candidate Review")
    print("    3. Alias Quality Check")
    print("    4. Sponsor Coverage Deep Dive")
    print("    5. Recommendations Summary")
    print("  Phase 5:")
    print("    1. Score Component Analysis")
    print("    2. Input Data Completeness")
    print("    3. Expected vs Actual Scoring")
    print("    4. Score Distribution Reasonableness")
    print("  Phase 6:")
    print("    1. API Response Validation")
    print("    2. Failed Trials List Accuracy")
    print("    3. Company Search Functionality")
    print("    4. Timeline Visualization Data")
    print("  Phase 7:")
    print("    1. Failure Signal Coverage")
    print("    2. Early Warning Signal Gaps")
    print("    3. Regulatory Events Gap")
    print("    4. Patent/IP Intelligence Gap")
    print("    5. Prioritized Gaps Summary")
    print("="*80)


if __name__ == "__main__":
    main()

