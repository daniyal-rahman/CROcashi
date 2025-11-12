#!/usr/bin/env python3
"""
Split training data into train and validation sets.

Stratifies by entity type to ensure balanced representation.
"""
import sys
import json
import random
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def split_training_data(
    input_file='data/llm_training/entity_matching_training.jsonl',
    train_ratio=0.8,
    seed=42
):
    """Split training data into train and validation sets."""
    input_file = Path(input_file)
    
    if not input_file.exists():
        print(f"✗ Input file not found: {input_file}")
        print("  Run: python scripts/export_training_data.py first")
        return
    
    # Read all examples
    examples = []
    with open(input_file, 'r') as f:
        for line in f:
            examples.append(json.loads(line))
    
    print(f"Loaded {len(examples)} examples")
    
    # Group by entity type for stratification
    by_entity_type = defaultdict(list)
    for ex in examples:
        entity_type = ex['metadata']['entity_type']
        by_entity_type[entity_type].append(ex)
    
    print(f"Entity types: {list(by_entity_type.keys())}")
    
    # Split each entity type
    random.seed(seed)
    train_examples = []
    val_examples = []
    
    for entity_type, type_examples in by_entity_type.items():
        random.shuffle(type_examples)
        split_idx = int(len(type_examples) * train_ratio)
        
        train_examples.extend(type_examples[:split_idx])
        val_examples.extend(type_examples[split_idx:])
        
        print(f"  {entity_type}: {split_idx} train, {len(type_examples) - split_idx} val")
    
    # Shuffle combined sets
    random.shuffle(train_examples)
    random.shuffle(val_examples)
    
    # Save
    train_file = input_file.parent / 'train.jsonl'
    val_file = input_file.parent / 'val.jsonl'
    
    with open(train_file, 'w') as f:
        for ex in train_examples:
            f.write(json.dumps(ex) + '\n')
    
    with open(val_file, 'w') as f:
        for ex in val_examples:
            f.write(json.dumps(ex) + '\n')
    
    print(f"\n✓ Split complete:")
    print(f"  Train: {len(train_examples)} examples → {train_file}")
    print(f"  Val: {len(val_examples)} examples → {val_file}")


if __name__ == '__main__':
    split_training_data()

