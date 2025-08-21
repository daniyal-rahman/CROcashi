#!/usr/bin/env python3
"""
Test script for document ingestion functionality.

This script demonstrates the document ingestion workflow for PR/IR and conference abstracts.
"""

import sys
import os
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.db.session import get_db_session
from ncfd.ingest.document_ingest import DocumentIngester
from ncfd.extract.asset_extractor import norm_drug_name, extract_asset_codes

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_asset_extraction():
    """Test asset extraction functionality."""
    print("Testing asset extraction...")
    
    # Test text with various asset codes
    test_text = """
    Our lead compound AB-123 showed promising results in Phase 2 trials.
    The combination therapy with XYZ-456 and BMS-AA-001 demonstrated efficacy.
    We also tested AB123X in preclinical models.
    """
    
    # Extract asset codes
    matches = extract_asset_codes(test_text)
    print(f"Found {len(matches)} asset code matches:")
    for match in matches:
        print(f"  - {match.value_text} (type: {match.alias_type})")
    
    # Test drug name normalization
    test_names = [
        "α-Tocopherol",
        "β-Carotene",
        "γ-Aminobutyric Acid",
        "AB-123®",
        "XYZ-456™"
    ]
    
    print("\nTesting drug name normalization:")
    for name in test_names:
        normalized = norm_drug_name(name)
        print(f"  '{name}' -> '{normalized}'")


def test_document_ingestion():
    """Test document ingestion workflow."""
    print("\nTesting document ingestion...")
    
    try:
        # Get database session
        with get_db_session() as session:
            # Initialize ingester
            ingester = DocumentIngester(session)
            
            # Test company domain discovery
            test_domains = ["example.com", "test-company.com"]
            print(f"Testing discovery for domains: {test_domains}")
            
            # Note: This would actually try to crawl real URLs, so we'll skip for now
            print("  (Skipping actual crawling for safety)")
            
            # Test conference source discovery
            conference_sources = ingester.discover_conference_abstracts()
            print(f"Found {len(conference_sources)} conference sources:")
            for source in conference_sources:
                print(f"  - {source['publisher']}: {source['url']}")
                
    except Exception as e:
        print(f"Database connection failed: {e}")
        print("Make sure the database is running and accessible")


def main():
    """Main test function."""
    print("NCFD Document Ingestion Test")
    print("=" * 40)
    
    # Test asset extraction
    test_asset_extraction()
    
    # Test document ingestion
    test_document_ingestion()
    
    print("\nTest completed!")


if __name__ == "__main__":
    main()
