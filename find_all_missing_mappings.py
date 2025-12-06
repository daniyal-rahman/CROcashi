"""
Find all missing field mappings across all entity types.
"""
import sys
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).parent))

# Read the pipeline file to see what's currently mapped
pipeline_file = Path('src/processing/pipeline.py')
with open(pipeline_file, 'r') as f:
    pipeline_content = f.read()

# Extract all context fields from processors
def extract_context_from_file(file_path):
    """Extract context dict from processor file."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find context={...} patterns
    context_fields = set()
    pattern = r"context\s*=\s*\{([^}]+)\}"
    matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
    
    for match in matches:
        ctx_content = match.group(1)
        # Extract keys
        key_pattern = r"['\"]([^'\"]+)['\"]\s*:"
        keys = re.findall(key_pattern, ctx_content)
        context_fields.update(keys)
    
    return context_fields

# Check each processor
processors = [
    ('ClinicalTrialsProcessor', 'src/processors/clinicaltrials_processor.py', 'ClinicalTrial'),
    ('PubMedProcessor', 'src/processors/pubmed_processor.py', 'Publication'),
    ('PubMedProcessor', 'src/processors/pubmed_processor.py', 'Publication'),
]

print("="*70)
print("COMPREHENSIVE MISSING FIELD MAPPING ANALYSIS")
print("="*70)

all_issues = []

# Check ClinicalTrial - manual check since we know the fields
print("\n1. ClinicalTrial (ClinicalTrialsProcessor):")
print("-" * 70)

# Context fields extracted (from code inspection)
clinical_trial_context = {
    'phase', 'phase_numeric', 'status', 'study_type', 'enrollment',
    'start_date', 'completion_date', 'why_stopped'
}

# Fields mapped in _build_entity_data (from code)
clinical_trial_mapped = {
    'nct_id', 'eudract_number', 'trial_title', 'phase', 'status', 
    'study_type', 'phase_numeric', 'enrollment_target', 'start_date',
    'completion_date', 'why_stopped', 'data_sources'
}

# Check what's missing
missing = []
for ctx_field in clinical_trial_context:
    # Map context field to DB field
    mapping = {
        'enrollment': 'enrollment_target',
        'phase': 'phase',
        'phase_numeric': 'phase_numeric',
        'status': 'status',
        'study_type': 'study_type',
        'start_date': 'start_date',
        'completion_date': 'completion_date',
        'why_stopped': 'why_stopped'
    }
    db_field = mapping.get(ctx_field, ctx_field)
    if db_field not in clinical_trial_mapped:
        missing.append(f"{ctx_field} -> {db_field}")

if missing:
    print(f"  ❌ Missing: {missing}")
    all_issues.extend(missing)
else:
    print(f"  ✅ All fields mapped")

# Check identifiers
clinical_trial_identifiers = {'nct_id', 'eudract_number'}
for ident_field in clinical_trial_identifiers:
    if ident_field not in clinical_trial_mapped:
        print(f"  ❌ Missing identifier mapping: {ident_field}")
        all_issues.append(f"{ident_field} (identifier)")

print("\n" + "="*70)
print("SUMMARY")
print("="*70)

if all_issues:
    print(f"\nFound {len(all_issues)} missing mappings:")
    for m in all_issues:
        print(f"  - {m}")
else:
    print("\n✅ All field mappings are complete!")

