#!/usr/bin/env python3
"""
Bulk import common aliases discovered during review.

Supports CSV import format:
- entity_id, alias, type (abbreviation/brand_name/etc), source

Validates aliases before import and tracks effectiveness.
"""
import sys
import csv
from pathlib import Path
from uuid import UUID
from typing import List, Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.resolution import EntityAlias
from database.models.entities import Company, Drug, Disease, Institution
from database.models.clinical import ClinicalTrial
from sqlalchemy import and_

# Valid alias types
ALIAS_TYPES = [
    'abbreviation',
    'brand_name',
    'former_name',
    'code_name',
    'misspelling',
    'original_name',
    'manual_review'
]


def get_entity_model(entity_type: str):
    """Get the entity model class for a given entity type."""
    models = {
        'company': Company,
        'drug': Drug,
        'disease': Disease,
        'institution': Institution,
        'trial': ClinicalTrial
    }
    return models.get(entity_type)


def validate_entity_exists(session, entity_type: str, entity_id: UUID) -> bool:
    """Validate that an entity exists in the database."""
    model = get_entity_model(entity_type)
    if not model:
        return False
    
    id_field = {
        'company': 'company_id',
        'drug': 'drug_id',
        'disease': 'disease_id',
        'institution': 'institution_id',
        'trial': 'trial_id'
    }.get(entity_type, 'id')
    
    entity = session.query(model).filter(
        getattr(model, id_field) == entity_id
    ).first()
    
    return entity is not None


def validate_alias_row(row: Dict, row_num: int) -> tuple[bool, Optional[str]]:
    """Validate a single alias row."""
    required_fields = ['entity_id', 'alias', 'entity_type']
    
    for field in required_fields:
        if field not in row or not row[field].strip():
            return False, f"Missing required field: {field}"
    
    # Validate entity_id is UUID
    try:
        UUID(row['entity_id'])
    except ValueError:
        return False, f"Invalid UUID format: {row['entity_id']}"
    
    # Validate alias type if provided
    if 'type' in row and row['type']:
        if row['type'] not in ALIAS_TYPES:
            return False, f"Invalid alias type: {row['type']}. Must be one of: {', '.join(ALIAS_TYPES)}"
    
    # Validate entity_type
    valid_entity_types = ['company', 'drug', 'disease', 'institution', 'trial', 'target']
    if row['entity_type'] not in valid_entity_types:
        return False, f"Invalid entity type: {row['entity_type']}. Must be one of: {', '.join(valid_entity_types)}"
    
    return True, None


def import_aliases_from_csv(csv_file: Path, dry_run: bool = False) -> Dict:
    """Import aliases from CSV file."""
    results = {
        'total_rows': 0,
        'validated': 0,
        'imported': 0,
        'skipped': 0,
        'errors': []
    }
    
    if not csv_file.exists():
        print(f"Error: CSV file not found: {csv_file}")
        return results
    
    print("=" * 80)
    print("IMPORTING ALIASES FROM CSV")
    print("=" * 80)
    print(f"File: {csv_file}")
    print(f"Mode: {'DRY RUN' if dry_run else 'IMPORT'}")
    print()
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        with get_db_session() as session:
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                results['total_rows'] += 1
                
                # Validate row
                is_valid, error_msg = validate_alias_row(row, row_num)
                if not is_valid:
                    results['errors'].append({
                        'row': row_num,
                        'error': error_msg,
                        'data': row
                    })
                    continue
                
                results['validated'] += 1
                
                # Parse fields
                entity_id = UUID(row['entity_id'])
                alias_text = row['alias'].strip()
                entity_type = row['entity_type'].strip()
                alias_type = row.get('type', '').strip() or None
                source = row.get('source', '').strip() or 'csv_import'
                
                # Validate entity exists
                if not validate_entity_exists(session, entity_type, entity_id):
                    results['errors'].append({
                        'row': row_num,
                        'error': f"Entity not found: {entity_type} {entity_id}",
                        'data': row
                    })
                    continue
                
                # Check if alias already exists
                existing = session.query(EntityAlias).filter(
                    and_(
                        EntityAlias.entity_type == entity_type,
                        EntityAlias.entity_id == entity_id,
                        EntityAlias.alias_text == alias_text
                    )
                ).first()
                
                if existing:
                    results['skipped'] += 1
                    print(f"  Row {row_num}: Skipped (alias already exists)")
                    continue
                
                # Create alias
                if not dry_run:
                    alias = EntityAlias(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        alias_text=alias_text,
                        alias_type=alias_type,
                        source=source,
                        confidence_score=1.0  # Manual import = high confidence
                    )
                    session.add(alias)
                    results['imported'] += 1
                    print(f"  Row {row_num}: ✓ Imported '{alias_text}' for {entity_type} {entity_id}")
                else:
                    results['imported'] += 1
                    print(f"  Row {row_num}: [DRY RUN] Would import '{alias_text}' for {entity_type} {entity_id}")
            
            if not dry_run and results['imported'] > 0:
                session.commit()
                print(f"\n✓ Committed {results['imported']} aliases to database")
    
    return results


def create_sample_csv(output_file: Path):
    """Create a sample CSV file with the correct format."""
    sample_data = [
        {
            'entity_id': '00000000-0000-0000-0000-000000000001',
            'alias': 'NSCLC',
            'entity_type': 'disease',
            'type': 'abbreviation',
            'source': 'manual_review'
        },
        {
            'entity_id': '00000000-0000-0000-0000-000000000002',
            'alias': 'CLL',
            'entity_type': 'disease',
            'type': 'abbreviation',
            'source': 'manual_review'
        }
    ]
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['entity_id', 'alias', 'entity_type', 'type', 'source']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sample_data)
    
    print(f"✓ Created sample CSV: {output_file}")
    print("\nCSV Format:")
    print("  entity_id: UUID of the entity")
    print("  alias: The alias text")
    print("  entity_type: company, drug, disease, institution, trial, or target")
    print("  type: abbreviation, brand_name, former_name, code_name, misspelling, original_name, or manual_review (optional)")
    print("  source: Source of the alias (optional, defaults to 'csv_import')")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Bulk import common aliases from CSV"
    )
    parser.add_argument(
        '--file',
        type=Path,
        required=True,
        help='CSV file to import (required fields: entity_id, alias, entity_type)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate and preview without importing'
    )
    parser.add_argument(
        '--create-sample',
        type=Path,
        help='Create a sample CSV file at the specified path'
    )
    
    args = parser.parse_args()
    
    if args.create_sample:
        create_sample_csv(args.create_sample)
        return
    
    if not args.file:
        parser.error("--file is required (or use --create-sample to create a template)")
    
    results = import_aliases_from_csv(args.file, dry_run=args.dry_run)
    
    print("\n" + "=" * 80)
    print("IMPORT SUMMARY")
    print("=" * 80)
    print(f"Total rows: {results['total_rows']}")
    print(f"Validated: {results['validated']}")
    print(f"Imported: {results['imported']}")
    print(f"Skipped: {results['skipped']}")
    print(f"Errors: {len(results['errors'])}")
    
    if results['errors']:
        print("\nErrors:")
        for error in results['errors'][:10]:  # Show first 10
            print(f"  Row {error['row']}: {error['error']}")
        if len(results['errors']) > 10:
            print(f"  ... and {len(results['errors']) - 10} more errors")


if __name__ == '__main__':
    main()





