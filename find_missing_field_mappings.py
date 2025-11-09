"""
Comprehensive search for missing field mappings between extracted context and database fields.

Principle: Fields extracted into ExtractedEntity.context but not mapped in _build_entity_data()
"""
import sys
from pathlib import Path
import ast
import re

sys.path.insert(0, str(Path(__file__).parent))

# Database model fields (from models)
MODEL_FIELDS = {
    'ClinicalTrial': [
        'nct_id', 'eudract_number', 'trial_title', 'phase', 'phase_numeric',
        'study_type', 'enrollment_target', 'enrollment_actual',
        'registration_date', 'start_date', 'primary_completion_date', 'completion_date',
        'status', 'status_verified_date', 'why_stopped',
        'allocation', 'intervention_model', 'masking', 'primary_purpose',
        'primary_endpoints', 'secondary_endpoints', 'study_locations',
        'results_posted', 'results_summary', 'results_url', 'sponsor_type'
    ],
    'Drug': [
        'drug_id', 'primary_name', 'generic_name', 'code_name', 'aliases',
        'drug_type', 'mechanism_of_action', 'indications', 'data_sources'
    ],
    'Company': [
        'company_id', 'name', 'ticker', 'founded_date', 'defunct_date',
        'status', 'legal_entity_status', 'headquarters_location', 'company_type'
    ],
    'Publication': [
        'pub_id', 'title', 'pmid', 'doi', 'pmcid', 'publication_date',
        'journal', 'abstract', 'publication_type', 'is_clinical_trial_result'
    ],
    'Patent': [
        'patent_id', 'patent_number', 'patent_office', 'title',
        'filing_date', 'publication_date', 'grant_date', 'expiration_date',
        'status', 'assignees'
    ],
    'SECFiling': [
        'filing_id', 'filing_type', 'filing_date', 'accession_number',
        'filing_url', 'full_text', 'mentions_milestones', 'mentions_restructuring',
        'cash_position', 'runway_months'
    ],
    'RegulatoryEvent': [
        'event_id', 'event_type', 'event_date', 'regulatory_body',
        'country', 'application_number', 'approval_type', 'description', 'document_url'
    ],
    'Institution': [
        'institution_id', 'name', 'institution_type', 'country'
    ],
    'Disease': [
        'disease_id', 'disease_name'
    ],
    'Target': [
        'target_id', 'gene_symbol', 'target_name', 'target_type'
    ]
}

def extract_context_fields_from_processor(file_path):
    """Extract all context fields set in processors."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find all context dictionaries
    context_fields = set()
    
    # Pattern: context={...} or context.get(...)
    # Look for context dict assignments
    pattern = r"context\s*=\s*\{([^}]+)\}"
    matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
    
    for match in matches:
        context_content = match.group(1)
        # Extract keys from context dict
        key_pattern = r"['\"]([^'\"]+)['\"]\s*:"
        keys = re.findall(key_pattern, context_content)
        context_fields.update(keys)
    
    return context_fields

def extract_mapped_fields_from_pipeline():
    """Extract fields mapped in _build_entity_data."""
    pipeline_file = Path('src/processing/pipeline.py')
    with open(pipeline_file, 'r') as f:
        content = f.read()
    
    # Find _build_entity_data method
    pattern = r"elif model\.__name__ == '(\w+)':(.*?)(?=elif|return data)"
    matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
    
    mapped_fields = {}
    for match in matches:
        model_name = match.group(1)
        block = match.group(2)
        
        # Extract data['field'] assignments
        field_pattern = r"data\['([^']+)'\]"
        fields = re.findall(field_pattern, block)
        mapped_fields[model_name] = set(fields)
    
    return mapped_fields

def find_missing_mappings():
    """Find fields in context but not mapped to database."""
    print("="*70)
    print("COMPREHENSIVE MISSING FIELD MAPPING ANALYSIS")
    print("="*70)
    
    # Get mapped fields from pipeline
    mapped_fields = extract_mapped_fields_from_pipeline()
    
    # Check each processor
    processors = [
        ('ClinicalTrialsProcessor', 'src/processors/clinicaltrials_processor.py', 'ClinicalTrial'),
        ('PubMedProcessor', 'src/processors/pubmed_processor.py', 'Publication'),
        ('OpenFDAProcessor', 'src/processors/openfda_processor.py', 'Drug'),
        ('PatentsViewProcessor', 'src/processors/patentsview_processor.py', 'Patent'),
        ('SECFilingsProcessor', 'src/processors/sec_filings_processor.py', 'SECFiling'),
        ('FDADrugsProcessor', 'src/processors/fda_drugs_processor.py', 'RegulatoryEvent'),
    ]
    
    issues_found = []
    
    for proc_name, proc_file, model_name in processors:
        proc_path = Path(proc_file)
        if not proc_path.exists():
            continue
        
        print(f"\n{proc_name} -> {model_name}:")
        print("-" * 70)
        
        # Get context fields from processor
        context_fields = extract_context_fields_from_processor(proc_path)
        
        # Get mapped fields for this model
        mapped = mapped_fields.get(model_name, set())
        
        # Get database fields for this model
        db_fields = set(MODEL_FIELDS.get(model_name, []))
        
        # Find context fields that exist in DB but not mapped
        missing_mappings = []
        for field in context_fields:
            # Check if field exists in database model
            if field in db_fields and field not in mapped:
                missing_mappings.append(field)
        
        if missing_mappings:
            print(f"  ❌ Missing mappings: {missing_mappings}")
            issues_found.append({
                'processor': proc_name,
                'model': model_name,
                'missing': missing_mappings
            })
        else:
            print(f"  ✅ All context fields mapped")
    
    return issues_found

if __name__ == "__main__":
    issues = find_missing_mappings()
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    if issues:
        print(f"\nFound {len(issues)} processors with missing field mappings:")
        for issue in issues:
            print(f"\n  {issue['processor']} ({issue['model']}):")
            for field in issue['missing']:
                print(f"    - {field}")
    else:
        print("\n✅ No missing field mappings found!")

