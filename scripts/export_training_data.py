#!/usr/bin/env python3
"""
Export reviewed match candidates as LLM training data.

This script exports all reviewed entity match candidates to JSONL format
for fine-tuning an LLM on entity matching tasks.
"""
import sys
import json
from pathlib import Path
from datetime import datetime
from uuid import UUID

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.resolution import EntityMatchCandidate
from database.models.entities import Company, Drug, Disease, Institution
from database.models.clinical import ClinicalTrial


def get_entity_details(session, entity_type: str, entity_id: UUID) -> dict:
    """Get details about an entity."""
    try:
        if entity_type == 'company':
            entity = session.query(Company).filter(Company.company_id == entity_id).first()
            if entity:
                return {
                    'id': str(entity.company_id),
                    'name': entity.name,
                    'ticker': entity.ticker,
                    'status': entity.status
                }
        elif entity_type == 'drug':
            entity = session.query(Drug).filter(Drug.drug_id == entity_id).first()
            if entity:
                return {
                    'id': str(entity.drug_id),
                    'name': entity.primary_name,
                    'generic_name': entity.generic_name,
                    'drug_type': entity.drug_type
                }
        elif entity_type == 'disease':
            entity = session.query(Disease).filter(Disease.disease_id == entity_id).first()
            if entity:
                return {
                    'id': str(entity.disease_id),
                    'name': entity.disease_name
                }
        elif entity_type == 'institution':
            entity = session.query(Institution).filter(Institution.institution_id == entity_id).first()
            if entity:
                return {
                    'id': str(entity.institution_id),
                    'name': entity.name,
                    'institution_type': entity.institution_type
                }
        elif entity_type == 'trial':
            entity = session.query(ClinicalTrial).filter(ClinicalTrial.trial_id == entity_id).first()
            if entity:
                return {
                    'id': str(entity.trial_id),
                    'title': entity.trial_title,
                    'nct_id': entity.nct_id,
                    'phase': entity.phase
                }
    except Exception as e:
        print(f"Error getting entity details for {entity_type} {entity_id}: {e}")
    
    return {}


def create_training_example(session, candidate: EntityMatchCandidate) -> dict:
    """
    Create a training example from a reviewed candidate.
    
    Format for LLM fine-tuning:
    {
        "messages": [
            {"role": "system", "content": "You are an expert in biomedical entity matching."},
            {"role": "user", "content": "Candidate: ... Should these match?"},
            {"role": "assistant", "content": "{\"match\": true, \"confidence\": 0.85, \"reasoning\": \"...\"}"}
        ]
    }
    """
    # Get entity details if matched
    entity_details = {}
    if candidate.matched_to:
        entity_details = get_entity_details(session, candidate.entity_type, candidate.matched_to)
    
    # Build user prompt
    user_content = f"""**Candidate Entity:**
- Text: "{candidate.extracted_text}"
- Type: {candidate.entity_type}
- Source: {candidate.source_name}
- Context: {json.dumps(candidate.extracted_context or {}, indent=2)}

**Potential Match:**
- Entity Name: "{entity_details.get('name', 'N/A')}"
- Confidence: {float(candidate.match_confidence or 0.0):.2f}

**Question:** Should these be matched?

Consider:
1. Abbreviations (NSCLC = Non-Small Cell Lung Cancer)
2. Synonyms
3. Different formulations
4. Stage/progression variations
5. Brand vs generic names

Respond with JSON only:"""

    # Build assistant response based on review decision
    if candidate.status == 'reviewed':
        # Approved match
        assistant_content = json.dumps({
            "match": True,
            "confidence": float(candidate.match_confidence or 0.85),
            "reasoning": candidate.match_reasoning or "Entities match based on manual review"
        }, indent=2)
    else:  # new_entity or rejected
        # Rejected match
        assistant_content = json.dumps({
            "match": False,
            "confidence": 0.0,
            "reasoning": candidate.review_notes or "Different entities, creating new"
        }, indent=2)
    
    # Create training example in chat format
    training_example = {
        "messages": [
            {
                "role": "system",
                "content": "You are an expert in biomedical entity matching."
            },
            {
                "role": "user",
                "content": user_content
            },
            {
                "role": "assistant",
                "content": assistant_content
            }
        ],
        "metadata": {
            "candidate_id": str(candidate.candidate_id),
            "entity_type": candidate.entity_type,
            "source_name": candidate.source_name,
            "reviewed_by": candidate.reviewed_by,
            "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None
        }
    }
    
    return training_example


