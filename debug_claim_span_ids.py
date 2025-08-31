#!/usr/bin/env python3
"""
Debug script to understand why Claim objects are not preserving span_ids.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.extract.models import EvidenceSpan, Claim


def debug_claim_span_ids():
    """Debug why Claim objects are not preserving span_ids."""
    print("🔍 DEBUGGING CLAIM SPAN_IDS ISSUE")
    print("=" * 50)
    
    # Create a test EvidenceSpan
    span = EvidenceSpan(
        doc_id="test:123",
        quote="Test text with 15.8% response rate",
        section="Results",
        char_start=100,
        char_end=200,
        confidence=0.9
    )
    
    print(f"EvidenceSpan created:")
    print(f"  doc_id: {span.doc_id}")
    print(f"  span_id: {span.span_id}")
    print(f"  span_ids: {span.span_ids}")
    print()
    
    # Create a Claim with span_ids
    claim = Claim(
        claim_id="test#claim_0",
        doc_id="test:123",
        span_ids=[span.span_id],  # This should work
        type="effect_size",
        proposition="response_rate: 15.8",
        stance="neutral",
        value=15.8,
        units="percent",
        endpoint="response_rate"
    )
    
    print(f"Claim created:")
    print(f"  claim_id: {claim.claim_id}")
    print(f"  doc_id: {claim.doc_id}")
    print(f"  span_ids: {claim.span_ids}")
    print(f"  parent_ids: {claim.parent_ids}")
    print(f"  value: {claim.value}")
    print(f"  units: {claim.units}")
    print()
    
    # Check if span_ids is empty
    if not claim.span_ids:
        print("❌ PROBLEM: Claim span_ids is empty!")
        print("This violates the requirement: 'Every numeric must be span-anchored'")
        return False
    else:
        print("✅ SUCCESS: Claim span_ids is properly set")
        return True


if __name__ == "__main__":
    success = debug_claim_span_ids()
    if success:
        print("\n🎉 Claim span_ids debugging successful!")
    else:
        print("\n❌ Claim span_ids debugging failed!")
    sys.exit(0 if success else 1)
