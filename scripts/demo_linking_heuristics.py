#!/usr/bin/env python3
"""
Demo script for linking heuristics and promotion system.

This script demonstrates the current implementation status and shows
how precision validation gates auto-promotion.
"""

import logging
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.mapping.linking_heuristics import LinkingHeuristics, LinkPromoter, LinkCandidate
from ncfd.config import get_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def demo_linking_heuristics():
    """Demonstrate the linking heuristics system."""
    print("NCFD Linking Heuristics Demo")
    print("=" * 40)
    
    # Load configuration
    config = get_config()
    linking_config = config.get('linking_heuristics', {})
    
    print(f"\n1. Configuration Status:")
    print(f"   Auto-promotion enabled: {linking_config.get('auto_promote_enabled', False)}")
    print(f"   Min labeled precision: {linking_config.get('min_labeled_precision', 0.95)}")
    print(f"   Min labeled links: {linking_config.get('min_labeled_links', 50)}")
    
    # Create mock link candidates to demonstrate the system
    print("\n2. Creating mock link candidates...")
    
    candidates = [
        LinkCandidate(
            doc_id=1,
            asset_id=101,
            nct_id="NCT12345678",
            link_type="nct_near_asset",
            confidence=1.00,
            evidence={
                'heuristic': 'HP-1',
                'asset_span': {'page_no': 1, 'char_start': 100, 'char_end': 106, 'text': 'AB-123'},
                'nct_span': {'page_no': 1, 'char_start': 150, 'char_end': 158, 'text': 'NCT12345678'},
                'distance': 50
            }
        ),
        LinkCandidate(
            doc_id=1,
            asset_id=102,
            link_type="code_inn_company_pr",
            confidence=0.90,
            evidence={
                'heuristic': 'HP-3',
                'code_span': {'page_no': 1, 'char_start': 200, 'char_end': 206, 'text': 'XYZ-456'},
                'inn_span': {'page_no': 1, 'char_start': 250, 'char_end': 260, 'text': 'Test Drug'},
                'company_hosted': True
            }
        ),
        LinkCandidate(
            doc_id=2,
            asset_id=103,
            link_type="abstract_specificity",
            confidence=0.85,
            evidence={
                'heuristic': 'HP-4',
                'entity_span': {'page_no': 1, 'char_start': 300, 'char_end': 306, 'text': 'BMS-001'},
                'has_phase': True,
                'has_indication': True,
                'in_title': True,
                'code_unique': True
            }
        )
    ]
    
    print(f"Created {len(candidates)} link candidates:")
    for i, candidate in enumerate(candidates, 1):
        print(f"  {i}. {candidate.link_type} (confidence: {candidate.confidence:.2f})")
        print(f"     Evidence: {candidate.evidence.get('heuristic', 'Unknown')}")
    
    # Demonstrate confidence scoring with actual implementation status
    print("\n3. Confidence scoring breakdown (current implementation):")
    print("   HP-1 (NCT near asset): 1.00 - ✅ IMPLEMENTED - Highest confidence")
    print("   HP-2 (Exact intervention match): 0.95 - ❌ NOT IMPLEMENTED - Requires CT.gov cache")
    print("   HP-3 (Company PR bias): 0.90 - ✅ IMPLEMENTED - Uncalibrated confidence")
    print("   HP-4 (Abstract specificity): 0.85 - ✅ IMPLEMENTED - Uncalibrated confidence")
    
    # Demonstrate promotion logic
    print("\n4. Promotion logic:")
    print("   Auto-promote: ❌ DISABLED until precision validation")
    print("   Human review: ✅ REQUIRED for all links")
    print("   Evidence capture: ✅ All spans and context preserved")
    
    # Show evidence structure
    print("\n5. Evidence structure example:")
    hp1_evidence = candidates[0].evidence
    print(f"   HP-1 Evidence:")
    print(f"     - Asset: {hp1_evidence['asset_span']['text']} at chars {hp1_evidence['asset_span']['char_start']}-{hp1_evidence['asset_span']['char_end']}")
    print(f"     - NCT: {hp1_evidence['nct_span']['text']} at chars {hp1_evidence['nct_span']['char_start']}-{hp1_evidence['nct_span']['char_end']}")
    print(f"     - Distance: {hp1_evidence['distance']} characters")
    
    # Demonstrate conflict resolution
    print("\n6. Conflict resolution:")
    print("   Multiple assets without combo → Downgrade by 0.20")
    print("   Combo therapy detected → Allow multiple, no downgrade")
    print("   Evidence preserved for human review")
    
    print("\n🎉 Linking heuristics demo completed!")
    print("\nNext steps:")
    print("1. ✅ Run Alembic migration to create final xref tables")
    print("2. ✅ Integrate with document processing pipeline")
    print("3. 🔄 Set up monitoring and review workflows")
    print("4. 🎯 Collect labeled data for precision validation")
    print("5. 🚀 Enable auto-promotion when precision ≥95% on ≥50 links")


