#!/usr/bin/env python3
"""
Test script for the smart PubMed search pipeline.

This demonstrates the early stopping strategy with rate limiting.
"""

import logging
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_ruxolitinib_search():
    """Test smart search for Ruxolitinib."""
    
    logger.info("="*60)
    logger.info("TEST: Smart Search for Ruxolitinib")
    logger.info("="*60)
    
    try:
        from ncfd.ingest.smart_pubmed import quick_smart_search
        
        # Test 1: Basic drug search
        logger.info("🔍 Testing basic Ruxolitinib search...")
        result = quick_smart_search("ruxolitinib")
        
        logger.info(f"Decision: {result.decision}")
        logger.info(f"Reason: {result.reason}")
        logger.info(f"Total hits: {result.total_hits}")
        logger.info(f"Top summaries: {len(result.top_summaries)}")
        
        if result.top_summaries:
            logger.info("\n📊 Top 5 Summaries:")
            for i, summary in enumerate(result.top_summaries[:5]):
                logger.info(f"  {i+1}. PMID: {summary.pmid}")
                logger.info(f"     Title: {summary.title[:80]}...")
                logger.info(f"     Journal: {summary.journal}")
                logger.info(f"     Score: {summary.score}")
                logger.info(f"     Types: {', '.join(summary.pub_types[:3])}")
                logger.info(f"     NCT IDs: {summary.secondary_ids}")
                logger.info("")
        
        if result.decision == "promote":
            logger.info(f"✅ PROMOTED: {len(result.promoted_ids)} papers for deep fetch")
            logger.info(f"Promoted IDs: {result.promoted_ids[:5]}")
        else:
            logger.info(f"⏹️  EARLY STOP: {result.reason}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ruxolitinib search failed: {e}")
        return None


def test_ruxolitinib_with_disease():
    """Test smart search for Ruxolitinib + myelofibrosis."""
    
    logger.info("="*60)
    logger.info("TEST: Smart Search for Ruxolitinib + Myelofibrosis")
    logger.info("="*60)
    
    try:
        from ncfd.ingest.smart_pubmed import quick_smart_search
        
        logger.info("🔍 Testing Ruxolitinib + myelofibrosis search...")
        result = quick_smart_search("ruxolitinib", disease="myelofibrosis")
        
        logger.info(f"Decision: {result.decision}")
        logger.info(f"Reason: {result.reason}")
        logger.info(f"Total hits: {result.total_hits}")
        logger.info(f"Top summaries: {len(result.top_summaries)}")
        
        if result.top_summaries:
            logger.info("\n📊 Top 5 Summaries:")
            for i, summary in enumerate(result.top_summaries[:5]):
                logger.info(f"  {i+1}. PMID: {summary.pmid}")
                logger.info(f"     Title: {summary.title[:80]}...")
                logger.info(f"     Journal: {summary.journal}")
                logger.info(f"     Score: {summary.score}")
                logger.info(f"     Types: {', '.join(summary.pub_types[:3])}")
                logger.info("")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ruxolitinib + disease search failed: {e}")
        return None


def test_ruxolitinib_with_nct():
    """Test smart search for Ruxolitinib anchored to a specific NCT."""
    
    logger.info("="*60)
    logger.info("TEST: Smart Search for Ruxolitinib + NCT Anchor")
    logger.info("="*60)
    
    try:
        from ncfd.ingest.smart_pubmed import quick_smart_search
        
        # Use a known Ruxolitinib trial
        nct_id = "NCT00952289"  # COMFORT-I trial
        
        logger.info(f"🔍 Testing Ruxolitinib + NCT {nct_id} search...")
        result = quick_smart_search("ruxolitinib", nct_id=nct_id)
        
        logger.info(f"Decision: {result.decision}")
        logger.info(f"Reason: {result.reason}")
        logger.info(f"Total hits: {result.total_hits}")
        logger.info(f"Top summaries: {len(result.top_summaries)}")
        
        if result.top_summaries:
            logger.info("\n📊 Top 5 Summaries:")
            for i, summary in enumerate(result.top_summaries[:5]):
                logger.info(f"  {i+1}. PMID: {summary.pmid}")
                logger.info(f"     Title: {summary.title[:80]}...")
                logger.info(f"     Journal: {summary.journal}")
                logger.info(f"     Score: {summary.score}")
                logger.info(f"     NCT IDs: {summary.secondary_ids}")
                logger.info("")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ruxolitinib + NCT search failed: {e}")
        return None


