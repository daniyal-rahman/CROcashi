#!/usr/bin/env python3
"""
Analyze review patterns to identify failure modes and improvement opportunities.

Identifies common patterns in rejected matches:
- Abbreviation mismatches
- Formulation differences
- Stage variations
- Brand vs generic names
- Common false positives/negatives
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import re
from typing import Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.resolution import EntityMatchCandidate
from database.models.entities import Company, Drug, Disease, Institution
from database.models.clinical import ClinicalTrial
from sqlalchemy import func

# Set up output directory
output_dir = project_root / 'data' / 'pattern_analysis'
output_dir.mkdir(parents=True, exist_ok=True)


def get_entity_name(session, entity_type: str, entity_id) -> str:
    """Get entity name for analysis."""
    try:
        if entity_type == 'company':
            entity = session.query(Company).filter(Company.company_id == entity_id).first()
            return entity.name if entity else ''
        elif entity_type == 'drug':
            entity = session.query(Drug).filter(Drug.drug_id == entity_id).first()
            return entity.primary_name or entity.generic_name if entity else ''
        elif entity_type == 'disease':
            entity = session.query(Disease).filter(Disease.disease_id == entity_id).first()
            return entity.disease_name if entity else ''
        elif entity_type == 'institution':
            entity = session.query(Institution).filter(Institution.institution_id == entity_id).first()
            return entity.name if entity else ''
        elif entity_type == 'trial':
            entity = session.query(ClinicalTrial).filter(ClinicalTrial.trial_id == entity_id).first()
            return entity.trial_title if entity else ''
    except:
        pass
    return ''


def detect_abbreviation(text1: str, text2: str) -> bool:
    """Detect if one text is an abbreviation of the other."""
    text1_upper = text1.upper().strip()
    text2_upper = text2.upper().strip()
    
    # Check if one is all caps and shorter (likely abbreviation)
    if text1_upper == text1 and len(text1) < len(text2) and len(text1) <= 10:
        # Check if first letters match
        words2 = text2.split()
        if len(words2) > 1:
            abbrev = ''.join(w[0] for w in words2 if w)
            if text1_upper == abbrev:
                return True
    
    if text2_upper == text2 and len(text2) < len(text1) and len(text2) <= 10:
        words1 = text1.split()
        if len(words1) > 1:
            abbrev = ''.join(w[0] for w in words1 if w)
            if text2_upper == abbrev:
                return True
    
    return False


def detect_formulation_diff(text1: str, text2: str) -> bool:
    """Detect formulation differences (tablet vs injection, etc.)."""
    formulations = [
        ('tablet', 'injection'), ('tablet', 'capsule'), ('tablet', 'oral'),
        ('injection', 'infusion'), ('iv', 'oral'), ('subcutaneous', 'iv'),
        ('nab-', 'paclitaxel'), ('liposomal', 'doxorubicin')
    ]
    
    text1_lower = text1.lower()
    text2_lower = text2.lower()
    
    for form1, form2 in formulations:
        if (form1 in text1_lower and form2 in text2_lower) or \
           (form2 in text1_lower and form1 in text2_lower):
            return True
    
    return False


def detect_stage_variation(text1: str, text2: str) -> bool:
    """Detect stage/progression variations."""
    stage_patterns = [
        r'stage\s+[ivx]+',
        r'stage\s+\d+',
        r'advanced',
        r'early',
        r'metastatic',
        r'localized'
    ]
    
    text1_lower = text1.lower()
    text2_lower = text2.lower()
    
    stages1 = [p for p in stage_patterns if re.search(p, text1_lower)]
    stages2 = [p for p in stage_patterns if re.search(p, text2_lower)]
    
    # If both have stage info but different
    if stages1 and stages2 and stages1 != stages2:
        return True
    
    return False


def analyze_rejected_candidates(days: int = 7) -> Dict:
    """Analyze rejected candidates to identify patterns."""
    cutoff_date = datetime.now().date() - timedelta(days=days)
    
    with get_db_session() as session:
        # Get rejected candidates
        rejected = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.status == 'new_entity',
            EntityMatchCandidate.reviewed_at >= cutoff_date,
            EntityMatchCandidate.deleted_at.is_(None),
            EntityMatchCandidate.potential_matches.isnot(None)
        ).all()
        
        patterns = {
            'abbreviations': [],
            'formulations': [],
            'stages': [],
            'short_text': [],
            'navigation_text': [],
            'low_confidence': [],
            'no_matches': [],
            'multiple_matches': []
        }
        
        for candidate in rejected:
            extracted = candidate.extracted_text or ''
            potential_matches = candidate.potential_matches or []
            confidence = float(candidate.match_confidence) if candidate.match_confidence else 0.0
            
            # Analyze top match if available
            if potential_matches:
                top_match = potential_matches[0]
                entity_id = top_match.get('entity_id')
                if entity_id:
                    entity_name = get_entity_name(session, candidate.entity_type, entity_id)
                    
                    if entity_name:
                        # Check for abbreviation
                        if detect_abbreviation(extracted, entity_name):
                            patterns['abbreviations'].append({
                                'extracted': extracted,
                                'entity_name': entity_name,
                                'entity_type': candidate.entity_type,
                                'source': candidate.source_name
                            })
                        
                        # Check for formulation difference
                        if detect_formulation_diff(extracted, entity_name):
                            patterns['formulations'].append({
                                'extracted': extracted,
                                'entity_name': entity_name,
                                'entity_type': candidate.entity_type,
                                'source': candidate.source_name
                            })
                        
                        # Check for stage variation
                        if detect_stage_variation(extracted, entity_name):
                            patterns['stages'].append({
                                'extracted': extracted,
                                'entity_name': entity_name,
                                'entity_type': candidate.entity_type,
                                'source': candidate.source_name
                            })
            
            # Check for short text
            if len(extracted.strip()) < 5:
                patterns['short_text'].append({
                    'extracted': extracted,
                    'entity_type': candidate.entity_type,
                    'source': candidate.source_name
                })
            
            # Check for navigation/header text
            nav_terms = ['back to', 'go to', 'search', 'browse', 'guidance:', 'system limitation']
            if any(term in extracted.lower() for term in nav_terms):
                patterns['navigation_text'].append({
                    'extracted': extracted,
                    'entity_type': candidate.entity_type,
                    'source': candidate.source_name
                })
            
            # Low confidence
            if confidence < 0.70:
                patterns['low_confidence'].append({
                    'extracted': extracted,
                    'confidence': confidence,
                    'entity_type': candidate.entity_type,
                    'source': candidate.source_name
                })
            
            # No matches
            if not potential_matches:
                patterns['no_matches'].append({
                    'extracted': extracted,
                    'entity_type': candidate.entity_type,
                    'source': candidate.source_name
                })
            
            # Multiple matches
            if len(potential_matches) > 1:
                patterns['multiple_matches'].append({
                    'extracted': extracted,
                    'num_matches': len(potential_matches),
                    'entity_type': candidate.entity_type,
                    'source': candidate.source_name
                })
        
        return patterns


def generate_recommendations(patterns: Dict) -> List[str]:
    """Generate recommendations based on patterns."""
    recommendations = []
    
    if len(patterns['abbreviations']) > 10:
        recommendations.append(
            f"Add abbreviation detection: Found {len(patterns['abbreviations'])} abbreviation cases. "
            "Consider adding abbreviation dictionary or pattern matching."
        )
    
    if len(patterns['formulations']) > 5:
        recommendations.append(
            f"Handle formulation differences: Found {len(patterns['formulations'])} formulation variations. "
            "These should typically NOT match (e.g., tablet vs injection). Current behavior is correct."
        )
    
    if len(patterns['stages']) > 5:
        recommendations.append(
            f"Handle stage variations: Found {len(patterns['stages'])} stage/progression differences. "
            "Consider normalizing stage information before matching."
        )
    
    if len(patterns['navigation_text']) > 5:
        recommendations.append(
            f"Improve extraction: Found {len(patterns['navigation_text'])} navigation/header text cases. "
            "Improve entity extraction to filter out non-entity text."
        )
    
    if len(patterns['short_text']) > 10:
        recommendations.append(
            f"Filter short text: Found {len(patterns['short_text'])} very short extracted texts. "
            "Add minimum length validation in extraction phase."
        )
    
    if len(patterns['low_confidence']) > 20:
        recommendations.append(
            f"Review confidence thresholds: Found {len(patterns['low_confidence'])} low confidence matches. "
            "Consider adjusting confidence scoring or thresholds."
        )
    
    return recommendations


def display_pattern_analysis(patterns: Dict, recommendations: List[str]):
    """Display pattern analysis results."""
    print("=" * 80)
    print("REVIEW PATTERN ANALYSIS")
    print("=" * 80)
    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    print("## PATTERN SUMMARY")
    print("-" * 80)
    print(f"Abbreviation cases: {len(patterns['abbreviations'])}")
    print(f"Formulation differences: {len(patterns['formulations'])}")
    print(f"Stage variations: {len(patterns['stages'])}")
    print(f"Short text: {len(patterns['short_text'])}")
    print(f"Navigation/header text: {len(patterns['navigation_text'])}")
    print(f"Low confidence: {len(patterns['low_confidence'])}")
    print(f"No matches: {len(patterns['no_matches'])}")
    print(f"Multiple matches: {len(patterns['multiple_matches'])}")
    print()
    
    # Show examples
    if patterns['abbreviations']:
        print("## ABBREVIATION EXAMPLES")
        print("-" * 80)
        for ex in patterns['abbreviations'][:5]:
            print(f"  Extracted: {ex['extracted']}")
            print(f"  Entity: {ex['entity_name']}")
            print(f"  Type: {ex['entity_type']}, Source: {ex['source']}")
            print()
    
    if patterns['formulations']:
        print("## FORMULATION DIFFERENCE EXAMPLES")
        print("-" * 80)
        for ex in patterns['formulations'][:5]:
            print(f"  Extracted: {ex['extracted']}")
            print(f"  Entity: {ex['entity_name']}")
            print(f"  Type: {ex['entity_type']}, Source: {ex['source']}")
            print()
    
    # Recommendations
    if recommendations:
        print("## RECOMMENDATIONS")
        print("-" * 80)
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")
        print()


def export_pattern_analysis(patterns: Dict, recommendations: List[str]):
    """Export pattern analysis to file."""
    report_file = output_dir / f'pattern_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    
    import json
    report_data = {
        'generated_at': datetime.now().isoformat(),
        'pattern_counts': {
            'abbreviations': len(patterns['abbreviations']),
            'formulations': len(patterns['formulations']),
            'stages': len(patterns['stages']),
            'short_text': len(patterns['short_text']),
            'navigation_text': len(patterns['navigation_text']),
            'low_confidence': len(patterns['low_confidence']),
            'no_matches': len(patterns['no_matches']),
            'multiple_matches': len(patterns['multiple_matches'])
        },
        'examples': {
            'abbreviations': patterns['abbreviations'][:10],
            'formulations': patterns['formulations'][:10],
            'stages': patterns['stages'][:10]
        },
        'recommendations': recommendations
    }
    
    with open(report_file, 'w') as f:
        json.dump(report_data, f, indent=2, default=str)
    
    print(f"✓ Pattern analysis saved to {report_file}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Analyze review patterns to identify failure modes"
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to analyze (default: 7)'
    )
    parser.add_argument(
        '--export',
        action='store_true',
        help='Export analysis to file'
    )
    
    args = parser.parse_args()
    
    print(f"Analyzing patterns from last {args.days} days...")
    patterns = analyze_rejected_candidates(days=args.days)
    recommendations = generate_recommendations(patterns)
    
    display_pattern_analysis(patterns, recommendations)
    
    if args.export:
        export_pattern_analysis(patterns, recommendations)


if __name__ == '__main__':
    main()


