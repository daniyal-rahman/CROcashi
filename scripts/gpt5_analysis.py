#!/usr/bin/env python3
"""
Run GPT-5 analysis on trials.
"""

import json
import sys
import asyncio
from pathlib import Path

from ncfd.synthesis.independent_llm_analysis import IndependentLLMAnalysis, trigger_independent_llm_analysis_sync
from ncfd.config import get_config


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="GPT-5 Thinking Analysis for Clinical Trials",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic analysis
  python scripts/gpt5_analysis.py --trial-id NCT01234567 --indication "NSCLC" --phase 3 --p-fail 0.85

  # With API key from environment
  OPENAI_API_KEY=your_key python scripts/gpt5_analysis.py --trial-id NCT01234567 --indication "NSCLC" --phase 3

  # Save results to file
  python scripts/gpt5_analysis.py --trial-id NCT01234567 --indication "NSCLC" --phase 3 --out results.json

  # Verbose output
  python scripts/gpt5_analysis.py --trial-id NCT01234567 --indication "NSCLC" --phase 3 --verbose
        """
    )
    
    # Required arguments
    parser.add_argument("--trial-id", required=True, help="Internal trial ID")
    parser.add_argument("--nct-id", required=True, help="ClinicalTrials.gov ID")
    parser.add_argument("--indication", required=True, help="Disease indication")
    parser.add_argument("--phase", required=True, help="Trial phase")
    
    # Optional arguments
    parser.add_argument("--primary-endpoint", help="Primary endpoint")
    parser.add_argument("--mechanism", help="Mechanism of action")
    parser.add_argument("--p-fail", type=float, default=0.0, help="Deterministic P_fail score")
    parser.add_argument("--api-key", help="OpenAI API key (or set OPENAI_API_KEY env var)")
    parser.add_argument("--out", help="Output file for results (JSON)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OpenAI API key required.")
        print("Set OPENAI_API_KEY in your .env file or use --api-key parameter")
        return 1
    
    # Validate inputs
    if args.p_fail < 0 or args.p_fail > 1:
        print("❌ Error: P_fail must be between 0 and 1")
        return 1
    
    if args.phase not in ["1", "2", "3", "4"]:
        print("❌ Error: Phase must be 1, 2, 3, or 4")
        return 1
    
    # Print analysis parameters
    if args.verbose:
        print("🔬 GPT-5 Thinking Analysis")
        print("=" * 50)
        print(f"Trial ID: {args.trial_id}")
        print(f"NCT ID: {args.nct_id}")
        print(f"Indication: {args.indication}")
        print(f"Phase: {args.phase}")
        print(f"Primary Endpoint: {args.primary_endpoint or 'Not specified'}")
        print(f"Mechanism: {args.mechanism or 'Not specified'}")
        print(f"Deterministic P_fail: {args.p_fail:.3f}")
        print()
    
    try:
        # Run analysis
        if args.verbose:
            print("🔄 Running GPT-5 thinking analysis...")
        
        result = trigger_independent_llm_analysis_sync(
            trial_id=args.trial_id,
            nct_id=args.nct_id,
            indication=args.indication,
            phase=args.phase,
            primary_endpoint=args.primary_endpoint,
            mechanism=args.mechanism,
            p_fail=args.p_fail
        )
        
        if args.verbose:
            print("✅ Analysis completed!")
            print()
        
        # Display results
        if args.verbose:
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
        
        # Save to file if requested
        if args.out:
            with open(args.out, 'w') as f:
                json.dump(result, f, indent=2)
            if args.verbose:
                print(f"💾 Results saved to {args.out}")
        
        # Return success
        return 0
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