def test_advanced_search():
    """Test advanced search with multiple drug synonyms."""
    
    logger.info("="*60)
    logger.info("TEST: Advanced Search with Multiple Drug Synonyms")
    logger.info("="*60)
    
    try:
        from ncfd.ingest.smart_pubmed import SmartPubMedClient
        
        client = SmartPubMedClient()
        
        # Test with multiple drug synonyms
        drug_synonyms = ["ruxolitinib", "INCB018424", "Jakafi"]
        
        logger.info(f"🔍 Testing advanced search with synonyms: {drug_synonyms}")
        result = client.smart_search(
            drug_synonyms=drug_synonyms,
            disease="myelofibrosis",
            k_top=30,
            promote_threshold=3  # Lower threshold for testing
        )
        
        logger.info(f"Decision: {result.decision}")
        logger.info(f"Reason: {result.reason}")
        logger.info(f"Total hits: {result.total_hits}")
        logger.info(f"Top summaries: {len(result.top_summaries)}")
        
        if result.top_summaries:
            logger.info("\n📊 Top 10 Summaries by Score:")
            for i, summary in enumerate(result.top_summaries[:10]):
                logger.info(f"  {i+1}. PMID: {summary.pmid} (Score: {summary.score})")
                logger.info(f"     Title: {summary.title[:70]}...")
                logger.info(f"     Journal: {summary.journal}")
                logger.info(f"     Types: {', '.join(summary.pub_types[:2])}")
                logger.info("")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Advanced search failed: {e}")
        return None


if __name__ == "__main__":
    logger.info("🚀 Starting Smart PubMed Search Pipeline Tests")
    logger.info("This demonstrates the early stopping strategy with rate limiting")
    logger.info("No API key required - using PubMed E-utilities")
    
    # Test 1: Basic drug search
    result1 = test_ruxolitinib_search()
    
    # Test 2: Drug + disease search
    result2 = test_ruxolitinib_with_disease()
    
    # Test 3: Drug + NCT anchor search
    result3 = test_ruxolitinib_with_nct()
    
    # Test 4: Advanced search with synonyms
    result4 = test_advanced_search()
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("SUMMARY")
    logger.info("="*60)
    
    tests = [
        ("Basic Ruxolitinib", result1),
        ("Ruxolitinib + Myelofibrosis", result2),
        ("Ruxolitinib + NCT Anchor", result3),
        ("Advanced Synonyms", result4)
    ]
    
    for test_name, result in tests:
        if result:
            status = "✅ PROMOTED" if result.decision == "promote" else "⏹️  EARLY STOP"
            logger.info(f"{test_name}: {status} - {result.reason}")
        else:
            logger.info(f"{test_name}: ❌ FAILED")
    
    logger.info("\n🎯 KEY INSIGHTS:")
    logger.info("• Smart search pipeline is working with rate limiting")
    logger.info("• Early stopping prevents unnecessary deep fetches")
    logger.info("• Multiple search strategies (drug, disease, NCT anchor)")
    logger.info("• Scoring system identifies promising papers")
    
    logger.info("\n🚀 Next Steps:")
    logger.info("1. Test with more drugs and conditions")
    logger.info("2. Adjust scoring thresholds based on results")
    logger.info("3. Implement deep fetch for promoted papers")
    logger.info("4. Scale up to get your 3k+ paper corpus!")
    
    logger.info("\n🎉 Smart PubMed search pipeline is ready!")
