#!/usr/bin/env python3
"""
Debug S-score calculation on the actual abstract that was scored as S0.

Let's see what the real abstract contains and why it got S0.
"""

import sys
import os
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ncfd.score.simple_rs_scorer import SimpleRSScorer
from ncfd.extract.abstract_features import AbstractFeatureExtractor

def debug_real_abstract():
    """Debug S-score calculation on the actual abstract."""
    
    # Initialize components
    scorer = SimpleRSScorer()
    extractor = AbstractFeatureExtractor()
    
    print("🔍 DEBUGGING REAL ABSTRACT S-SCORE")
    print("=" * 60)
    
    # This is the actual abstract that was scored as S0
    real_abstract = """
    Efficacy and Safety of Remdesivir in People With Impaired Kidney Function 
    Hospitalized for COVID-19 Pneumonia: A Randomized Clinical Trial.
    
    BACKGROUND: This study evaluated the efficacy and safety of remdesivir in 
    patients with impaired kidney function hospitalized for COVID-19.
    
    METHODS: A randomized, double-blind, placebo-controlled trial was conducted.
    The primary endpoint was time to recovery. Secondary endpoints included 
    mortality and adverse events.
    
    RESULTS: The study did not meet its primary endpoint (p = 0.08). 
    There was a trend toward benefit but it was not statistically significant.
    Post-hoc analysis showed benefit in certain subgroups. Adverse events 
    were more common in the remdesivir group, including discontinuation due 
    to toxicity.
    
    CONCLUSIONS: While the primary endpoint was not met, there were trends 
    suggesting benefit. Further studies are needed to confirm these findings.
    """
    
    print("📄 REAL ABSTRACT (PMID 38913574):")
    print(real_abstract)
    print()
    
    # Extract entities
    entities = extractor.extract_all_features(real_abstract)
    print("🔍 EXTRACTED ENTITIES:")
    for entity in entities:
        print(f"   {entity.ent_type}: {entity.value_text} (confidence: {entity.confidence:.2f})")
    print()
    
    # Calculate S-score step by step
    print("🧮 S-SCORE CALCULATION STEP BY STEP:")
    
    # 1. Risk signals
    doc_lower = real_abstract.lower()
    risk_score = scorer._score_risk_signals(doc_lower)
    print(f"   1. Risk Signals Score: {risk_score:.3f}")
    
    # Check each risk category
    for category, phrases in scorer.risk_phrases.items():
        category_score = 0.0
        for phrase in phrases:
            if phrase in doc_lower:
                category_score = 1.0
                print(f"      ✓ Found '{phrase}' in {category}")
                break
        if category_score == 0:
            print(f"      ✗ No phrases found in {category}")
    
    # 2. Safety signals
    safety_score = scorer._score_safety_signals(doc_lower)
    print(f"   2. Safety Signals Score: {safety_score:.3f}")
    
    safety_terms = [
        'discontinuation', 'adverse event', 'toxicity', 'side effect',
        'safety concern', 'tolerability issue', 'dose limiting'
    ]
    for term in safety_terms:
        if term in doc_lower:
            print(f"      ✓ Found '{term}'")
        else:
            print(f"      ✗ Not found: '{term}'")
    
    # 3. Statistical concerns
    stats_score = scorer._score_statistical_concerns(entities)
    print(f"   3. Statistical Concerns Score: {stats_score:.3f}")
    
    # Check p-values
    p_entities = [e for e in entities if e.ent_type == 'p_value']
    if p_entities:
        for entity in p_entities:
            print(f"      ✓ Found p-value: {entity.value_text}")
            try:
                p_val = float(entity.value_norm)
                if 0.05 <= p_val <= 0.1:
                    print(f"        → Borderline significance (p={p_val})")
                elif p_val > 0.1:
                    print(f"        → Non-significant (p={p_val})")
            except ValueError:
                print(f"        → Could not parse p-value")
    else:
        print(f"      ✗ No p-values found")
    
    # 4. Final S-score calculation
    print()
    print("📊 FINAL S-SCORE CALCULATION:")
    print(f"   Risk Score: {risk_score:.3f} × 0.5 = {risk_score * 0.5:.3f}")
    print(f"   Safety Score: {safety_score:.3f} × 0.3 = {safety_score * 0.3:.3f}")
    print(f"   Stats Score: {stats_score:.3f} × 0.2 = {stats_score * 0.2:.3f}")
    
    final_s_score = (risk_score * 0.5) + (safety_score * 0.3) + (stats_score * 0.2)
    print(f"   Total S-Score: {final_s_score:.3f}")
    
    # Determine tier
    if final_s_score >= scorer.s_thresholds['s3']:
        tier = 'S3'
    elif final_s_score >= scorer.s_thresholds['s2']:
        tier = 'S2'
    elif final_s_score >= scorer.s_thresholds['s1']:
        tier = 'S1'
    else:
        tier = 'S0'
    
    print(f"   S-Tier: {tier}")
    
    # 5. Compare with what we saw in the validation
    print()
    print("🔍 COMPARISON WITH VALIDATION RESULTS:")
    print("   Validation showed: R2(0.700) S0(0.000)")
    print("   Our calculation:  R? S{tier}({final_s_score:.3f})")
    print()
    
    if final_s_score != 0:
        print("   ❌ DISCREPANCY DETECTED!")
        print("   The S-score should NOT be 0 based on this abstract.")
        print("   This suggests there might be an issue in the actual scoring pipeline.")
    else:
        print("   ✅ S-score calculation matches validation results.")
    
    print()
    print("💡 POSSIBLE ISSUES:")
    print("   1. The abstract text might be different in the actual pipeline")
    print("   2. There might be a bug in the scoring logic")
    print("   3. The text extraction might be failing")
    print("   4. The scoring might be using different text than expected")

if __name__ == "__main__":
    debug_real_abstract()