def export_training_data(
    output_dir='data/llm_training',
    output_file=None,
    format='jsonl',
    split_train_val=True,
    train_ratio=0.8
):
    """Export all reviewed candidates to JSONL format."""
    import random
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("EXPORTING TRAINING DATA FOR LLM FINE-TUNING")
    print("=" * 80)
    print(f"Output directory: {output_dir}")
    print(f"Format: {format}")
    print(f"Train/Val split: {split_train_val} ({train_ratio:.0%}/{1-train_ratio:.0%})")
    print()
    
    with get_db_session() as session:
        # Get all reviewed candidates
        candidates = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.status.in_(['reviewed', 'new_entity']),
            EntityMatchCandidate.deleted_at.is_(None)
        ).order_by(EntityMatchCandidate.reviewed_at).all()
        
        print(f"Found {len(candidates)} reviewed candidates")
        print()
        
        if len(candidates) == 0:
            print("⚠️  No reviewed candidates found. Complete manual reviews first.")
            return
        
        training_examples = []
        
        # Create training examples
        for i, candidate in enumerate(candidates, 1):
            print(f"[{i}/{len(candidates)}] Processing {candidate.candidate_id}...", end=' ')
            try:
                example = create_training_example(session, candidate)
                training_examples.append(example)
                print("✓")
            except Exception as e:
                print(f"✗ Error: {e}")
        
        print()
        
        # Shuffle for train/val split
        if split_train_val:
            random.seed(42)  # For reproducibility
            random.shuffle(training_examples)
            split_idx = int(len(training_examples) * train_ratio)
            train_examples = training_examples[:split_idx]
            val_examples = training_examples[split_idx:]
            
            # Save train set
            train_file = output_dir / 'train.jsonl'
            with open(train_file, 'w') as f:
                for ex in train_examples:
                    f.write(json.dumps(ex) + '\n')
            print(f"✓ Exported {len(train_examples)} training examples to {train_file}")
            
            # Save val set
            val_file = output_dir / 'val.jsonl'
            with open(val_file, 'w') as f:
                for ex in val_examples:
                    f.write(json.dumps(ex) + '\n')
            print(f"✓ Exported {len(val_examples)} validation examples to {val_file}")
        else:
            # Save single file
            if output_file:
                output_path = Path(output_file)
            else:
                output_path = output_dir / 'entity_matching_v1.jsonl'
            
            with open(output_path, 'w') as f:
                for ex in training_examples:
                    f.write(json.dumps(ex) + '\n')
            
            print(f"✓ Exported {len(training_examples)} training examples to {output_path}")
        
        # Save metadata
        metadata_file = output_dir / 'training_metadata.json'
        metadata = {
            'export_date': datetime.now().isoformat(),
            'total_examples': len(training_examples),
            'approved_matches': len([c for c in candidates if c.status == 'reviewed']),
            'rejected_matches': len([c for c in candidates if c.status == 'new_entity']),
            'entity_types': {},
            'sources': {}
        }
        
        # Count by entity type and source
        for candidate in candidates:
            metadata['entity_types'][candidate.entity_type] = \
                metadata['entity_types'].get(candidate.entity_type, 0) + 1
            metadata['sources'][candidate.source_name] = \
                metadata['sources'].get(candidate.source_name, 0) + 1
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✓ Saved metadata to {metadata_file}")
        print()
        print("Summary:")
        print(f"  Total Examples: {metadata['total_examples']}")
        print(f"  Approved: {metadata['approved_matches']}")
        print(f"  Rejected: {metadata['rejected_matches']}")
        print(f"  Entity Types: {', '.join(metadata['entity_types'].keys())}")
        print(f"  Sources: {', '.join(metadata['sources'].keys())}")
        print()
        print("Next steps:")
        print("  1. Review training data: cat data/llm_training/entity_matching_training.jsonl | head")
        print("  2. Split into train/val: python scripts/split_training_data.py")
        print("  3. Fine-tune model when RTX 5080 arrives")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Export reviewed candidates as LLM training data"
    )
    parser.add_argument(
        '--format',
        type=str,
        default='jsonl',
        choices=['jsonl'],
        help='Output format (default: jsonl)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (default: data/llm_training/entity_matching_v1.jsonl)'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default='data/llm_training',
        help='Output directory (default: data/llm_training)'
    )
    parser.add_argument(
        '--no-split',
        action='store_true',
        help='Do not split into train/val sets'
    )
    parser.add_argument(
        '--train-ratio',
        type=float,
        default=0.8,
        help='Train set ratio (default: 0.8)'
    )
    
    args = parser.parse_args()
    
    export_training_data(
        output_dir=args.output_dir,
        output_file=args.output,
        format=args.format,
        split_train_val=not args.no_split,
        train_ratio=args.train_ratio
    )

