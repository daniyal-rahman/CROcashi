#!/usr/bin/env python3
"""
Comprehensive Repository Audit
Checks actual ingestion status, data quality, and relationship creation vs claims.
Identifies bugs, empty tables, and LLM-generated green flags.
"""
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime
import json

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

from database.config import get_db_session
from database.models.sources import Source
from database.models.staging import StagingRawData
from database.models.entities import (
    Company, Drug, Disease, Institution
)
from database.models.clinical import ClinicalTrial
from database.models.publications import Publication, Patent, SECFiling
from database.models.relationships import (
    TrialSponsor, TrialDrug, TrialDisease,
    PublicationTrial, PublicationDrug, PublicationCompany,
    FilingCompany, FilingDrug,
    CompanyDrug, PatentDrug, PatentCompany
)


class ComprehensiveAudit:
    """Comprehensive audit of repository ingestion and data quality."""
    
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'sources': {},
            'data_quality': {},
            'relationships': {},
            'bugs': [],
            'warnings': [],
            'summary': {}
        }
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all audit checks."""
        print("\n" + "="*80)
        print("COMPREHENSIVE REPOSITORY AUDIT")
        print("="*80)
        
        with get_db_session() as session:
            self.check_source_registration(session)
            self.check_ingestion_scripts(session)
            self.check_staging_data(session)
            self.check_entity_counts(session)
            self.check_relationship_counts(session)
            self.check_empty_tables(session)
            self.check_processing_logs(session)
            self.check_relationship_coverage(session)
            self.check_data_quality_issues(session)
            self.check_processor_implementation(session)
            self.generate_summary()
        
        return self.results
    
    def check_source_registration(self, session: Session):
        """Check source registration vs claims."""
        print("\n[1/11] Checking Source Registration...")
        
        # Get registered sources
        registered = session.query(Source).filter(
            Source.deleted_at.is_(None)
        ).all()
        
        # Get ingestion scripts
        ingestion_dir = project_root / 'ingestion'
        ingestion_scripts = {
            f.stem for f in ingestion_dir.glob('*.py')
            if f.name not in ['__init__.py', 'test_helper.py']
        }
        
        active_sources = [s for s in registered if s.is_active]
        inactive_sources = [s for s in registered if not s.is_active]
        unregistered_scripts = ingestion_scripts - {s.source_name for s in registered}
        
        self.results['sources'] = {
            'total_scripts': len(ingestion_scripts),
            'registered': len(registered),
            'active': len(active_sources),
            'inactive': len(inactive_sources),
            'unregistered': len(unregistered_scripts),
            'active_list': [s.source_name for s in active_sources],
            'inactive_list': [s.source_name for s in inactive_sources],
            'unregistered_list': sorted(list(unregistered_scripts))[:20]  # First 20
        }
        
        # Check for claims vs reality
        if len(active_sources) < 10:
            self.results['warnings'].append({
                'type': 'source_count',
                'message': f"Only {len(active_sources)} active sources, not 30+ as might be claimed",
                'severity': 'high'
            })
        
        print(f"  ✓ Found {len(ingestion_scripts)} ingestion scripts")
        print(f"  ✓ {len(registered)} registered, {len(active_sources)} active")
        print(f"  ✓ {len(unregistered_scripts)} unregistered scripts")
    
    def check_ingestion_scripts(self, session: Session):
        """Check if ingestion scripts actually work."""
        print("\n[2/11] Checking Ingestion Scripts...")
        
        # Check which sources have data in staging
        staging_sources = session.query(StagingRawData.source_system).distinct().all()
        staging_source_names = {s[0] for s in staging_sources}
        
        # Check processing logs
        processing_sources = session.execute(
            text("SELECT DISTINCT source_name FROM source_processing_log")
        ).fetchall()
        processing_source_names = {s[0] for s in processing_sources}
        
        self.results['sources']['with_staging_data'] = len(staging_source_names)
        self.results['sources']['with_processing_logs'] = len(processing_source_names)
        self.results['sources']['staging_sources'] = sorted(list(staging_source_names))
        self.results['sources']['processing_sources'] = sorted(list(processing_source_names))
        
        # Check for sources that claim to be active but have no data
        active_sources = session.query(Source).filter(
            Source.is_active == True,
            Source.deleted_at.is_(None)
        ).all()
        
        active_without_data = []
        for source in active_sources:
            has_staging = source.source_name in staging_source_names
            has_processing = source.source_name in processing_source_names
            if not has_staging and not has_processing:
                active_without_data.append(source.source_name)
        
        if active_without_data:
            self.results['bugs'].append({
                'type': 'active_source_no_data',
                'sources': active_without_data,
                'message': f"Active sources with no data: {', '.join(active_without_data)}"
            })
        
        print(f"  ✓ {len(staging_source_names)} sources with staging data")
        print(f"  ✓ {len(processing_source_names)} sources with processing logs")
        if active_without_data:
            print(f"  ⚠ {len(active_without_data)} active sources with no data")
    
    def check_staging_data(self, session: Session):
        """Check staging table data."""
        print("\n[3/11] Checking Staging Data...")
        
        total_staging = session.query(StagingRawData).count()
        processed_staging = session.query(StagingRawData).filter(
            StagingRawData.processed_at.isnot(None)
        ).count()
        unprocessed_staging = total_staging - processed_staging
        
        # By source
        staging_by_source = session.execute(
            text("""
                SELECT source_system, COUNT(*) as count,
                       COUNT(processed_at) as processed_count
                FROM staging_raw_data
                WHERE deleted_at IS NULL
                GROUP BY source_system
                ORDER BY count DESC
            """)
        ).fetchall()
        
        self.results['data_quality']['staging'] = {
            'total': total_staging,
            'processed': processed_staging,
            'unprocessed': unprocessed_staging,
            'processing_rate': (processed_staging / total_staging * 100) if total_staging > 0 else 0,
            'by_source': [
                {'source': s[0], 'total': s[1], 'processed': s[2], 
                 'rate': (s[2] / s[1] * 100) if s[1] > 0 else 0}
                for s in staging_by_source
            ]
        }
        
        if unprocessed_staging > 0:
            self.results['warnings'].append({
                'type': 'unprocessed_staging',
                'count': unprocessed_staging,
                'message': f"{unprocessed_staging} unprocessed staging records"
            })
        
        print(f"  ✓ {total_staging} total staging records")
        print(f"  ✓ {processed_staging} processed ({processed_staging/total_staging*100:.1f}%)")
        print(f"  ⚠ {unprocessed_staging} unprocessed")
    
    def check_entity_counts(self, session: Session):
        """Check entity counts in database."""
        print("\n[4/11] Checking Entity Counts...")
        
        entity_counts = {
            'companies': session.query(Company).filter(Company.deleted_at.is_(None)).count(),
            'drugs': session.query(Drug).filter(Drug.deleted_at.is_(None)).count(),
            'diseases': session.query(Disease).filter(Disease.deleted_at.is_(None)).count(),
            'trials': session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count(),
            'publications': session.query(Publication).filter(Publication.deleted_at.is_(None)).count(),
            'institutions': session.query(Institution).filter(Institution.deleted_at.is_(None)).count(),
            'filings': session.query(SECFiling).filter(SECFiling.deleted_at.is_(None)).count(),
            'patents': session.query(Patent).filter(Patent.deleted_at.is_(None)).count(),
        }
        
        self.results['data_quality']['entities'] = entity_counts
        
        # Check for suspiciously low counts
        if entity_counts['publications'] > 0 and entity_counts['trials'] > 0:
            pub_trial_ratio = entity_counts['publications'] / entity_counts['trials']
            if pub_trial_ratio < 0.1:
                self.results['warnings'].append({
                    'type': 'low_publication_count',
                    'message': f"Only {entity_counts['publications']} publications for {entity_counts['trials']} trials (ratio: {pub_trial_ratio:.2f})"
                })
        
        print(f"  ✓ Companies: {entity_counts['companies']}")
        print(f"  ✓ Drugs: {entity_counts['drugs']}")
        print(f"  ✓ Diseases: {entity_counts['diseases']}")
        print(f"  ✓ Trials: {entity_counts['trials']}")
        print(f"  ✓ Publications: {entity_counts['publications']}")
        print(f"  ✓ Filings: {entity_counts['filings']}")
        print(f"  ✓ Patents: {entity_counts['patents']}")
    
    def check_relationship_counts(self, session: Session):
        """Check relationship counts."""
        print("\n[5/11] Checking Relationship Counts...")
        
        relationship_counts = {
            'trial_sponsors': session.query(TrialSponsor).filter(TrialSponsor.deleted_at.is_(None)).count(),
            'trial_drugs': session.query(TrialDrug).filter(TrialDrug.deleted_at.is_(None)).count(),
            'trial_diseases': session.query(TrialDisease).filter(TrialDisease.deleted_at.is_(None)).count(),
            'publication_trials': session.query(PublicationTrial).filter(PublicationTrial.deleted_at.is_(None)).count(),
            'publication_drugs': session.query(PublicationDrug).filter(PublicationDrug.deleted_at.is_(None)).count(),
            'publication_companies': session.query(PublicationCompany).filter(PublicationCompany.deleted_at.is_(None)).count(),
            'filing_companies': session.query(FilingCompany).filter(FilingCompany.deleted_at.is_(None)).count(),
            'filing_drugs': session.query(FilingDrug).filter(FilingDrug.deleted_at.is_(None)).count(),
            'company_drugs': session.query(CompanyDrug).filter(CompanyDrug.deleted_at.is_(None)).count(),
            'patent_drugs': session.query(PatentDrug).filter(PatentDrug.deleted_at.is_(None)).count(),
            'patent_companies': session.query(PatentCompany).filter(PatentCompany.deleted_at.is_(None)).count(),
        }
        
        self.results['relationships']['counts'] = relationship_counts
        
        # Check for empty relationship tables that should have data
        trial_count = self.results['data_quality']['entities']['trials']
        pub_count = self.results['data_quality']['entities']['publications']
        filing_count = self.results['data_quality']['entities']['filings']
        
        if pub_count > 0:
            if relationship_counts['publication_trials'] == 0:
                self.results['bugs'].append({
                    'type': 'empty_relationship_table',
                    'table': 'publication_trials',
                    'message': f"0 publication-trial relationships despite {pub_count} publications and {trial_count} trials"
                })
            if relationship_counts['publication_drugs'] == 0:
                self.results['bugs'].append({
                    'type': 'empty_relationship_table',
                    'table': 'publication_drugs',
                    'message': f"0 publication-drug relationships despite {pub_count} publications"
                })
        
        if filing_count > 0:
            if relationship_counts['filing_drugs'] == 0:
                self.results['bugs'].append({
                    'type': 'empty_relationship_table',
                    'table': 'filing_drugs',
                    'message': f"0 filing-drug relationships despite {filing_count} filings"
                })
        
        print(f"  ✓ Trial-Sponsor: {relationship_counts['trial_sponsors']}")
        print(f"  ✓ Trial-Drug: {relationship_counts['trial_drugs']}")
        print(f"  ✓ Trial-Disease: {relationship_counts['trial_diseases']}")
        print(f"  ⚠ Publication-Trial: {relationship_counts['publication_trials']} (expected >0)")
        print(f"  ⚠ Publication-Drug: {relationship_counts['publication_drugs']} (expected >0)")
        print(f"  ⚠ Filing-Drug: {relationship_counts['filing_drugs']} (expected >0)")
    
    def check_empty_tables(self, session: Session):
        """Check for empty tables that should have data."""
        print("\n[6/11] Checking Empty Tables...")
        
        inspector = inspect(session.bind)
        all_tables = inspector.get_table_names()
        
        empty_tables = []
        for table_name in sorted(all_tables):
            if table_name.startswith('alembic_'):
                continue
            
            count = session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            if count == 0:
                empty_tables.append(table_name)
        
        self.results['data_quality']['empty_tables'] = empty_tables
        self.results['data_quality']['empty_table_count'] = len(empty_tables)
        
        # Check if critical tables are empty
        critical_empty = []
        for table in ['publication_trials', 'publication_drugs', 'filing_drugs', 
                     'regulatory_events', 'patents', 'patent_drugs']:
            if table in empty_tables:
                critical_empty.append(table)
        
        if critical_empty:
            self.results['bugs'].append({
                'type': 'critical_empty_tables',
                'tables': critical_empty,
                'message': f"Critical tables are empty: {', '.join(critical_empty)}"
            })
        
        print(f"  ✓ Found {len(empty_tables)} empty tables")
        if critical_empty:
            print(f"  ⚠ Critical empty tables: {', '.join(critical_empty)}")
    
    def check_processing_logs(self, session: Session):
        """Check processing logs for errors."""
        print("\n[7/11] Checking Processing Logs...")
        
        # Get processing statistics
        total_logs = session.execute(
            text("SELECT COUNT(*) FROM source_processing_log")
        ).scalar()
        
        failed_logs = session.execute(
            text("""
                SELECT COUNT(*) FROM source_processing_log
                WHERE processing_status = 'failed' OR errors IS NOT NULL
            """)
        ).scalar()
        
        # Get recent processing activity
        recent_activity = session.execute(
            text("""
                SELECT source_name, COUNT(*) as count, MAX(processing_completed_at) as last_run
                FROM source_processing_log
                WHERE processing_completed_at >= NOW() - INTERVAL '30 days'
                GROUP BY source_name
                ORDER BY count DESC
            """)
        ).fetchall()
        
        self.results['data_quality']['processing'] = {
            'total_logs': total_logs,
            'failed_logs': failed_logs,
            'failure_rate': (failed_logs / total_logs * 100) if total_logs > 0 else 0,
            'recent_activity': [
                {'source': r[0], 'count': r[1], 'last_run': str(r[2])}
                for r in recent_activity
            ]
        }
        
        if failed_logs > 0:
            self.results['warnings'].append({
                'type': 'processing_failures',
                'count': failed_logs,
                'message': f"{failed_logs} failed processing logs"
            })
        
        print(f"  ✓ {total_logs} total processing logs")
        print(f"  ⚠ {failed_logs} failed logs")
        print(f"  ✓ {len(recent_activity)} sources active in last 30 days")
    
    def check_relationship_coverage(self, session: Session):
        """Check relationship coverage rates."""
        print("\n[8/11] Checking Relationship Coverage...")
        
        trial_count = self.results['data_quality']['entities']['trials']
        pub_count = self.results['data_quality']['entities']['publications']
        filing_count = self.results['data_quality']['entities']['filings']
        
        rel_counts = self.results['relationships']['counts']
        
        coverage = {}
        
        if trial_count > 0:
            coverage['trials_with_sponsors'] = {
                'count': rel_counts['trial_sponsors'],
                'total': trial_count,
                'rate': (rel_counts['trial_sponsors'] / trial_count * 100)
            }
            coverage['trials_with_drugs'] = {
                'count': rel_counts['trial_drugs'],
                'total': trial_count,
                'rate': (rel_counts['trial_drugs'] / trial_count * 100)
            }
            coverage['trials_with_diseases'] = {
                'count': rel_counts['trial_diseases'],
                'total': trial_count,
                'rate': (rel_counts['trial_diseases'] / trial_count * 100)
            }
        
        if pub_count > 0:
            coverage['publications_with_trials'] = {
                'count': rel_counts['publication_trials'],
                'total': pub_count,
                'rate': (rel_counts['publication_trials'] / pub_count * 100)
            }
            coverage['publications_with_drugs'] = {
                'count': rel_counts['publication_drugs'],
                'total': pub_count,
                'rate': (rel_counts['publication_drugs'] / pub_count * 100)
            }
        
        if filing_count > 0:
            coverage['filings_with_drugs'] = {
                'count': rel_counts['filing_drugs'],
                'total': filing_count,
                'rate': (rel_counts['filing_drugs'] / filing_count * 100)
            }
        
        self.results['relationships']['coverage'] = coverage
        
        # Check for suspiciously low coverage
        if trial_count > 0:
            if coverage['trials_with_drugs']['rate'] < 40:
                self.results['warnings'].append({
                    'type': 'low_drug_coverage',
                    'rate': coverage['trials_with_drugs']['rate'],
                    'message': f"Only {coverage['trials_with_drugs']['rate']:.1f}% of trials have drugs (expected 60-90%)"
                })
        
        if pub_count > 0:
            if coverage['publications_with_trials']['rate'] == 0:
                self.results['bugs'].append({
                    'type': 'zero_publication_trial_coverage',
                    'message': f"0% of publications linked to trials (expected 5-20%)"
                })
            if coverage['publications_with_drugs']['rate'] == 0:
                self.results['bugs'].append({
                    'type': 'zero_publication_drug_coverage',
                    'message': f"0% of publications linked to drugs (expected 30-50%)"
                })
        
        print(f"  ✓ Trial-Sponsor coverage: {coverage.get('trials_with_sponsors', {}).get('rate', 0):.1f}%")
        print(f"  ✓ Trial-Drug coverage: {coverage.get('trials_with_drugs', {}).get('rate', 0):.1f}%")
        print(f"  ⚠ Publication-Trial coverage: {coverage.get('publications_with_trials', {}).get('rate', 0):.1f}%")
        print(f"  ⚠ Publication-Drug coverage: {coverage.get('publications_with_drugs', {}).get('rate', 0):.1f}%")
    
    def check_data_quality_issues(self, session: Session):
        """Check for data quality issues."""
        print("\n[9/11] Checking Data Quality Issues...")
        
        issues = []
        
        # Check for orphaned relationships
        orphaned_trial_sponsors = session.execute(
            text("""
                SELECT COUNT(*) FROM trial_sponsors ts
                LEFT JOIN clinical_trials ct ON ts.trial_id = ct.trial_id
                WHERE ct.trial_id IS NULL AND ts.deleted_at IS NULL
            """)
        ).scalar()
        
        if orphaned_trial_sponsors > 0:
            issues.append({
                'type': 'orphaned_relationships',
                'table': 'trial_sponsors',
                'count': orphaned_trial_sponsors
            })
        
        # Check for null names
        null_company_names = session.query(Company).filter(
            Company.name.is_(None),
            Company.deleted_at.is_(None)
        ).count()
        
        if null_company_names > 0:
            issues.append({
                'type': 'null_names',
                'table': 'companies',
                'count': null_company_names
            })
        
        # Check for duplicate relationships
        duplicate_trial_drugs = session.execute(
            text("""
                SELECT trial_id, drug_id, COUNT(*) as cnt
                FROM trial_drugs
                WHERE deleted_at IS NULL
                GROUP BY trial_id, drug_id
                HAVING COUNT(*) > 1
            """)
        ).fetchall()
        
        if duplicate_trial_drugs:
            issues.append({
                'type': 'duplicate_relationships',
                'table': 'trial_drugs',
                'count': len(duplicate_trial_drugs)
            })
        
        self.results['data_quality']['issues'] = issues
        
        if issues:
            for issue in issues:
                self.results['warnings'].append({
                    'type': issue['type'],
                    'message': f"{issue['table']}: {issue['count']} {issue['type']}"
                })
        
        print(f"  ✓ Found {len(issues)} data quality issues")
        for issue in issues:
            print(f"    ⚠ {issue['type']} in {issue['table']}: {issue['count']}")
    
    def check_processor_implementation(self, session: Session):
        """Check if processors are actually implemented."""
        print("\n[10/11] Checking Processor Implementation...")
        
        # Check if processors exist for active sources
        processors_dir = project_root / 'src' / 'processors'
        processor_files = {f.stem.replace('_processor', '') for f in processors_dir.glob('*_processor.py')}
        
        active_sources = self.results['sources']['active_list']
        missing_processors = [s for s in active_sources if s not in processor_files]
        
        self.results['sources']['missing_processors'] = missing_processors
        
        if missing_processors:
            self.results['bugs'].append({
                'type': 'missing_processors',
                'sources': missing_processors,
                'message': f"Active sources without processors: {', '.join(missing_processors)}"
            })
        
        print(f"  ✓ Found {len(processor_files)} processors")
        if missing_processors:
            print(f"  ⚠ {len(missing_processors)} active sources missing processors")
    
    def generate_summary(self):
        """Generate audit summary."""
        print("\n[11/11] Generating Summary...")
        
        summary = {
            'total_sources_claimed': self.results['sources']['total_scripts'],
            'active_sources': self.results['sources']['active'],
            'sources_with_data': self.results['sources']['with_staging_data'],
            'total_entities': sum(self.results['data_quality']['entities'].values()),
            'total_relationships': sum(self.results['relationships']['counts'].values()),
            'empty_tables': self.results['data_quality']['empty_table_count'],
            'bugs_found': len(self.results['bugs']),
            'warnings': len(self.results['warnings']),
            'critical_issues': [
                b for b in self.results['bugs'] 
                if b['type'] in ['empty_relationship_table', 'critical_empty_tables', 
                                'zero_publication_trial_coverage', 'zero_publication_drug_coverage']
            ]
        }
        
        self.results['summary'] = summary
        
        print("\n" + "="*80)
        print("AUDIT SUMMARY")
        print("="*80)
        print(f"Total Ingestion Scripts: {summary['total_sources_claimed']}")
        print(f"Active Sources: {summary['active_sources']}")
        print(f"Sources with Data: {summary['sources_with_data']}")
        print(f"Total Entities: {summary['total_entities']}")
        print(f"Total Relationships: {summary['total_relationships']}")
        print(f"Empty Tables: {summary['empty_tables']}")
        print(f"Bugs Found: {summary['bugs_found']}")
        print(f"Warnings: {summary['warnings']}")
        print(f"Critical Issues: {len(summary['critical_issues'])}")
        
        if summary['critical_issues']:
            print("\n🚨 CRITICAL ISSUES:")
            for issue in summary['critical_issues']:
                print(f"  - {issue['message']}")
        
        print("\n" + "="*80)


def main():
    """Run comprehensive audit."""
    audit = ComprehensiveAudit()
    results = audit.run_all_checks()
    
    # Save results
    output_file = project_root / 'COMPREHENSIVE_AUDIT_REPORT.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n✓ Audit complete. Results saved to: {output_file}")
    
    # Print critical findings
    if results['bugs']:
        print("\n🚨 BUGS FOUND:")
        for bug in results['bugs']:
            print(f"  - [{bug['type']}] {bug['message']}")
    
    return 0 if len(results['bugs']) == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

