#!/usr/bin/env python3
"""
Automated batch review of match candidates using decision logic.

This script reviews candidates automatically based on confidence scores and match quality,
similar to manual_review_candidates.py but processes in batches and tracks progress.
"""
import sys
from pathlib import Path
import logging
from datetime import datetime
from uuid import UUID

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.resolution import EntityMatchCandidate
from database.models.entities import Company, Drug, Disease, Institution
from database.models.clinical import ClinicalTrial
from src.entity_resolution.review_interface import ReviewInterface

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def get_entity_details(session, entity_type: str, entity_id: UUID) -> dict:
    """Get details about an entity."""
    try:
        if entity_type == 'company':
            entity = session.query(Company).filter(Company.company_id == entity_id).first()
            if entity:
                return {'name': entity.name, 'ticker': entity.ticker, 'status': entity.status}
        elif entity_type == 'drug':
            entity = session.query(Drug).filter(Drug.drug_id == entity_id).first()
            if entity:
                return {'name': entity.primary_name, 'generic_name': entity.generic_name, 'drug_type': entity.drug_type}
        elif entity_type == 'disease':
            entity = session.query(Disease).filter(Disease.disease_id == entity_id).first()
            if entity:
                return {'name': entity.disease_name}
        elif entity_type == 'institution':
            entity = session.query(Institution).filter(Institution.institution_id == entity_id).first()
            if entity:
                return {'name': entity.name, 'institution_type': entity.institution_type}
        elif entity_type == 'trial':
            entity = session.query(ClinicalTrial).filter(ClinicalTrial.trial_id == entity_id).first()
            if entity:
                return {'title': entity.trial_title, 'nct_id': entity.nct_id, 'phase': entity.phase}
    except Exception as e:
        logger.error(f"Error getting entity details: {e}")
    
    return {}


def analyze_candidate(session, candidate: EntityMatchCandidate) -> dict:
    """Analyze a candidate and determine if it should be approved or rejected."""
    extracted_text = candidate.extracted_text or ''
    potential_matches = candidate.potential_matches or []
    confidence = float(candidate.match_confidence) if candidate.match_confidence else 0.0
    
    analysis = {
        'candidate_id': str(candidate.candidate_id),
        'entity_type': candidate.entity_type,
        'source_name': candidate.source_name,
        'extracted_text': extracted_text,
        'confidence': confidence,
        'potential_matches': [],
        'decision': None,
        'reasoning': '',
        'entity_id': None
    }
    
    # Get details for potential matches
    for match in potential_matches[:3]:  # Top 3 matches
        entity_id = UUID(match.get('entity_id', ''))
        score = match.get('score', 0.0)
        reason = match.get('reason', '')
        
        entity_details = get_entity_details(session, candidate.entity_type, entity_id)
        
        analysis['potential_matches'].append({
            'entity_id': str(entity_id),
            'score': score,
            'reason': reason,
            'details': entity_details
        })
    
    # Decision logic
    if not potential_matches:
        # No potential matches - likely a new entity
        analysis['decision'] = 'reject'
        analysis['reasoning'] = 'No potential matches found - create new entity'
    elif len(potential_matches) == 1:
        # Single match - check confidence
        match = potential_matches[0]
        score = match.get('score', 0.0)
        
        if score >= 0.85:
            # High confidence - approve
            analysis['decision'] = 'approve'
            analysis['entity_id'] = match.get('entity_id')
            analysis['reasoning'] = f'High confidence match (score: {score:.2f})'
        elif score >= 0.70:
            # Medium confidence - need to check if text matches
            entity_id = UUID(match.get('entity_id', ''))
            entity_details = get_entity_details(session, candidate.entity_type, entity_id)
            entity_name = entity_details.get('name', '') or entity_details.get('title', '') or entity_details.get('generic_name', '')
            
            # Check if extracted text is similar to entity name
            if entity_name and (extracted_text.lower() in entity_name.lower() or entity_name.lower() in extracted_text.lower()):
                analysis['decision'] = 'approve'
                analysis['entity_id'] = str(entity_id)
                analysis['reasoning'] = f'Medium confidence but text matches entity name (score: {score:.2f})'
            else:
                analysis['decision'] = 'reject'
                analysis['reasoning'] = f'Medium confidence but text does not match (score: {score:.2f})'
        else:
            # Low confidence - reject
            analysis['decision'] = 'reject'
            analysis['reasoning'] = f'Low confidence match (score: {score:.2f}) - create new entity'
    else:
        # Multiple matches - check best match
        best_match = potential_matches[0]
        score = best_match.get('score', 0.0)
        
        if score >= 0.85:
            # High confidence best match - approve
            analysis['decision'] = 'approve'
            analysis['entity_id'] = best_match.get('entity_id')
            analysis['reasoning'] = f'Multiple matches, best match has high confidence (score: {score:.2f})'
        else:
            # Low confidence or ambiguous - reject
            analysis['decision'] = 'reject'
            analysis['reasoning'] = f'Multiple matches but best match has low confidence (score: {score:.2f}) - create new entity'
    
    # Special cases based on extracted text
    extracted_lower = extracted_text.lower()
    
    # Check for obvious non-entity text (navigation, headers, etc.)
    if any(term in extracted_lower for term in ['back to', 'go to', 'search for', 'browse', 'all ', 'guidance:', 'fda guidance:', 'eua authorization', 'search criteria', 'system limitation']):
        analysis['decision'] = 'reject'
        analysis['reasoning'] = 'Extracted text appears to be navigation/header text, not an entity name'
    
    # Check for very short or generic text
    if len(extracted_text.strip()) < 3:
        analysis['decision'] = 'reject'
        analysis['reasoning'] = 'Extracted text is too short to be a valid entity name'
    
    return analysis


