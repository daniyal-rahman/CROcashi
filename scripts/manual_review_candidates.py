#!/usr/bin/env python3
"""
Manually review match candidates and apply decisions.
Examines each candidate, makes approve/reject decisions, and applies them.
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
from database.models.resolution import EntityMatchCandidate, EntityAlias
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
            entity_name = entity_details.get('name', '') or entity_details.get('title', '')
            
            # Check if extracted text is similar to entity name
            if entity_name and extracted_text.lower() in entity_name.lower() or entity_name.lower() in extracted_text.lower():
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
    if any(term in extracted_lower for term in ['back to', 'go to', 'search for', 'browse', 'all ', 'guidance:', 'fda guidance:', 'eua authorization']):
        analysis['decision'] = 'reject'
        analysis['reasoning'] = 'Extracted text appears to be navigation/header text, not an entity name'
    
    # Check for very short or generic text
    if len(extracted_text.strip()) < 3:
        analysis['decision'] = 'reject'
        analysis['reasoning'] = 'Extracted text is too short to be a valid entity name'
    
    return analysis


def review_all_candidates():
    """Review all match candidates and apply decisions."""
    print("=" * 80)
    print("MANUAL REVIEW OF MATCH CANDIDATES")
    print("=" * 80)
    print(f"Started at: {datetime.now()}")
    print()
    
    results = {
        'approved': [],
        'rejected': [],
        'errors': []
    }
    
    with get_db_session() as session:
        # Fetch all candidates
        candidates = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.status == 'needs_review',
            EntityMatchCandidate.deleted_at.is_(None)
        ).order_by(EntityMatchCandidate.created_at).all()
        
        print(f"Found {len(candidates)} candidates to review")
        print()
        
        review_interface = ReviewInterface(session)
        
        # Review each candidate
        for i, candidate in enumerate(candidates, 1):
            print(f"[{i}/{len(candidates)}] Reviewing candidate {candidate.candidate_id}")
            print(f"  Entity Type: {candidate.entity_type}")
            print(f"  Source: {candidate.source_name}")
            print(f"  Extracted Text: {candidate.extracted_text[:100] if candidate.extracted_text else 'N/A'}...")
            
            # Analyze candidate
            analysis = analyze_candidate(session, candidate)
            
            print(f"  Decision: {analysis['decision']}")
            print(f"  Reasoning: {analysis['reasoning']}")
            
            try:
                if analysis['decision'] == 'approve' and analysis['entity_id']:
                    # Approve match
                    entity_id = UUID(analysis['entity_id'])
                    success = review_interface.confirm_match(
                        candidate.candidate_id,
                        entity_id,
                        reviewer_name='automated_review',
                        notes=analysis['reasoning']
                    )
                    
                    if success:
                        print(f"  ✓ Approved - matched to {entity_id}")
                        results['approved'].append({
                            'candidate_id': str(candidate.candidate_id),
                            'entity_id': analysis['entity_id'],
                            'reasoning': analysis['reasoning']
                        })
                    else:
                        print(f"  ✗ Failed to approve")
                        results['errors'].append({
                            'candidate_id': str(candidate.candidate_id),
                            'error': 'Failed to approve match'
                        })
                
                elif analysis['decision'] == 'reject':
                    # Reject match
                    success = review_interface.reject_match(
                        candidate.candidate_id,
                        reviewer_name='automated_review',
                        notes=analysis['reasoning']
                    )
                    
                    if success:
                        print(f"  ✓ Rejected - will create new entity")
                        results['rejected'].append({
                            'candidate_id': str(candidate.candidate_id),
                            'reasoning': analysis['reasoning']
                        })
                    else:
                        print(f"  ✗ Failed to reject")
                        results['errors'].append({
                            'candidate_id': str(candidate.candidate_id),
                            'error': 'Failed to reject match'
                        })
                else:
                    print(f"  ⚠️ No decision made (missing entity_id for approve)")
                    results['errors'].append({
                        'candidate_id': str(candidate.candidate_id),
                        'error': 'No decision made - missing entity_id'
                    })
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
                results['errors'].append({
                    'candidate_id': str(candidate.candidate_id),
                    'error': str(e)
                })
                logger.error(f"Error processing candidate {candidate.candidate_id}: {e}", exc_info=True)
            
            print()
    
    # Summary
    print("=" * 80)
    print("REVIEW SUMMARY")
    print("=" * 80)
    print(f"Total candidates: {len(candidates)}")
    print(f"Approved: {len(results['approved'])}")
    print(f"Rejected: {len(results['rejected'])}")
    print(f"Errors: {len(results['errors'])}")
    print()
    
    return results


if __name__ == '__main__':
    results = review_all_candidates()
    
    # Save results to file
    output_file = project_root / 'MATCH_CANDIDATE_REVIEW_RESULTS.md'
    with open(output_file, 'w') as f:
        f.write("# Match Candidate Review Results\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"- **Total Reviewed**: {len(results['approved']) + len(results['rejected']) + len(results['errors'])}\n")
        f.write(f"- **Approved**: {len(results['approved'])}\n")
        f.write(f"- **Rejected**: {len(results['rejected'])}\n")
        f.write(f"- **Errors**: {len(results['errors'])}\n\n")
        
        if results['approved']:
            f.write("## Approved Matches\n\n")
            for item in results['approved']:
                f.write(f"- **Candidate**: {item['candidate_id']}\n")
                f.write(f"  - **Matched to**: {item['entity_id']}\n")
                f.write(f"  - **Reasoning**: {item['reasoning']}\n\n")
        
        if results['rejected']:
            f.write("## Rejected Matches (New Entities)\n\n")
            for item in results['rejected']:
                f.write(f"- **Candidate**: {item['candidate_id']}\n")
                f.write(f"  - **Reasoning**: {item['reasoning']}\n\n")
        
        if results['errors']:
            f.write("## Errors\n\n")
            for item in results['errors']:
                f.write(f"- **Candidate**: {item['candidate_id']}\n")
                f.write(f"  - **Error**: {item['error']}\n\n")
    
    print(f"✓ Results saved to {output_file}")
    sys.exit(0 if len(results['errors']) == 0 else 1)

