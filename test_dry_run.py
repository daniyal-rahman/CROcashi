#!/usr/bin/env python3
"""
Dry run test - validates code structure without database.

Tests code logic, imports, and data structures.
"""
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("ENTITY RESOLUTION SYSTEM - DRY RUN TEST")
print("=" * 80)

# Test 1: Imports
print("\n[1/7] Testing imports...")
try:
    from src.entity_resolution.types import (
        EntityType, ExtractedEntity, MatchMethod,
        ResolutionResult, ResolutionStatus
    )
    print("✓ Entity resolution types")
    
    from src.entity_resolution.base_processor import BaseProcessor
    print("✓ Base processor")
    
    from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
    from src.processors.fda_drugs_processor import FDADrugsProcessor
    print("✓ Source processors")
    
    print("✅ All imports successful")
except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Load sample data
print("\n[2/7] Loading sample data...")
ct_file = Path('data/raw/clinicaltrials_gov/clinicaltrials_gov_sample.json')
if not ct_file.exists():
    print(f"✗ Sample file not found: {ct_file}")
    sys.exit(1)

with open(ct_file) as f:
    ct_data = json.load(f)

studies = ct_data.get('studies', [])
print(f"✓ Loaded {len(studies)} clinical trials")

# Test 3: Test entity extraction (no database)
print("\n[3/7] Testing entity extraction...")

# Create a mock session object
class MockSession:
    def query(self, *args, **kwargs):
        return self
    def filter(self, *args, **kwargs):
        return self
    def first(self):
        return None
    def all(self):
        return []
    def execute(self, *args, **kwargs):
        class MockResult:
            def scalar(self):
                return 0.5  # Mock trigram similarity
            def fetchall(self):
                return []
        return MockResult()
    def add(self, *args, **kwargs):
        pass
    def commit(self):
        pass
    def rollback(self):
        pass

mock_session = MockSession()
processor = ClinicalTrialsProcessor(mock_session)

# Extract from first study
if studies:
    study = studies[0]
    nct_id = processor.get_source_identifier(study)
    print(f"✓ Source identifier: {nct_id}")
    
    entities = processor.extract_entities(study)
    print(f"✓ Extracted entities:")
    
    total_entities = 0
    for entity_type, entity_list in entities.items():
        if entity_list:
            total_entities += len(entity_list)
            print(f"  - {entity_type}: {len(entity_list)}")
            
            # Show first entity of each type
            if entity_list:
                first = entity_list[0]
                print(f"    Example: {first.name[:60] if len(first.name) > 60 else first.name}")
    
    print(f"✓ Total entities extracted: {total_entities}")
    
    if total_entities == 0:
        print("⚠️  Warning: No entities extracted. Check data structure.")
else:
    print("✗ No studies found in sample data")

# Test 4: Test entity extraction validation
print("\n[4/7] Testing entity validation...")
if entities:
    is_valid = processor.validate_extraction(entities)
    if is_valid:
        print("✓ Entity extraction passed validation")
    else:
        print("✗ Entity extraction failed validation")
        print(f"  Warnings: {processor.metrics.warnings}")

# Test 5: Test relationship extraction
print("\n[5/7] Testing relationship extraction...")
if studies:
    # Mock resolved entities
    resolved_entities = {
        'trial_0': 'mock-trial-uuid',
        'drug_0': 'mock-drug-uuid',
        'disease_0': 'mock-disease-uuid',
        'sponsor': 'mock-sponsor-uuid'
    }
    
    relationships = processor.extract_relationships(study, resolved_entities)
    print(f"✓ Extracted {len(relationships)} relationships")
    
    if relationships:
        rel_types = {}
        for rel in relationships:
            rel_types[rel.relationship_type] = rel_types.get(rel.relationship_type, 0) + 1
        
        print("  Relationship types:")
        for rel_type, count in rel_types.items():
            print(f"    - {rel_type}: {count}")

# Test 6: Test data structures
print("\n[6/7] Testing data structures...")

# Create test entity
test_entity = ExtractedEntity(
    entity_type=EntityType.DRUG,
    name="Test Drug",
    identifiers={'test_id': 'TEST001'},
    context={'company': 'Test Company'},
    source_name='test',
    source_identifier='test_001'
)
print(f"✓ Created ExtractedEntity: {test_entity.name}")

# Create test resolution result
test_result = ResolutionResult(
    status=ResolutionStatus.HIGH_CONFIDENCE,
    entity_id=None,
    confidence_score=0.92,
    match_method=MatchMethod.FUZZY_CONTEXT,
    reasoning="Test reasoning"
)
print(f"✓ Created ResolutionResult: {test_result.status.value}")

# Test 7: Test processor metrics
print("\n[7/7] Testing processor metrics...")
metrics = processor.get_metrics()
print(f"✓ Metrics collected:")
print(f"  - Entities extracted: {metrics.entities_extracted}")
print(f"  - Warnings: {len(metrics.warnings)}")
print(f"  - Errors: {len(metrics.errors)}")

if metrics.start_time and metrics.end_time:
    print(f"  - Duration: {metrics.duration_seconds:.2f}s")

# Summary
print("\n" + "=" * 80)
print("DRY RUN TEST SUMMARY")
print("=" * 80)

issues_found = []

if total_entities == 0:
    issues_found.append("No entities extracted from sample data")

if len(relationships) == 0:
    issues_found.append("No relationships extracted")

if issues_found:
    print("\n⚠️  ISSUES FOUND:")
    for issue in issues_found:
        print(f"  - {issue}")
    print("\nThese may be due to data format changes or extraction logic issues.")
    print("Check the processor implementation against actual data structure.")
else:
    print("\n✅ DRY RUN COMPLETED SUCCESSFULLY")
    print("\nAll code components are working correctly:")
    print("  ✓ Imports functional")
    print("  ✓ Data loading works")
    print("  ✓ Entity extraction works")
    print("  ✓ Relationship extraction works")
    print("  ✓ Data structures valid")

print("\n" + "=" * 80)
print("\nNEXT STEPS:")
print("\n1. Set up PostgreSQL database:")
print("   createdb biotech_kg")
print("\n2. Install dependencies:")
print("   python3 -m venv venv && source venv/bin/activate")
print("   pip install -r requirements.txt")
print("\n3. Run full integration test:")
print("   python3 test_integration.py")
print("\n4. See TESTING_INSTRUCTIONS.md for detailed testing guide")
print("")