def review_candidates_automated(limit=100):
    """Review candidates automatically using decision logic."""
    print("=" * 80)
    print("AUTOMATED BATCH REVIEW OF MATCH CANDIDATES")
    print("=" * 80)
    print(f"Started at: {datetime.now()}")
    print(f"Target: Review {limit} candidates")
    print()
    
    results = {
        'approved': [],
        'rejected': [],
        'errors': []
    }
    
    with get_db_session() as session:
        # Fetch candidates
        candidates = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.status == 'needs_review',
            EntityMatchCandidate.deleted_at.is_(None)
        ).order_by(EntityMatchCandidate.created_at).limit(limit).all()
        
        total_available = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.status == 'needs_review',
            EntityMatchCandidate.deleted_at.is_(None)
        ).count()
        
        print(f"Found {total_available} total candidates available")
        print(f"Reviewing {len(candidates)} candidates in this batch")
        print()
        
        review_interface = ReviewInterface(session)
        
        # Review each candidate
        for i, candidate in enumerate(candidates, 1):
            if i % 10 == 0:
                print(f"Progress: {i}/{len(candidates)} ({i*100//len(candidates)}%)")
            
            # Analyze candidate
            analysis = analyze_candidate(session, candidate)
            
            try:
                if analysis['decision'] == 'approve' and analysis['entity_id']:
                    # Approve match
                    entity_id = UUID(analysis['entity_id'])
                    success = review_interface.confirm_match(
                        candidate.candidate_id,
                        entity_id,
                        reviewer_name='automated_batch_review',
                        notes=analysis['reasoning']
                    )
                    
                    if success:
                        results['approved'].append({
                            'candidate_id': str(candidate.candidate_id),
                            'entity_id': analysis['entity_id'],
                            'reasoning': analysis['reasoning'],
                            'extracted_text': analysis['extracted_text']
                        })
                    else:
                        results['errors'].append({
                            'candidate_id': str(candidate.candidate_id),
                            'error': 'Failed to approve match'
                        })
                
                elif analysis['decision'] == 'reject':
                    # Reject match
                    success = review_interface.reject_match(
                        candidate.candidate_id,
                        reviewer_name='automated_batch_review',
                        notes=analysis['reasoning']
                    )
                    
                    if success:
                        results['rejected'].append({
                            'candidate_id': str(candidate.candidate_id),
                            'reasoning': analysis['reasoning'],
                            'extracted_text': analysis['extracted_text']
                        })
                    else:
                        results['errors'].append({
                            'candidate_id': str(candidate.candidate_id),
                            'error': 'Failed to reject match'
                        })
                else:
                    results['errors'].append({
                        'candidate_id': str(candidate.candidate_id),
                        'error': f"No decision made - {analysis.get('reasoning', 'unknown reason')}"
                    })
                
            except Exception as e:
                results['errors'].append({
                    'candidate_id': str(candidate.candidate_id),
                    'error': str(e)
                })
                logger.error(f"Error processing candidate {candidate.candidate_id}: {e}", exc_info=True)
    
    # Summary
    print("\n" + "=" * 80)
    print("REVIEW SUMMARY")
    print("=" * 80)
    print(f"Total candidates reviewed: {len(candidates)}")
    print(f"Approved: {len(results['approved'])}")
    print(f"Rejected: {len(results['rejected'])}")
    print(f"Errors: {len(results['errors'])}")
    print(f"Completed at: {datetime.now()}")
    print("=" * 80)
    
    # Save results
    output_file = project_root / 'AUTOMATED_REVIEW_RESULTS.md'
    with open(output_file, 'w') as f:
        f.write("# Automated Batch Review Results\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"- **Total Reviewed**: {len(candidates)}\n")
        f.write(f"- **Approved**: {len(results['approved'])}\n")
        f.write(f"- **Rejected**: {len(results['rejected'])}\n")
        f.write(f"- **Errors**: {len(results['errors'])}\n\n")
        
        if results['approved']:
            f.write("## Approved Matches\n\n")
            for item in results['approved'][:20]:  # Show first 20
                f.write(f"- **Text**: {item['extracted_text'][:60]}...\n")
                f.write(f"  - **Matched to**: {item['entity_id']}\n")
                f.write(f"  - **Reasoning**: {item['reasoning']}\n\n")
        
        if results['rejected']:
            f.write("## Rejected Matches (New Entities)\n\n")
            for item in results['rejected'][:20]:  # Show first 20
                f.write(f"- **Text**: {item['extracted_text'][:60]}...\n")
                f.write(f"  - **Reasoning**: {item['reasoning']}\n\n")
    
    print(f"\n✓ Results saved to {output_file}")
    
    return results


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Automated batch review of match candidates"
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Number of candidates to review (default: 100)'
    )
    
    args = parser.parse_args()
    
    results = review_candidates_automated(limit=args.limit)
    sys.exit(0 if len(results['errors']) == 0 else 1)