def demo_promotion_system():
    """Demonstrate the promotion system."""
    print("\n" + "=" * 40)
    print("Link Promotion System Demo")
    print("=" * 40)
    
    print("\n1. Promotion workflow:")
    print("   - Document links created with confidence scores")
    print("   - ❌ Auto-promotion: DISABLED until precision validation")
    print("   - ✅ Human review: REQUIRED for all links")
    print("   - 📊 Precision tracking: Enabled via link_audit table")
    
    print("\n2. Final xref tables:")
    print("   - study_assets_xref: General study-asset relationships")
    print("   - trial_assets_xref: NCT-specific trial-asset relationships")
    print("   - link_audit: ✅ Complete audit trail with label fields")
    print("   - merge_candidates: Asset deduplication workflow")
    
    print("\n3. Evidence preservation:")
    print("   - ✅ All spans and context stored in evidence_jsonb")
    print("   - ✅ Heuristic used and confidence score preserved")
    print("   - ✅ Source document and creation timestamp tracked")
    
    print("\n4. Precision validation:")
    print("   - ✅ link_audit.label: True/False for reviewed links")
    print("   - ✅ link_audit.label_source: human_review, gold_standard, etc.")
    print("   - ✅ link_audit.reviewed_by: Username or system ID")
    print("   - ✅ link_audit.reviewed_at: Review completion timestamp")
    
    print("\n5. Auto-promotion gates:")
    print("   - Feature flag: auto_promote_enabled = false")
    print("   - Min precision: 95% on labeled links")
    print("   - Min links: 50 labeled links per heuristic")
    print("   - Status: ❌ DISABLED until validation complete")
    
    print("\n🎉 Promotion system demo completed!")


def demo_precision_validation():
    """Demonstrate precision validation system."""
    print("\n" + "=" * 40)
    print("Precision Validation System Demo")
    print("=" * 40)
    
    print("\n1. Current implementation status:")
    print("   HP-1 (NCT near asset): ✅ IMPLEMENTED")
    print("   HP-2 (Exact intervention): ❌ NOT IMPLEMENTED")
    print("   HP-3 (Company PR bias): ✅ IMPLEMENTED")
    print("   HP-4 (Abstract specificity): ✅ IMPLEMENTED")
    
    print("\n2. Precision validation requirements:")
    print("   - Each heuristic needs ≥50 labeled links")
    print("   - Each heuristic needs ≥95% precision")
    print("   - All heuristics must meet requirements")
    print("   - Auto-promotion remains disabled until then")
    
    print("\n3. Data collection strategy:")
    print("   - Human review of existing links")
    print("   - Gold standard dataset creation")
    print("   - External validation sources")
    print("   - Continuous monitoring and updates")
    
    print("\n4. Database functions available:")
    print("   - get_heuristic_precision(heuristic, start_date, end_date)")
    print("   - can_auto_promote_heuristic(heuristic, min_precision, min_links)")
    print("   - heuristic_precision_summary view")
    
    print("\n🎉 Precision validation demo completed!")


if __name__ == "__main__":
    try:
        demo_linking_heuristics()
        demo_promotion_system()
        demo_precision_validation()
        
        print("\n" + "=" * 60)
        print("📋 SUMMARY OF IMPLEMENTATION STATUS")
        print("=" * 60)
        print("✅ COMPLETED:")
        print("   - HP-1: NCT near asset (confidence 1.00)")
        print("   - HP-3: Company PR bias (confidence 0.90)")
        print("   - HP-4: Abstract specificity (confidence 0.85)")
        print("   - Link audit table with label fields")
        print("   - Precision validation functions")
        print("   - Feature flag system")
        print("   - Configuration-driven thresholds")
        
        print("\n❌ NOT IMPLEMENTED:")
        print("   - HP-2: Exact intervention match (requires CT.gov cache)")
        print("   - Auto-promotion (disabled until precision validation)")
        
        print("\n🔄 NEXT STEPS:")
        print("   1. Collect labeled data for precision validation")
        print("   2. Implement HP-2 when CT.gov cache is available")
        print("   3. Enable auto-promotion when precision ≥95%")
        print("   4. Monitor and calibrate confidence scores")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        sys.exit(1)
