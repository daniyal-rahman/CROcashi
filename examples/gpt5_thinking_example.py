#!/usr/bin/env python3
"""
Example of using the GPT-5 thinking hook for advanced analysis.
"""

import json
import sys
import asyncio
from pathlib import Path

from ncfd.synthesis.independent_llm_analysis import IndependentLLMAnalysis, trigger_independent_llm_analysis_sync
from ncfd.config import get_config


def create_real_trial_data():
    """Create real trial data for demonstration."""
    return {
        "trial_id": "example_trial_001",
        "nct_id": "NCT01234567",
        "indication": "Advanced Non-Small Cell Lung Cancer",
        "phase": "3",
        "primary_endpoint": "Overall Survival",
        "mechanism": "PD-1 inhibitor",
        "p_fail": 0.85  # Above GPT-5 threshold
    }


async def run_async_example():
    """Run the async example with real API calls."""
    print("🤖 GPT-5 Thinking Hook Example (Async)")
    print("=" * 50)
    
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Please set your OpenAI API key in the .env file")
        return 1
    
    print("✅ Using OpenAI API key from environment")
    print()
    
    # Create trial data
    trial_data = create_real_trial_data()
    
    print(f"Trial: {trial_data['nct_id']} ({trial_data['phase']}) in {trial_data['indication']}")
    print(f"Primary Endpoint: {trial_data['primary_endpoint']}")
    print(f"Mechanism: {trial_data['mechanism']}")
    print(f"Deterministic P_fail: {trial_data['p_fail']:.3f}")
    print()
    
    # Initialize GPT-5 thinking hook
    hook = IndependentLLMAnalysis(api_key)
    
    try:
        print("🔄 Step 1: Literature Review Agent")
        print("   Searching for relevant trials and papers...")
        
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
        
        # Display top trials
        if literature_result.relevant_trials:
            print("   📋 Top Relevant Trials:")
            for i, trial in enumerate(literature_result.relevant_trials[:3]):
                print(f"      {i+1}. {trial.get('nct_id', 'N/A')}: {trial.get('title', 'N/A')}")
                print(f"         Results: {trial.get('results', 'N/A')}, Relevance: {trial.get('relevance_score', 0):.2f}")
            print()
        
        print("🔄 Step 2: Independent Analysis Agent")
        print("   Analyzing evidence and making predictions...")
        
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
        
        # Display analysis results
        print("📊 Analysis Results:")
        print(f"   Mechanistic Analysis: {analysis_result.mechanistic_analysis[:100]}...")
        print(f"   Class Prior Analysis: {analysis_result.class_prior_analysis[:100]}...")
        print()
        
        if analysis_result.independent_risk_factors:
            print("   🔍 Independent Risk Factors:")
            for risk in analysis_result.independent_risk_factors:
                print(f"      • {risk}")
            print()
        
        if analysis_result.strong_red_flags:
            print("   🚨 Strong Red Flags:")
            for flag in analysis_result.strong_red_flags:
                print(f"      ⚠️  {flag}")
            print()
        
        if analysis_result.additional_insights:
            print("   💡 Additional Insights:")
            for insight in analysis_result.additional_insights:
                print(f"      • {insight}")
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
        print()
        
        print("✅ GPT-5 Thinking Analysis Complete!")
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return 1
    
    return 0


def run_sync_example():
    """Run the synchronous example."""
    print("🤖 GPT-5 Thinking Hook Example (Sync)")
    print("=" * 50)
    
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Please set your OpenAI API key in the .env file")
        return 1
    
    print("✅ Using OpenAI API key from environment")
    print()
    
    # Create trial data
    trial_data = create_real_trial_data()
    
    print(f"Trial: {trial_data['nct_id']} ({trial_data['phase']}) in {trial_data['indication']}")
    print(f"Primary Endpoint: {trial_data['primary_endpoint']}")
    print(f"Mechanism: {trial_data['mechanism']}")
    print(f"Deterministic P_fail: {trial_data['p_fail']:.3f}")
    print()
    
    try:
        print("🔄 Running complete GPT-5 analysis...")
        
        # Run complete analysis
        result = trigger_independent_llm_analysis_sync(
            trial_id=trial_data["trial_id"],
            nct_id=trial_data["nct_id"],
            indication=trial_data["indication"],
            phase=trial_data["phase"],
            primary_endpoint=trial_data["primary_endpoint"],
            mechanism=trial_data["mechanism"],
            p_fail=trial_data["p_fail"]
        )
        
        print("✅ Analysis completed!")
        print()
        
        # Display results
        print("📊 Results Summary:")
        print(f"   GPT-5 P_fail: {result.get('gpt5_p_fail', 'N/A')}")
        print(f"   Confidence Level: {result.get('confidence_level', 'N/A')}")
        print(f"   Literature Confidence: {result.get('literature_confidence', 'N/A')}")
        print(f"   Relevant Trials: {result.get('relevant_trials_count', 'N/A')}")
        print(f"   Relevant Papers: {result.get('relevant_papers_count', 'N/A')}")
        print(f"   Analysis Quality: {result.get('analysis_quality', 'N/A')}")
        print(f"   Disagreement Level: {result.get('disagreement_level', 'N/A')}")
        print(f"   Recommendation Strength: {result.get('recommendation_strength', 'N/A')}")
        print()
        
        if result.get('strong_red_flags'):
            print("🚨 Strong Red Flags:")
            for flag in result['strong_red_flags']:
                print(f"   ⚠️  {flag}")
            print()
        
        if result.get('recommendation'):
            print("📋 Recommendation:")
            print(f"   {result['recommendation']}")
            print()
        
        print("✅ GPT-5 Thinking Analysis Complete!")
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return 1
    
    return 0


def main():
    """Main function to run examples."""
    import argparse
    
    parser = argparse.ArgumentParser(description="GPT-5 Thinking Hook Example")
    parser.add_argument("--mode", choices=["async", "sync"], default="sync", 
                       help="Run mode: async or sync (default: sync)")
    
    args = parser.parse_args()
    
    if args.mode == "async":
        return asyncio.run(run_async_example())
    else:
        return run_sync_example()


if __name__ == "__main__":
    exit(main())
