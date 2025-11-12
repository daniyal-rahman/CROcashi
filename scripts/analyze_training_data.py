#!/usr/bin/env python3
"""
Analyze training data quality and distribution.

Checks for:
- Label balance (approve/reject ratio)
- Entity type distribution
- Source distribution
- Edge case coverage
"""
import sys
import json
from pathlib import Path
from collections import Counter, defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def analyze_training_data(input_file='data/llm_training/entity_matching_training.jsonl'):
    """Analyze training data quality."""
    input_file = Path(input_file)
    
    if not input_file.exists():
        print(f"✗ Input file not found: {input_file}")
        return
    
    # Read examples
    examples = []
    with open(input_file, 'r') as f:
        for line in f:
            examples.append(json.loads(line))
    
    print("=" * 80)
    print("TRAINING DATA ANALYSIS")
    print("=" * 80)
    print(f"Total examples: {len(examples)}\n")
    
    # Extract labels
    labels = []
    entity_types = []
    sources = []
    confidences = []
    
    for ex in examples:
        # Parse assistant response
        assistant_msg = ex['messages'][2]['content']
        response = json.loads(assistant_msg)
        
        labels.append(response['match'])
        entity_types.append(ex['metadata']['entity_type'])
        sources.append(ex['metadata']['source_name'])
        confidences.append(response.get('confidence', 0.0))
    
    # Label balance
    print("Label Distribution:")
    label_counts = Counter(labels)
    print(f"  Approve (match=true): {label_counts[True]} ({label_counts[True]/len(labels)*100:.1f}%)")
    print(f"  Reject (match=false): {label_counts[False]} ({label_counts[False]/len(labels)*100:.1f}%)")
    
    if label_counts[True] / label_counts[False] > 2 or label_counts[False] / label_counts[True] > 2:
        print("  ⚠️  Warning: Imbalanced labels (>2:1 ratio)")
    else:
        print("  ✓ Labels reasonably balanced")
    print()
    
    # Entity type distribution
    print("Entity Type Distribution:")
    type_counts = Counter(entity_types)
    for etype, count in type_counts.most_common():
        print(f"  {etype}: {count} ({count/len(entity_types)*100:.1f}%)")
    print()
    
    # Source distribution
    print("Source Distribution:")
    source_counts = Counter(sources)
    for source, count in source_counts.most_common():
        print(f"  {source}: {count} ({count/len(sources)*100:.1f}%)")
    print()
    
    # Confidence distribution (for approved matches)
    approved_confidences = [c for c, l in zip(confidences, labels) if l]
    if approved_confidences:
        print("Confidence Distribution (Approved Matches):")
        print(f"  Mean: {sum(approved_confidences)/len(approved_confidences):.2f}")
        print(f"  Min: {min(approved_confidences):.2f}")
        print(f"  Max: {max(approved_confidences):.2f}")
        print()
    
    # Recommendations
    print("Recommendations:")
    if len(examples) < 100:
        print("  ⚠️  Dataset is small (<100 examples). Continue manual review to reach 500-1000.")
    elif len(examples) < 500:
        print("  ⚠️  Dataset is moderate (100-500). Aim for 500-1000 for best results.")
    else:
        print("  ✓ Dataset size is good (500+)")
    
    if label_counts[True] == 0 or label_counts[False] == 0:
        print("  ✗ Missing positive or negative examples!")
    
    if len(type_counts) < 3:
        print("  ⚠️  Limited entity type diversity. Consider reviewing more types.")
    
    print()
    print("Next steps:")
    print("  1. If dataset is small: python scripts/manual_review_candidates.py")
    print("  2. Split data: python scripts/split_training_data.py")
    print("  3. When RTX 5080 arrives: Fine-tune Llama 70B on this data")


if __name__ == '__main__':
    analyze_training_data()

