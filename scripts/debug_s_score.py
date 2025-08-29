#!/usr/bin/env python3
"""
Debug S-score calculation step by step.

Shows exactly how the S-score is calculated and why it might be 0.
"""

import sys
import os
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ncfd.score.simple_rs_scorer import SimpleRSScorer
from ncfd.extract.abstract_features import AbstractFeatureExtractor

def debug_s_score_calculation():
    """Debug S-score calculation step by step."""
    
    # Initialize components
    scorer = SimpleRSScorer()
    extractor = AbstractFeatureExtractor()
    
    print("🔍 DEBUGGING S-SCORE CALCULATION")
    print("=" * 60)
    
    # Show configuration
    print("📋 S-SCORE CONFIGURATION:")
    print(f"   S tier thresholds: {scorer.s_thresholds}")
    print(f"   Risk phrases: {scorer.risk_phrases}")
    print(f"   Component weights: Risk(0.5), Safety(0.3), Stats(0.2)")
    print()
    
    # Test with a sample abstract that should have some S-score
    sample_abstract = """
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
    
    print("📄 SAMPLE ABSTRACT:")
    print(sample_abstract)
    print()
    
    # Extract entities
    entities = extractor.extract_all_features(sample_abstract)
    print("🔍 EXTRACTED ENTITIES:")
    for entity in entities:
        print(f"   {entity.ent_type}: {entity.value_text} (confidence: {entity.confidence:.2f})")
    print()
    
    # Calculate S-score step by step
    print("🧮 S-SCORE CALCULATION STEP BY STEP:")
    
    # 1. Risk signals
    doc_lower = sample_abstract.lower()
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
    
    # Check confidence intervals
    ci_entities = [e for e in entities if e.ent_type == 'ci']
    if ci_entities:
        for entity in ci_entities:
            print(f"      ✓ Found CI: {entity.value_text}")
    else:
        print(f"      ✗ No confidence intervals found")
    
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
    
    # 5. Analysis
    print()
    print("🔍 ANALYSIS:")
    if final_s_score == 0:
        print("   ❌ S-score is 0 because:")
        if risk_score == 0:
            print("      - No risk signal phrases found in the text")
        if safety_score == 0:
            print("      - No safety signal terms found in the text")
        if stats_score == 0:
            print("      - No statistical concerns detected")
        print("   💡 This might indicate the text doesn't contain negative signals")
        print("   💡 Or the risk/safety phrases are too specific")
    else:
        print("   ✅ S-score > 0 indicates some negative signals were detected")
    
    print()
    print("💡 SUGGESTIONS FOR IMPROVEMENT:")
    print("   1. Expand risk phrases to include more common negative language")
    print("   2. Add more safety signal terms")
    print("   3. Consider including 'trend', 'borderline', 'post-hoc' as risk signals")
    print("   4. Add more statistical concern patterns")

if __name__ == "__main__":
    debug_s_score_calculation()
