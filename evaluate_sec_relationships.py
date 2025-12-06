"""
Comprehensive evaluation of SEC EDGAR relationships and wiring.

Checks:
1. Relationship integrity (foreign keys, orphaned relationships)
2. Data quality (null values, constraint violations)
3. Relationship correctness (filing-company links make sense)
4. Wiring completeness (all expected relationships exist)
5. Entity resolution quality
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models import (
    SECFiling, Company, Drug, FilingCompany, FilingDrug,
    StagingRawData, SourceProcessingLog
)
from sqlalchemy import func, and_, or_

print("=" * 70)
print("SEC EDGAR RELATIONSHIPS & WIRING EVALUATION")
print("=" * 70)

with get_db_session() as session:
    # ============================================================
    # 1. BASIC STATISTICS
    # ============================================================
    print("\n📊 BASIC STATISTICS:")
    
    filing_count = session.query(SECFiling).count()
    company_count = session.query(Company).count()
    drug_count = session.query(Drug).count()
    fc_rel_count = session.query(FilingCompany).count()
    fd_rel_count = session.query(FilingDrug).count()
    
    print(f"  SEC Filings: {filing_count}")
    print(f"  Companies: {company_count}")
    print(f"  Drugs: {drug_count}")
    print(f"  Filing-Company relationships: {fc_rel_count}")
    print(f"  Filing-Drug relationships: {fd_rel_count}")
    
    # ============================================================
    # 2. RELATIONSHIP INTEGRITY CHECKS
    # ============================================================
    print("\n🔗 RELATIONSHIP INTEGRITY:")
    
    # Check for orphaned Filing-Company relationships
    orphaned_fc = session.query(FilingCompany).filter(
        or_(
            ~FilingCompany.filing.has(),
            ~FilingCompany.company.has()
        )
    ).count()
    print(f"  Orphaned Filing-Company relationships: {orphaned_fc}")
    
    # Check for orphaned Filing-Drug relationships
    orphaned_fd = session.query(FilingDrug).filter(
        or_(
            ~FilingDrug.filing.has(),
            ~FilingDrug.drug.has()
        )
    ).count()
    print(f"  Orphaned Filing-Drug relationships: {orphaned_fd}")
    
    # Check for filings without company relationships
    filings_without_company = session.query(SECFiling).filter(
        ~SECFiling.companies.any()
    ).count()
    print(f"  Filings without company relationships: {filings_without_company}")
    
    # Check for companies without filing relationships
    companies_without_filings = session.query(Company).filter(
        ~Company.filings.any()
    ).count()
    print(f"  Companies without filing relationships: {companies_without_filings}")
    
    # ============================================================
    # 3. DATA QUALITY CHECKS
    # ============================================================
    print("\n✅ DATA QUALITY:")
    
    # Check for null required fields in filings
    null_filing_dates = session.query(SECFiling).filter(
        SECFiling.filing_date == None
    ).count()
    null_accession_numbers = session.query(SECFiling).filter(
        SECFiling.accession_number == None
    ).count()
    null_filing_types = session.query(SECFiling).filter(
        SECFiling.filing_type == None
    ).count()
    
    print(f"  Filings with null filing_date: {null_filing_dates}")
    print(f"  Filings with null accession_number: {null_accession_numbers}")
    print(f"  Filings with null filing_type: {null_filing_types}")
    
    # Check for invalid filing types
    invalid_filing_types = session.query(SECFiling).filter(
        ~SECFiling.filing_type.in_(['8-K', '10-K', '10-Q', 'S-1', 'DEF 14A'])
    ).count()
    print(f"  Filings with invalid filing_type: {invalid_filing_types}")
    
    # Check for invalid mention_types in FilingDrug
    invalid_mention_types = session.query(FilingDrug).filter(
        and_(
            FilingDrug.mention_type.isnot(None),
            ~FilingDrug.mention_type.in_(['pipeline_update', 'termination', 'milestone', 'licensing'])
        )
    ).count()
    print(f"  Filing-Drug relationships with invalid mention_type: {invalid_mention_types}")
    
    # ============================================================
    # 4. RELATIONSHIP CORRECTNESS
    # ============================================================
    print("\n🎯 RELATIONSHIP CORRECTNESS:")
    
    # Sample Filing-Company relationships
    sample_fc_rels = session.query(FilingCompany).limit(5).all()
    
    print(f"  Sample Filing-Company relationships ({min(5, fc_rel_count)}):")
    for i, rel in enumerate(sample_fc_rels, 1):
        filing = rel.filing
        company = rel.company
        if filing and company:
            print(f"    {i}. Filing: {filing.accession_number} ({filing.filing_date})")
            print(f"       Company: {company.name}")
            print(f"       ✅ Relationship valid")
        else:
            print(f"    {i}. ⚠️  Orphaned relationship")
    
    # Check if all filings have company relationships
    all_filings = session.query(SECFiling).all()
    filings_with_companies = sum(1 for f in all_filings if f.companies)
    print(f"\n  Filings with company relationships: {filings_with_companies}/{filing_count}")
    
    if filings_with_companies < filing_count:
        missing = filing_count - filings_with_companies
        print(f"  ⚠️  {missing} filings missing company relationships")
    
    # ============================================================
    # 5. WIRING COMPLETENESS
    # ============================================================
    print("\n🔌 WIRING COMPLETENESS:")
    
    # Check staging → processing → database flow
    staging_total = session.query(StagingRawData).filter_by(
        source_system='sec_edgar'
    ).count()
    staging_processed = session.query(StagingRawData).filter_by(
        source_system='sec_edgar',
        processed=True
    ).count()
    
    print(f"  Staging records: {staging_total}")
    print(f"  Processed records: {staging_processed}")
    print(f"  Processing rate: {staging_processed/staging_total*100:.1f}%" if staging_total > 0 else "N/A")
    
    # Check if all processed records have corresponding filings
    processed_identifiers = set(
        log.source_identifier for log in 
        session.query(SourceProcessingLog).filter_by(
            source_name='sec_edgar',
            processing_status='success'
        ).all()
    )
    filing_identifiers = set(
        f.accession_number for f in session.query(SECFiling).all()
    )
    
    print(f"  Processed identifiers: {len(processed_identifiers)}")
    print(f"  Filing identifiers: {len(filing_identifiers)}")
    
    missing_filings = processed_identifiers - filing_identifiers
    if missing_filings:
        print(f"  ⚠️  {len(missing_filings)} processed records missing filings")
    else:
        print(f"  ✅ All processed records have corresponding filings")
    
    # ============================================================
    # 6. ENTITY RESOLUTION QUALITY
    # ============================================================
    print("\n🎯 ENTITY RESOLUTION QUALITY:")
    
    # Check processing logs
    logs = session.query(SourceProcessingLog).filter_by(
        source_name='sec_edgar'
    ).all()
    
    if logs:
        total_extracted = sum(log.entities_extracted or 0 for log in logs)
        total_created = sum(log.entities_created or 0 for log in logs)
        total_matched = sum(log.entities_matched or 0 for log in logs)
        total_relationships = sum(log.relationships_created or 0 for log in logs)
        
        print(f"  Total entities extracted: {total_extracted}")
        print(f"  Total entities created: {total_created}")
        print(f"  Total entities matched: {total_matched}")
        print(f"  Total relationships created: {total_relationships}")
        
        if total_extracted > 0:
            match_rate = (total_matched / total_extracted) * 100
            creation_rate = (total_created / total_extracted) * 100
            print(f"  Match rate: {match_rate:.1f}%")
            print(f"  Creation rate: {creation_rate:.1f}%")
    
    # ============================================================
    # 7. DETAILED RELATIONSHIP ANALYSIS
    # ============================================================
    print("\n📋 DETAILED RELATIONSHIP ANALYSIS:")
    
    # Filing-Company relationship details
    if fc_rel_count > 0:
        print(f"\n  Filing-Company Relationships:")
        
        # Get all relationships with details
        fc_rels = session.query(FilingCompany).join(SECFiling).join(Company).all()
        
        for rel in fc_rels[:5]:  # Show first 5
            filing = rel.filing
            company = rel.company
            print(f"    - {filing.accession_number} ({filing.filing_type}, {filing.filing_date})")
            print(f"      → {company.name}")
            print(f"      Filing ID: {filing.filing_id}")
            print(f"      Company ID: {company.company_id}")
            print(f"      ✅ Valid foreign keys")
    
    # Filing-Drug relationship details
    if fd_rel_count > 0:
        print(f"\n  Filing-Drug Relationships:")
        
        fd_rels = session.query(FilingDrug).join(SECFiling).join(Drug).all()
        
        for rel in fd_rels[:5]:  # Show first 5
            filing = rel.filing
            drug = rel.drug
            print(f"    - {filing.accession_number}")
            print(f"      → {drug.primary_name}")
            print(f"      Mention type: {rel.mention_type}")
            print(f"      ✅ Valid relationship")
    else:
        print(f"\n  Filing-Drug Relationships: None (expected if no drug names found in filings)")
    
    # ============================================================
    # 8. CONSTRAINT VALIDATION
    # ============================================================
    print("\n🔒 CONSTRAINT VALIDATION:")
    
    # Check for duplicate Filing-Company relationships
    duplicate_fc = session.query(
        FilingCompany.filing_id,
        FilingCompany.company_id,
        func.count().label('count')
    ).group_by(
        FilingCompany.filing_id,
        FilingCompany.company_id
    ).having(func.count() > 1).all()
    
    print(f"  Duplicate Filing-Company relationships: {len(duplicate_fc)}")
    
    # Check for duplicate Filing-Drug relationships
    duplicate_fd = session.query(
        FilingDrug.filing_id,
        FilingDrug.drug_id,
        func.count().label('count')
    ).group_by(
        FilingDrug.filing_id,
        FilingDrug.drug_id
    ).having(func.count() > 1).all()
    
    print(f"  Duplicate Filing-Drug relationships: {len(duplicate_fd)}")
    
    # Check for duplicate accession numbers
    duplicate_accessions = session.query(
        SECFiling.accession_number,
        func.count().label('count')
    ).group_by(SECFiling.accession_number).having(func.count() > 1).all()
    
    print(f"  Duplicate accession numbers: {len(duplicate_accessions)}")
    
    # ============================================================
    # 9. WIRING FLOW VERIFICATION
    # ============================================================
    print("\n🔄 WIRING FLOW VERIFICATION:")
    
    # Check end-to-end flow for a sample record
    sample_staging = session.query(StagingRawData).filter_by(
        source_system='sec_edgar',
        processed=True
    ).first()
    
    if sample_staging:
        print(f"  Sample record flow:")
        print(f"    Staging ID: {sample_staging.staging_id}")
        print(f"    Source identifier: {sample_staging.source_record_id}")
        print(f"    Processed: {sample_staging.processed}")
        
        # Find corresponding filing
        filing = session.query(SECFiling).filter_by(
            accession_number=sample_staging.source_record_id
        ).first()
        
        if filing:
            print(f"    ✅ Corresponding filing found: {filing.filing_id}")
            
            # Check for company relationship
            fc_rel = session.query(FilingCompany).filter_by(
                filing_id=filing.filing_id
            ).first()
            
            if fc_rel:
                print(f"    ✅ Company relationship exists: {fc_rel.company.name}")
            else:
                print(f"    ⚠️  No company relationship found")
        else:
            print(f"    ⚠️  No corresponding filing found")
    
    # ============================================================
    # 10. SUMMARY & RECOMMENDATIONS
    # ============================================================
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    
    issues_found = []
    
    if orphaned_fc > 0 or orphaned_fd > 0:
        issues_found.append(f"Orphaned relationships: {orphaned_fc + orphaned_fd}")
    
    if filings_without_company > 0:
        issues_found.append(f"Filings without company relationships: {filings_without_company}")
    
    if null_filing_dates > 0 or null_accession_numbers > 0:
        issues_found.append(f"Null required fields in filings")
    
    if invalid_filing_types > 0:
        issues_found.append(f"Invalid filing types: {invalid_filing_types}")
    
    if len(duplicate_fc) > 0 or len(duplicate_fd) > 0:
        issues_found.append(f"Duplicate relationships detected")
    
    if issues_found:
        print("\n⚠️  ISSUES FOUND:")
        for issue in issues_found:
            print(f"  - {issue}")
    else:
        print("\n✅ NO ISSUES FOUND - All relationships and wiring are correct!")
    
    print(f"\n📊 Overall Statistics:")
    print(f"  - Processing success rate: {staging_processed/staging_total*100:.1f}%" if staging_total > 0 else "N/A")
    print(f"  - Relationship coverage: {filings_with_companies}/{filing_count} filings have company relationships")
    print(f"  - Data quality: {'✅ PASS' if not issues_found else '⚠️  ISSUES DETECTED'}")
    
    print("\n" + "=" * 70)

