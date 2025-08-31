#!/usr/bin/env python3
"""
Debug script to test MethodAuditor step by step.
"""

import sys
import json
import textwrap
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.extract.workers.llm.method_auditor import MethodAuditor
from ncfd.extract.models import EvidenceSpan, PocketContextCard

def _pp(obj, max_chars=100):
    s = json.dumps(obj, ensure_ascii=False) if isinstance(obj, (dict, list)) else str(obj)
    return textwrap.shorten(s, width=max_chars, placeholder="...")

def test_method_auditor():
    """Test MethodAuditor step by step."""
    
    print("🔬 Testing MethodAuditor step by step")
    print("=" * 50)
    
    # Create test data
    doc_id = "pmc:PMC2978916"
    
    methods_spans = [
        EvidenceSpan(
            doc_id=doc_id,
            page=1,
            char_start=0,
            char_end=200,
            quote="Patients with platinum-resistant ovarian cancer were treated with pegylated liposomal doxorubicin (PLD) 50 mg/m2 on day 1 (and repeated every 4 weeks) in combination with escalating doses of atrasentan once daily. The starting dose was 2.5 mg and escalated in cohorts of three patients from 5 to 10 mg.",
            section="Methods",
            confidence=0.9
        )
    ]
    
    design_json = {
        "arms": ["PLD + atrasentan"],
        "total_n": 26,
        "primary_endpoint": {
            "name": "feasibility_and_toxicity",
            "summary_measure": "safety_analysis"
        }
    }
    
    pocket_context = PocketContextCard(
        disease="ovarian_cancer",
        intervention_class="endothelin_receptor_antagonist"
    )
    
    # Test 1: Create auditor
    print("1. Creating MethodAuditor...")
    try:
        auditor = MethodAuditor()
        print("   ✅ MethodAuditor created successfully")
    except Exception as e:
        print(f"   ❌ Failed to create MethodAuditor: {e}")
        return
    
    # Test 2: Validate inputs
    print("\n2. Validating inputs...")
    try:
        inputs = {
            'evidence_spans': methods_spans,
            'design_json': design_json,
            'pocket_context': pocket_context
        }
        is_valid = auditor.validate_inputs(inputs)
        print(f"   ✅ Input validation: {is_valid}")
    except Exception as e:
        print(f"   ❌ Input validation failed: {e}")
        return
    
    # Test 3: Filter methods spans
    print("\n3. Filtering methods spans...")
    try:
        filtered_spans = auditor._filter_methods_spans(methods_spans)
        print(f"   ✅ Filtered spans: {len(filtered_spans)}")
    except Exception as e:
        print(f"   ❌ Span filtering failed: {e}")
        return
    
    # Test 4: Extract methodology
    print("\n4. Extracting methodology...")
    try:
        method_info = auditor._extract_methodology(filtered_spans, design_json, pocket_context)
        print(f"   ✅ Methodology extracted: {len(method_info)} fields")
        for key, value in method_info.items():
            print(f"     - {key}: {type(value)}")
    except Exception as e:
        print(f"   ❌ Methodology extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test 5: Create method card
    print("\n5. Creating method card...")
    try:
        method_card = auditor._create_method_card(method_info, filtered_spans)
        print(f"   ✅ MethodCard created successfully")
        print(f"     - Estimand: {_pp(method_card.estimand)}")
        print(f"     - Analysis set: {_pp(method_card.analysis_set)}")
    except Exception as e:
        print(f"   ❌ MethodCard creation failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n🎉 All tests passed! MethodAuditor is working correctly.")

if __name__ == "__main__":
    test_method_auditor()
