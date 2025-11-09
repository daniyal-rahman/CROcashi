"""
Analyze review candidates to determine if they should match.

This script helps identify:
1. Cases that should definitely match (false negatives)
2. Cases that correctly need review (true positives)
3. Patterns that could improve matching
"""
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models import EntityMatchCandidate
from database.models.entities import Drug, Disease, Company
from src.entity_resolution.review_interface import ReviewInterface


def analyze_review_candidates():
    """Analyze candidates in review queue."""
    print("\n" + "="*70)
    print("REVIEW CANDIDATE ANALYSIS")
    print("="*70)
    
    with get_db_session() as session:
        review_interface = ReviewInterface(session)
        
        # Get all pending reviews
        candidates = review_interface.get_pending_reviews(limit=100)
        
        print(f"\nTotal candidates needing review: {len(candidates)}")
        
        # Analyze by type
        by_type = {}
        for candidate in candidates:
            by_type[candidate.entity_type] = by_type.get(candidate.entity_type, 0) + 1
        
        print(f"\nBy entity type:")
        for etype, count in sorted(by_type.items()):
            print(f"  {etype}: {count}")
        
        # Analyze specific cases
        print("\n" + "="*70)
        print("DETAILED ANALYSIS")
        print("="*70)
        
        should_match = []
        should_not_match = []
        unclear = []
        
        for candidate in candidates[:30]:  # Analyze first 30
            analysis = analyze_candidate(session, candidate)
            
            if analysis['should_match'] == 'YES':
                should_match.append((candidate, analysis))
            elif analysis['should_match'] == 'NO':
                should_not_match.append((candidate, analysis))
            else:
                unclear.append((candidate, analysis))
        
        print(f"\nAnalysis of first 30 candidates:")
        print(f"  Should match: {len(should_match)}")
        print(f"  Should NOT match: {len(should_not_match)}")
        print(f"  Unclear: {len(unclear)}")
        
        # Show examples
        if should_match:
            print("\n" + "-"*70)
            print("SHOULD MATCH (False Negatives):")
            print("-"*70)
            for candidate, analysis in should_match[:5]:
                print(f"\n  Candidate: \"{candidate.extracted_text}\"")
                print(f"  Type: {candidate.entity_type}")
                print(f"  Confidence: {candidate.match_confidence:.2f}")
                if analysis.get('matched_entity'):
                    print(f"  Matched entity: \"{analysis['matched_entity']}\"")
                print(f"  Reason: {analysis['reason']}")
        
        if should_not_match:
            print("\n" + "-"*70)
            print("CORRECTLY FLAGGED (True Positives):")
            print("-"*70)
            for candidate, analysis in should_not_match[:5]:
                print(f"\n  Candidate: \"{candidate.extracted_text}\"")
                print(f"  Type: {candidate.entity_type}")
                print(f"  Confidence: {candidate.match_confidence:.2f}")
                if analysis.get('matched_entity'):
                    print(f"  Matched entity: \"{analysis['matched_entity']}\"")
                print(f"  Reason: {analysis['reason']}")
        
        # Pattern analysis
        print("\n" + "="*70)
        print("PATTERN ANALYSIS")
        print("="*70)
        
        patterns = analyze_patterns(candidates)
        
        print(f"\nCommon patterns:")
        for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {pattern}: {count} cases")
        
        return {
            'total': len(candidates),
            'should_match': len(should_match),
            'should_not_match': len(should_not_match),
            'unclear': len(unclear),
            'patterns': patterns
        }


