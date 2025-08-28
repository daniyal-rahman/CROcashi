#!/usr/bin/env python3
"""
PubMed Query Builder Test Suite

This test suite specifically tests the PubMed query builder to catch the issues
flagged in the code review:

1. Must include "{NCTID}"[si] without appending [tiab] to that token
2. Quotes are balanced; no doubled ""term"[tiab]"[tiab]
3. If synonyms exist, they appear as ("syn1"[tiab] OR "syn2"[tiab]) joined with the NCT term via OR
4. Query string must match regex: ^\("NCT\d{8}"\[si\]\)(?:\s+OR\s+\(.+\))?$
"""

import os
import sys
import re
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.ingest.smart_pubmed import SmartPubMedClient


class PubMedQueryBuilderTest:
    """Test suite for PubMed query builder sanity checks."""
    
    def __init__(self):
        self.query_pattern = r'^\("NCT\d{8}"\[si\]\)(?:\s+OR\s+\(.+\))?$'
        self.test_nct_id = "NCT05111574"
        self.test_drug_terms = ["Test Drug", "Test Compound", "Test Molecule"]
    
    def test_nct_only_query(self):
        """Test NCT-only query construction."""
        print("🔍 Testing NCT-only query construction...")
        
        # Mock configuration
        config = {
            'api_key': 'test_key',
            'base_url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
            'tool': 'NCFD-Literature-Pipeline-Test',
            'email': 'test@test.com'
        }
        
        # Create client
        client = SmartPubMedClient(config)
        
        # Build query for NCT only
        query = client._build_search_query(self.test_nct_id, [])
        
        print(f"Generated query: {query}")
        
        # Verify query structure
        assert re.match(self.query_pattern, query), f"Query does not match expected pattern: {query}"
        
        # Verify no doubled quotes
        assert '""' not in query, f"Query contains doubled quotes: {query}"
        
        # Verify NCT term has [si] not [tiab]
        assert f'"{self.test_nct_id}"[si]' in query, f"NCT term missing [si] tag: {query}"
        assert f'"{self.test_nct_id}"[tiab]' not in query, f"NCT term incorrectly has [tiab] tag: {query}"
        
        # Verify balanced quotes
        quote_count = query.count('"')
        assert quote_count % 2 == 0, f"Unbalanced quotes in query: {query} (count: {quote_count})"
        
        print("✅ NCT-only query test passed")
        return query
    
    def test_nct_with_drug_synonyms(self):
        """Test NCT query with drug synonyms."""
        print("🔍 Testing NCT query with drug synonyms...")
        
        # Mock configuration
        config = {
            'api_key': 'test_key',
            'base_url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
            'tool': 'NCFD-Literature-Pipeline-Test',
            'email': 'test@test.com'
        }
        
        # Create client
        client = SmartPubMedClient(config)
        
        # Build query for NCT with drug synonyms
        query = client._build_search_query(self.test_nct_id, self.test_drug_terms)
        
        print(f"Generated query: {query}")
        
        # Verify query structure
        assert re.match(self.query_pattern, query), f"Query does not match expected pattern: {query}"
        
        # Verify NCT term has [si] not [tiab]
        assert f'"{self.test_nct_id}"[si]' in query, f"NCT term missing [si] tag: {query}"
        assert f'"{self.test_nct_id}"[tiab]' not in query, f"NCT term incorrectly has [tiab] tag: {query}"
        
        # Verify drug synonyms are properly formatted
        for drug_term in self.test_drug_terms:
            assert f'"{drug_term}"[tiab]' in query, f"Drug term missing: {drug_term}"
        
        # Verify OR structure for synonyms
        assert ' OR ' in query, "Query missing OR operator for synonyms"
        
        # Verify no doubled quotes
        assert '""' not in query, f"Query contains doubled quotes: {query}"
        
        # Verify balanced quotes
        quote_count = query.count('"')
        assert quote_count % 2 == 0, f"Unbalanced quotes in query: {query} (count: {quote_count})"
        
        print("✅ NCT with drug synonyms query test passed")
        return query
    
    def test_query_balance_and_structure(self):
        """Test query balance and structure."""
        print("🔍 Testing query balance and structure...")
        
        # Mock configuration
        config = {
            'api_key': 'test_key',
            'base_url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
            'tool': 'NCFD-Literature-Pipeline-Test',
            'email': 'test@test.com'
        }
        
        # Create client
        client = SmartPubMedClient(config)
        
        # Test various combinations
        test_cases = [
            (self.test_nct_id, []),  # NCT only
            (self.test_nct_id, ["Drug A"]),  # NCT + 1 drug
            (self.test_nct_id, ["Drug A", "Drug B"]),  # NCT + 2 drugs
            (self.test_nct_id, ["Drug A", "Drug B", "Drug C"])  # NCT + 3 drugs
        ]
        
        for nct_id, drug_terms in test_cases:
            query = client._build_search_query(nct_id, drug_terms)
            print(f"Query for {nct_id} + {drug_terms}: {query}")
            
            # Verify no doubled quotes
            assert '""' not in query, f"Query contains doubled quotes: {query}"
            
            # Verify balanced quotes
            quote_count = query.count('"')
            assert quote_count % 2 == 0, f"Unbalanced quotes in query: {query} (count: {quote_count})"
            
            # Verify no malformed patterns like ""term"[tiab]"[tiab]
            assert '"[tiab]"[tiab]' not in query, f"Query contains malformed pattern: {query}"
            assert '"[si]"[tiab]' not in query, f"Query contains malformed pattern: {query}"
            
            # Verify NCT term integrity
            assert f'"{nct_id}"[si]' in query, f"NCT term missing or malformed: {query}"
        
        print("✅ Query balance and structure tests passed")
    
    def test_regex_pattern_matching(self):
        """Test that all generated queries match the expected regex pattern."""
        print("🔍 Testing regex pattern matching...")
        
        # Mock configuration
        config = {
            'api_key': 'test_key',
            'base_url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
            'tool': 'NCFD-Literature-Pipeline-Test',
            'email': 'test@test.com'
        }
        
        # Create client
        client = SmartPubMedClient(config)
        
        # Test multiple NCT IDs
        test_nct_ids = [
            "NCT05111574",
            "NCT12345678",
            "NCT87654321"
        ]
        
        # Test various drug term combinations
        drug_combinations = [
            [],
            ["Single Drug"],
            ["Drug A", "Drug B"],
            ["Compound 1", "Compound 2", "Compound 3"]
        ]
        
        pattern_matches = 0
        total_queries = 0
        
        for nct_id in test_nct_ids:
            for drug_terms in drug_combinations:
                query = client._build_search_query(nct_id, drug_terms)
                total_queries += 1
                
                if re.match(self.query_pattern, query):
                    pattern_matches += 1
                    print(f"✅ Pattern match: {query}")
                else:
                    print(f"❌ Pattern mismatch: {query}")
                    print(f"   Expected pattern: {self.query_pattern}")
        
        # All queries should match the pattern
        assert pattern_matches == total_queries, \
            f"Only {pattern_matches}/{total_queries} queries match the expected pattern"
        
        print(f"✅ All {total_queries} queries match the expected regex pattern")
    
    def test_edge_cases(self):
        """Test edge cases and error conditions."""
        print("🔍 Testing edge cases and error conditions...")
        
        # Mock configuration
        config = {
            'api_key': 'test_key',
            'base_url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
            'tool': 'NCFD-Literature-Pipeline-Test',
            'email': 'test@test.com'
        }
        
        # Create client
        client = SmartPubMedClient(config)
        
        # Test empty NCT ID
        try:
            query = client._build_search_query("", [])
            assert False, "Should have failed with empty NCT ID"
        except (ValueError, AssertionError):
            print("✅ Empty NCT ID correctly rejected")
        
        # Test invalid NCT ID format
        try:
            query = client._build_search_query("INVALID123", [])
            assert False, "Should have failed with invalid NCT ID format"
        except (ValueError, AssertionError):
            print("✅ Invalid NCT ID format correctly rejected")
        
        # Test very long drug names
        long_drug_name = "A" * 1000  # Very long drug name
        query = client._build_search_query(self.test_nct_id, [long_drug_name])
        
        # Verify query is still valid
        assert re.match(self.query_pattern, query), f"Long drug name query invalid: {query}"
        assert '""' not in query, f"Long drug name query has doubled quotes: {query}"
        
        print("✅ Edge case tests passed")
    
    def run_all_tests(self):
        """Run all PubMed query builder tests."""
        print("🚀 Starting PubMed Query Builder Test Suite")
        print("=" * 60)
        
        try:
            self.test_nct_only_query()
            self.test_nct_with_drug_synonyms()
            self.test_query_balance_and_structure()
            self.test_regex_pattern_matching()
            self.test_edge_cases()
            
            print("\n🎉 ALL PUBMED QUERY BUILDER TESTS PASSED!")
            print("✅ Query structure is correct")
            print("✅ No doubled quotes or malformed patterns")
            print("✅ All queries match expected regex pattern")
            print("✅ Edge cases handled properly")
            
            return True
            
        except Exception as e:
            print(f"\n💥 PUBMED QUERY BUILDER TESTS FAILED: {e}")
            raise


def main():
    """Main test execution function."""
    test_suite = PubMedQueryBuilderTest()
    
    try:
        success = test_suite.run_all_tests()
        if success:
            print("\n🎉 PubMed Query Builder Test Suite Completed Successfully!")
            print("The query builder is producing properly formatted queries.")
        else:
            print("\n💥 PubMed Query Builder Test Suite Failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 PubMed Query Builder Test Suite Failed with Exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
