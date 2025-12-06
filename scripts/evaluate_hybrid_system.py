#!/usr/bin/env python3
"""
Evaluate hybrid entity resolution system.

Compares performance of:
- Rule-based only resolver
- Hybrid (rule-based + LLM) resolver

Uses validated candidates as test set.
"""
import sys
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from uuid import UUID

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.resolution import EntityMatchCandidate
from database.models.entities import Company, Drug, Disease, Institution
from database.models.clinical import ClinicalTrial
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.hybrid_resolver import HybridEntityResolver
from src.entity_resolution.types import ExtractedEntity, EntityType
from src.config.feature_flags import FeatureFlags


def load_validation_set():
    """Load reviewed candidates as validation set."""
    with get_db_session() as session:
        candidates = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.status.in_(['reviewed', 'new_entity']),
            EntityMatchCandidate.deleted_at.is_(None)
        ).all()
        
        validation_data = []
        
        for candidate in candidates:
            # Convert to ExtractedEntity
            entity = ExtractedEntity(
                entity_type=EntityType(candidate.entity_type),
                name=candidate.extracted_text,
                identifiers={},
                context=candidate.extracted_context or {},
                metadata={'source_name': candidate.source_name}
            )
            
            # Ground truth
            ground_truth = {
                'should_match': candidate.status == 'reviewed',
                'matched_to': candidate.matched_to,
                'confidence': float(candidate.match_confidence or 0.0)
            }
            
            validation_data.append({
                'entity': entity,
                'ground_truth': ground_truth,
                'candidate_id': str(candidate.candidate_id)
            })
        
        return validation_data


def evaluate_resolver(resolver_class, validation_data, session):
    """Evaluate a resolver on validation data."""
    resolver = resolver_class(session)
    
    results = {
        'correct': 0,
        'incorrect': 0,
        'precision': 0.0,
        'recall': 0.0,
        'f1': 0.0,
        'predictions': []
    }
    
    true_positives = 0
    false_positives = 0
    true_negatives = 0
    false_negatives = 0
    
    for item in validation_data:
        entity = item['entity']
        ground_truth = item['ground_truth']
        
        # Get resolver prediction
        result = resolver.resolve(entity)
        
        # Determine if resolver matched
        predicted_match = result.entity_id is not None and result.confidence_score >= 0.85
        actual_match = ground_truth['should_match']
        
        # Calculate confusion matrix
        if predicted_match and actual_match:
            true_positives += 1
            results['correct'] += 1
        elif predicted_match and not actual_match:
            false_positives += 1
            results['incorrect'] += 1
        elif not predicted_match and actual_match:
            false_negatives += 1
            results['incorrect'] += 1
        else:  # not predicted_match and not actual_match
            true_negatives += 1
            results['correct'] += 1
        
        results['predictions'].append({
            'candidate_id': item['candidate_id'],
            'predicted_match': predicted_match,
            'actual_match': actual_match,
            'confidence': result.confidence_score,
            'method': result.match_method.value if result.match_method else 'none'
        })
    
    # Calculate metrics
    if true_positives + false_positives > 0:
        results['precision'] = true_positives / (true_positives + false_positives)
    
    if true_positives + false_negatives > 0:
        results['recall'] = true_positives / (true_positives + false_negatives)
    
    if results['precision'] + results['recall'] > 0:
        results['f1'] = 2 * (results['precision'] * results['recall']) / (results['precision'] + results['recall'])
    
    results['confusion_matrix'] = {
        'true_positives': true_positives,
        'false_positives': false_positives,
        'true_negatives': true_negatives,
        'false_negatives': false_negatives
    }
    
    results['accuracy'] = (true_positives + true_negatives) / len(validation_data)
    
    return results


def evaluate_system():
    """Evaluate both resolvers and compare."""
    print("=" * 80)
    print("HYBRID ENTITY RESOLUTION SYSTEM EVALUATION")
    print("=" * 80)
    print(f"Date: {datetime.now()}")
    print()
    
    # Print feature flags
    print("Configuration:")
    FeatureFlags.print_config()
    print()
    
    # Load validation set
    print("Loading validation set...")
    validation_data = load_validation_set()
    print(f"✓ Loaded {len(validation_data)} validation examples")
    print()
    
    if len(validation_data) == 0:
        print("⚠️  No validation data found. Run manual reviews first:")
        print("  python scripts/manual_review_candidates.py")
        return
    
    with get_db_session() as session:
        # Evaluate rule-based resolver
        print("Evaluating rule-based resolver...")
        rule_based_results = evaluate_resolver(EntityResolver, validation_data, session)
        print("✓ Rule-based evaluation complete")
        print()
        
        # Evaluate hybrid resolver
        print("Evaluating hybrid resolver...")
        hybrid_results = evaluate_resolver(HybridEntityResolver, validation_data, session)
        print("✓ Hybrid evaluation complete")
        print()
    
    # Print comparison
    print("=" * 80)
    print("RESULTS COMPARISON")
    print("=" * 80)
    print()
    
    print(f"{'Metric':<20} {'Rule-Based':<15} {'Hybrid':<15} {'Improvement':<15}")
    print("-" * 65)
    
    metrics = ['accuracy', 'precision', 'recall', 'f1']
    for metric in metrics:
        rule_val = rule_based_results[metric]
        hybrid_val = hybrid_results[metric]
        improvement = ((hybrid_val - rule_val) / rule_val * 100) if rule_val > 0 else 0
        
        print(f"{metric.capitalize():<20} {rule_val:<15.3f} {hybrid_val:<15.3f} {improvement:>+14.1f}%")
    
    print()
    print("Confusion Matrix:")
    print()
    
    print("Rule-Based:")
    cm = rule_based_results['confusion_matrix']
    print(f"  True Positives:  {cm['true_positives']}")
    print(f"  False Positives: {cm['false_positives']}")
    print(f"  True Negatives:  {cm['true_negatives']}")
    print(f"  False Negatives: {cm['false_negatives']}")
    print()
    
    print("Hybrid:")
    cm = hybrid_results['confusion_matrix']
    print(f"  True Positives:  {cm['true_positives']}")
    print(f"  False Positives: {cm['false_positives']}")
    print(f"  True Negatives:  {cm['true_negatives']}")
    print(f"  False Negatives: {cm['false_negatives']}")
    print()
    
    # Save results
    output_dir = Path('data/evaluation')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / f'evaluation_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'configuration': FeatureFlags.get_config_summary(),
            'validation_size': len(validation_data),
            'rule_based': rule_based_results,
            'hybrid': hybrid_results
        }, f, indent=2)
    
    print(f"✓ Results saved to {output_file}")
    print()
    
    # Recommendations
    print("Recommendations:")
    if hybrid_results['f1'] > rule_based_results['f1']:
        print("  ✓ Hybrid resolver performs better - recommend deployment")
    elif hybrid_results['f1'] == rule_based_results['f1']:
        print("  ⚠️  No improvement from LLM - check model and prompts")
    else:
        print("  ✗ Hybrid resolver performs worse - investigate issues")
    
    if not FeatureFlags.USE_LLM_VALIDATION:
        print("  ⚠️  LLM validation is disabled - enable to test hybrid system")
    
    if len(validation_data) < 50:
        print(f"  ⚠️  Small validation set ({len(validation_data)}) - collect more reviews for reliable evaluation")


if __name__ == '__main__':
    evaluate_system()