def analyze_candidate(session, candidate):
    """Analyze a single candidate to determine if it should match."""
    extracted = candidate.extracted_text.lower().strip()
    
    if not candidate.potential_matches:
        return {
            'should_match': 'NO',
            'reason': 'No potential matches found',
            'matched_entity': None
        }
    
    # Get the top match
    top_match = candidate.potential_matches[0]
    match_id = UUID(top_match['entity_id'])
    
    # Get the matched entity
    matched_entity = None
    matched_name = None
    
    if candidate.entity_type == 'drug':
        entity = session.query(Drug).filter_by(drug_id=match_id).first()
        if entity:
            matched_entity = entity
            matched_name = entity.primary_name.lower().strip()
    elif candidate.entity_type == 'disease':
        entity = session.query(Disease).filter_by(disease_id=match_id).first()
        if entity:
            matched_entity = entity
            matched_name = entity.disease_name.lower().strip()
    elif candidate.entity_type == 'company':
        entity = session.query(Company).filter_by(company_id=match_id).first()
        if entity:
            matched_entity = entity
            matched_name = entity.name.lower().strip()
    
    if not matched_entity:
        return {
            'should_match': 'UNKNOWN',
            'reason': 'Matched entity not found',
            'matched_entity': None
        }
    
    # Check if they should match
    # Case 1: Exact match (case-insensitive)
    if extracted == matched_name:
        return {
            'should_match': 'YES',
            'reason': 'Exact match (case-insensitive)',
            'matched_entity': matched_entity.primary_name if hasattr(matched_entity, 'primary_name') else matched_entity.name if hasattr(matched_entity, 'name') else matched_entity.disease_name
        }
    
    # Case 2: One contains the other (for drugs)
    if candidate.entity_type == 'drug':
        if extracted in matched_name or matched_name in extracted:
            # Check if it's a different formulation
            if 'nab-' in matched_name and 'nab-' not in extracted:
                return {
                    'should_match': 'NO',
                    'reason': 'Different formulation (nab-paclitaxel vs paclitaxel)',
                    'matched_entity': matched_entity.primary_name
                }
            elif 'albumin' in matched_name.lower() and 'albumin' not in extracted:
                return {
                    'should_match': 'NO',
                    'reason': 'Different formulation (albumin-bound vs standard)',
                    'matched_entity': matched_entity.primary_name
                }
            else:
                return {
                    'should_match': 'MAYBE',
                    'reason': 'One contains the other - may be same drug',
                    'matched_entity': matched_entity.primary_name
                }
    
    # Case 3: Very similar (high confidence but flagged)
    if candidate.match_confidence >= 0.85:
        return {
            'should_match': 'MAYBE',
            'reason': f'High confidence ({candidate.match_confidence:.2f}) but flagged - likely should match',
            'matched_entity': matched_entity.primary_name if hasattr(matched_entity, 'primary_name') else matched_entity.name if hasattr(matched_entity, 'name') else matched_entity.disease_name
        }
    
    # Case 4: Contains extra text (e.g., "Continued Irinotecan Hydrochloride (HCI) Treatment")
    if candidate.entity_type == 'drug':
        # Extract base drug name
        base_extracted = extracted.split()[0] if extracted.split() else extracted
        base_matched = matched_name.split()[0] if matched_name.split() else matched_name
        
        if base_extracted == base_matched:
            return {
                'should_match': 'YES',
                'reason': 'Base drug name matches (extracted has extra text)',
                'matched_entity': matched_entity.primary_name
            }
    
    # Default: unclear
    return {
        'should_match': 'UNKNOWN',
        'reason': f'Similarity: {candidate.match_confidence:.2f} - needs manual review',
        'matched_entity': matched_entity.primary_name if hasattr(matched_entity, 'primary_name') else matched_entity.name if hasattr(matched_entity, 'name') else matched_entity.disease_name
    }


def analyze_patterns(candidates):
    """Identify patterns in review candidates."""
    patterns = {}
    
    for candidate in candidates:
        text = candidate.extracted_text.lower()
        
        # Pattern: Case sensitivity
        if text.isupper() or text.islower():
            patterns['Case sensitivity'] = patterns.get('Case sensitivity', 0) + 1
        
        # Pattern: Contains "continued" or "treatment"
        if 'continued' in text or 'treatment' in text:
            patterns['Contains treatment descriptor'] = patterns.get('Contains treatment descriptor', 0) + 1
        
        # Pattern: Contains dosage info
        if any(char.isdigit() for char in text) and ('mg' in text or 'ml' in text):
            patterns['Contains dosage'] = patterns.get('Contains dosage', 0) + 1
        
        # Pattern: Contains comparator label
        if 'comparator:' in text.lower():
            patterns['Comparator label'] = patterns.get('Comparator label', 0) + 1
        
        # Pattern: Stage/grade information
        if 'stage' in text or 'grade' in text:
            patterns['Contains stage/grade'] = patterns.get('Contains stage/grade', 0) + 1
    
    return patterns


if __name__ == "__main__":
    results = analyze_review_candidates()
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Total candidates: {results['total']}")
    print(f"Should match: {results['should_match']}")
    print(f"Correctly flagged: {results['should_not_match']}")
    print(f"Unclear: {results['unclear']}")
    print("="*70)

