#!/usr/bin/env python3
"""
Detailed GPT-5 analysis for the Cassava trial.
"""

import json
import sys
import asyncio
from pathlib import Path

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.catalyst.backtest import BacktestRunner
from ncfd.config import get_config


async def analyze_cassava_trial():
    """Run detailed analysis on the Cassava trial."""
    print("🔬 Cassava Trial GPT-5 Analysis")
    print("=" * 60)
    
    # Cassava trial details
    trial_data = {
        "trial_id": "cassava_001",
        "nct_id": "NCT04388254",
        "indication": "Alzheimer's Disease",
        "phase": "2",
        "primary_endpoint": "ADAS-Cog11",
        "mechanism": "simufilam (small molecule filamin A inhibitor)",
        "p_fail": 0.809,
        "design": "randomized withdrawal after open-label extension",
        "sample_size": 155,
        "results": "0.57 point difference (not significant)",
        "subgroups": ["Mild AD (p=0.03)", "Moderate AD (p=0.048)"]
    }
    
    print(f"Trial: {trial_data['nct_id']} (Phase {trial_data['phase']})")
    print(f"Indication: {trial_data['indication']}")
    print(f"Primary Endpoint: {trial_data['primary_endpoint']}")
    print(f"Mechanism: {trial_data['mechanism']}")
    print(f"Design: {trial_data['design']}")
    print(f"Sample Size: {trial_data['sample_size']}")
    print(f"Results: {trial_data['results']}")
    print(f"Subgroups: {', '.join(trial_data['subgroups'])}")
    print(f"Deterministic P_fail: {trial_data['p_fail']:.3f}")
    print()
    
    # Initialize GPT-5 thinking hook
    hook = GPT5ThinkingHook()
    
    try:
        print("🔄 Step 1: Literature Review Agent")
        print("   Searching for relevant Alzheimer's trials and papers...")
        print()
        
        # Step 1: Literature Review
        literature_result = await hook.literature_agent.review_literature(
            trial_id=trial_data["trial_id"],
            nct_id=trial_data["nct_id"],
            indication=trial_data["indication"],
            phase=trial_data["phase"],
            primary_endpoint=trial_data["primary_endpoint"],
            mechanism=trial_data["mechanism"]
        )
        
        print(f"   ✅ Found {len(literature_result.relevant_trials)} relevant trials")
        print(f"   ✅ Found {len(literature_result.relevant_papers)} relevant papers")
        print(f"   ✅ Confidence: {literature_result.confidence_score:.2f}")
        print()
        
        # Display relevant trials
        if literature_result.relevant_trials:
            print("   📋 Relevant Trials Found:")
            for i, trial in enumerate(literature_result.relevant_trials[:5]):
                print(f"      {i+1}. {trial.get('nct_id', 'N/A')}: {trial.get('title', 'N/A')}")
                print(f"         Phase: {trial.get('phase', 'N/A')}, Results: {trial.get('results', 'N/A')}")
                print(f"         Relevance: {trial.get('relevance_score', 0):.2f}")
                print(f"         Key: {trial.get('key_findings', 'N/A')}")
                print()
        
        # Display relevant papers
        if literature_result.relevant_papers:
            print("   📚 Relevant Papers Found:")
            for i, paper in enumerate(literature_result.relevant_papers[:3]):
                print(f"      {i+1}. {paper.get('title', 'N/A')} ({paper.get('year', 'N/A')})")
                print(f"         Authors: {paper.get('authors', 'N/A')}")
                print(f"         Relevance: {paper.get('relevance_score', 0):.2f}")
                print(f"         Key: {paper.get('key_findings', 'N/A')}")
                print()
        
        print("🔄 Step 2: Independent Analysis Agent")
        print("   Analyzing evidence and making predictions...")
        print()
        
        # Step 2: Independent Analysis
        analysis_result = await hook.analysis_agent.analyze_independently(
            trial_id=trial_data["trial_id"],
            nct_id=trial_data["nct_id"],
            indication=trial_data["indication"],
            phase=trial_data["phase"],
            primary_endpoint=trial_data["primary_endpoint"],
            p_fail=trial_data["p_fail"],
            literature_result=literature_result
        )
        
        print(f"   ✅ GPT-5 P_fail: {analysis_result.gpt5_p_fail:.3f}")
        print(f"   ✅ Confidence Level: {analysis_result.confidence_level}")
        print(f"   ✅ Agreement with Deterministic: {analysis_result.agreement_with_deterministic:.2f}")
        print()
        
        # Display detailed analysis
        print("📊 Detailed Analysis Results:")
        print()
        
        print("🔬 Mechanistic Analysis:")
        print(f"   {analysis_result.mechanistic_analysis}")
        print()
        
        print("📈 Class Prior Analysis:")
        print(f"   {analysis_result.class_prior_analysis}")
        print()
        
        if analysis_result.independent_risk_factors:
            print("🔍 Independent Risk Factors:")
            for risk in analysis_result.independent_risk_factors:
                print(f"   • {risk}")
            print()
        
        if analysis_result.additional_insights:
            print("💡 Additional Insights:")
            for insight in analysis_result.additional_insights:
                print(f"   • {insight}")
            print()
        
        if analysis_result.strong_red_flags:
            print("🚨 Strong Red Flags:")
            for flag in analysis_result.strong_red_flags:
                print(f"   ⚠️  {flag}")
            print()
        
        print("📋 Final Recommendation:")
        print(f"   {analysis_result.recommendation}")
        print()
        
        # Calculate summary metrics
        disagreement = abs(trial_data["p_fail"] - analysis_result.gpt5_p_fail)
        quality = hook._calculate_analysis_quality(literature_result, analysis_result)
        
        print("📈 Summary Metrics:")
        print(f"   Analysis Quality: {quality}")
        print(f"   Disagreement Level: {disagreement:.3f}")
        print(f"   Recommendation Strength: {len(analysis_result.strong_red_flags)} strong red flags")
        print(f"   Literature Confidence: {literature_result.confidence_score:.2f}")
        print(f"   Analysis Confidence: {analysis_result.confidence_level}")
        print()
        
        print("✅ Cassava Trial Analysis Complete!")
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(asyncio.run(analyze_cassava_trial()))
