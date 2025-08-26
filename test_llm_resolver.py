#!/usr/bin/env python3
"""
Test file for LLM resolver functionality
Tests the Janssen Biotech, Inc. -> J&J subsidiary resolution case
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.mapping.llm_decider import (
    decide_with_llm_research,
    _fuzzy_company_match,
    _enhanced_system_prompt,
    _enhanced_user_prompt,
    fetch_ctgov_metadata
)
from ncfd.db.session import get_session
from ncfd.mapping.llm_decider import ClinicalTrialMetadata
from sqlalchemy import text

def test_janssen_biotech_resolution():
    """Test LLM resolution for Janssen Biotech, Inc. -> J&J"""
    
    print("🧪 Testing LLM Resolver for Janssen Biotech, Inc.")
    print("=" * 60)
    
    # Test case
    nct_id = "NCT01314118"
    sponsor_text = "Janssen Biotech, Inc."
    
    print(f"NCT ID: {nct_id}")
    print(f"Sponsor: {sponsor_text}")
    print(f"Expected: Should resolve to JOHNSON & JOHNSON (company_id 27)")
    print()
    
    # Test 1: Check if we can fetch trial metadata
    print("📋 Test 1: Fetching ClinicalTrials.gov metadata...")
    try:
        trial_metadata = fetch_ctgov_metadata(nct_id)
        if trial_metadata:
            print(f"✅ Successfully fetched metadata:")
            print(f"   - Sponsor: {trial_metadata.sponsor}")
            print(f"   - Title: {trial_metadata.title[:100]}...")
            print(f"   - Phase: {trial_metadata.phase}")
        else:
            print("❌ Failed to fetch trial metadata")
            return
    except Exception as e:
        print(f"❌ Error fetching metadata: {e}")
        return
    
    print()
    
    # Test 2: Check company matching logic
    print("🔍 Test 2: Testing company matching logic...")
    
    # Set up proper database connection for testing
    db_url = "postgresql://ncfd:ncfd@localhost:5433/ncfd"
    print(f"   Using database: {db_url}")
    
    with get_session(db_url) as session:
        # Test direct company name matching
        test_names = [
            "Janssen Biotech, Inc.",
            "Janssen Biotech",
            "Janssen",
            "Johnson & Johnson",
            "J&J"
        ]
        
        for test_name in test_names:
            company_id, confidence, match_type = _fuzzy_company_match(test_name, session)
            print(f"   '{test_name}' -> company_id: {company_id}, confidence: {confidence:.3f}, type: {match_type}")
        
        # Check what J&J companies exist
        print("\n   Existing J&J related companies:")
        result = session.execute(
            text("SELECT company_id, name FROM companies WHERE name ILIKE '%johnson%' OR name ILIKE '%J&J%' OR name ILIKE '%JNJ%'")
        ).fetchall()
        for row in result:
            print(f"     {row[0]}: {row[1]}")
    
    print()
    
    # Test 3: Check LLM prompts
    print("🤖 Test 3: LLM Prompt Analysis...")
    system_prompt = _enhanced_system_prompt()
    user_prompt = _enhanced_user_prompt(nct_id, trial_metadata)
    
    print("System Prompt:")
    print(f"   {system_prompt}")
    print()
    print("User Prompt (first 200 chars):")
    print(f"   {user_prompt[:200]}...")
    
    print()
    
    # Test 4: Check environment variables
    print("🔧 Test 4: Environment Configuration...")
    print(f"   OPENAI_MODEL_RESOLVER: {os.getenv('OPENAI_MODEL_RESOLVER', 'NOT SET')}")
    print(f"   RESOLVER_DISABLE_PROB: {os.getenv('RESOLVER_DISABLE_PROB', 'NOT SET')}")
    print(f"   OPENAI_API_KEY: {'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
    
    print()
    
    # Test 5: Try actual LLM resolution (if API key available)
    print("🚀 Test 5: Attempting LLM Resolution...")
    if os.getenv('OPENAI_API_KEY'):
        try:
            with get_session(db_url) as session:
                llm_dec, raw = decide_with_llm_research(
                    run_id="test-janssen",
                    nct_id=nct_id,
                    session=session,
                    context={}
                )
                
                print(f"✅ LLM Decision:")
                print(f"   Mode: {llm_dec.mode}")
                print(f"   Company ID: {llm_dec.company_id}")
                print(f"   Confidence: {llm_dec.confidence:.3f}")
                print(f"   Rationale: {llm_dec.rationale[:200]}...")
                
                if llm_dec.research_evidence:
                    print(f"   Research Evidence Keys: {list(llm_dec.research_evidence.keys())}")
                
        except Exception as e:
            print(f"❌ LLM Resolution failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("⚠️  Skipping LLM test - no OpenAI API key")
    
    print()
    print("=" * 60)
    print("🎯 Summary of Issues Found:")
    print("1. LLM path not being called due to _llm_enabled() returning False")
    print("2. Company matching may not handle subsidiary relationships well")
    print("3. Need to ensure LLM is called for low-confidence probabilistic decisions")

def test_llm_enabled_logic():
    """Test the _llm_enabled function logic"""
    
    print("\n🔧 Testing _llm_enabled Logic")
    print("=" * 40)
    
    # Import the function
    from ncfd.mapping.cli import _llm_enabled
    
    # Test cases
    test_cases = [
        ("auto", "RESOLVER_DISABLE_PROB=0"),
        ("auto", "RESOLVER_DISABLE_PROB=1"),
        ("llm", "RESOLVER_DISABLE_PROB=0"),
        ("llm", "RESOLVER_DISABLE_PROB=1"),
    ]
    
    for decider, env_setting in test_cases:
        # Set environment variable
        if "=" in env_setting:
            key, value = env_setting.split("=")
            os.environ[key] = value
        
        result = _llm_enabled(decider)
        print(f"   decider='{decider}', {env_setting} -> {result}")
        
        # Clean up
        if "=" in env_setting:
            key, _ = env_setting.split("=")
            if key in os.environ:
                del os.environ[key]

if __name__ == "__main__":
    print("🧪 LLM Resolver Test Suite")
    print("=" * 60)
    
    # Test the LLM enabled logic first
    test_llm_enabled_logic()
    
    # Test the Janssen Biotech case
    test_janssen_biotech_resolution()
    
    print("\n✅ Test suite completed!")
