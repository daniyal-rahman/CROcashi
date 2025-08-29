#!/usr/bin/env python3
"""
Test script to verify the fixes for trial_query_builder.py and mapper.py.
"""

import asyncio
import logging
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ncfd.ingest.pubmed.trial_query_builder import TrialQueryBuilder
from ncfd.ingest.pubmed.mapper import PubMedMapper

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_trial_query_builder_fixes():
    """Test the fixes in TrialQueryBuilder."""
    logger.info("🔍 Testing TrialQueryBuilder fixes...")
    
    try:
        builder = TrialQueryBuilder()
        
        # Test 1: List truncation fix
        logger.info("Testing list truncation fix...")
        asset_aliases = [f"Asset{i}" for i in range(15)]  # More than max_asset_aliases (10)
        indication_terms = [f"Indication{i}" for i in range(20)]  # More than max_indication_terms (15)
        
        result = builder.build_trial_query(
            trial_id="TEST001",
            asset_aliases=asset_aliases,
            indication_terms=indication_terms,
            trial_phase="PHASE3"
        )
        
        # Verify that the returned metadata uses the trimmed lists
        metadata = result['metadata']
        actual_assets = metadata['asset_aliases']
        actual_indications = metadata['indication_terms']
        
        if len(actual_assets) == 10 and len(actual_indications) == 15:
            logger.info("✅ List truncation fix working correctly")
        else:
            logger.error(f"❌ List truncation not working: got {len(actual_assets)} assets, {len(actual_indications)} indications")
            return False
        
        # Test 2: Publication type tag fix
        logger.info("Testing publication type tag fix...")
        query = result['query_string']
        if '[pt]' in query and '[ptyp]' not in query:
            logger.info("✅ Publication type tag fix working correctly")
        else:
            logger.error("❌ Publication type tag fix not working")
            return False
        
        # Test 3: Field tags fix
        logger.info("Testing field tags fix...")
        if '[tiab]' in query:
            logger.info("✅ Field tags fix working correctly")
        else:
            logger.error("❌ Field tags fix not working")
            return False
        
        # Test 4: NCT boost fix
        logger.info("Testing NCT boost fix...")
        result_with_nct = builder.build_trial_query(
            trial_id="TEST002",
            asset_aliases=["Remdesivir"],
            indication_terms=["COVID-19"],
            trial_nct="NCT04257656"
        )
        
        query_with_nct = result_with_nct['query_string']
        if '[si]' in query_with_nct:
            logger.info("✅ NCT boost fix working correctly")
        else:
            logger.error("❌ NCT boost fix not working")
            return False
        
        # Test 5: Safe query trimming
        logger.info("Testing safe query trimming...")
        # Create a very long query
        long_asset_aliases = [f"VeryLongAssetName{i}" for i in range(50)]
        long_result = builder.build_trial_query(
            trial_id="TEST003",
            asset_aliases=long_asset_aliases,
            indication_terms=["Cancer"],
            trial_phase="PHASE3"
        )
        
        if len(long_result['query_string']) <= builder.max_query_length:
            logger.info("✅ Safe query trimming working correctly")
        else:
            logger.error(f"❌ Safe query trimming not working: query length {len(long_result['query_string'])}")
            return False
        
        logger.info("🎉 All TrialQueryBuilder fixes working correctly!")
        return True
        
    except Exception as e:
        logger.error(f"❌ TrialQueryBuilder test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mapper_fixes():
    """Test the fixes in PubMedMapper."""
    logger.info("\n🔍 Testing PubMedMapper fixes...")
    
    try:
        mapper = PubMedMapper()
        
        # Test 1: ESummary mapping (no abstracts)
        logger.info("Testing ESummary mapping fix...")
        esummary_data = {
            "12345": {
                "title": "Test Article",
                "abstract": "",  # ESummary doesn't have abstracts
                "fulljournalname": "Test Journal",
                "pubdate": "2023 Dec 15",
                "articleids": [
                    {"idtype": "doi", "value": "10.1234/test.2023.001"},
                    {"idtype": "pmid", "value": "12345"}
                ],
                "authors": [{"name": "Test Author"}],
                "lang": ["en"]
            }
        }
        
        mapped_docs = mapper.map_esummary_result(esummary_data)
        
        if mapped_docs and len(mapped_docs) == 1:
            doc = mapped_docs[0]
            
            # Check that abstract is empty (will be populated by EFetch)
            abstract = doc.get('text', {}).get('abstract_text', '')
            if abstract == "":
                logger.info("✅ ESummary abstract fix working correctly")
            else:
                logger.error(f"❌ ESummary abstract fix not working: got '{abstract}'")
                return False
            
            # Check that DOI is extracted from articleids
            doi = doc.get('doi', '')
            if doi == "10.1234/test.2023.001":
                logger.info("✅ DOI extraction fix working correctly")
            else:
                logger.error(f"❌ DOI extraction fix not working: got '{doi}'")
                return False
            
            # Check that MeSH/substances are empty (come from EFetch)
            mesh = doc.get('citation', {}).get('mesh_jsonb', [])
            substances = doc.get('citation', {}).get('substances_jsonb', [])
            if mesh == [] and substances == []:
                logger.info("✅ MeSH/substances fix working correctly")
            else:
                logger.error("❌ MeSH/substances fix not working")
                return False
        else:
            logger.error("❌ ESummary mapping failed")
            return False
        
        # Test 2: Date parsing fix
        logger.info("Testing date parsing fix...")
        test_dates = [
            ("2023 Dec 15", 2023, 12, 15),  # Full date
            ("2023 Dec", 2023, 12, 1),      # Month only
            ("2023", 2023, 1, 1),           # Year only
            ("Dec 2023", 2023, 12, 1),      # Month first
        ]
        
        for date_str, expected_year, expected_month, expected_day in test_dates:
            parsed_date = mapper._parse_pub_date(date_str)
            if parsed_date:
                if (parsed_date.year == expected_year and 
                    parsed_date.month == expected_month and 
                    parsed_date.day == expected_day):
                    logger.info(f"✅ Date parsing working for '{date_str}'")
                else:
                    logger.error(f"❌ Date parsing failed for '{date_str}': got {parsed_date}")
                    return False
            else:
                logger.error(f"❌ Date parsing returned None for '{date_str}'")
                return False
        
        # Test 3: EFetch abstracts mapping
        logger.info("Testing EFetch abstracts mapping fix...")
        existing_docs = [{"pmid": "12345", "text": {"abstract_text": ""}}]
        efetch_data = {"12345": "This is the abstract text from EFetch."}
        
        updated_docs = mapper.map_efetch_abstracts(efetch_data, existing_docs)
        
        if updated_docs and len(updated_docs) == 1:
            updated_doc = updated_docs[0]
            abstract = updated_doc.get('text', {}).get('abstract_text', '')
            content_type = updated_doc.get('content_type', '')
            
            if abstract == "This is the abstract text from EFetch." and content_type == "abstract":
                logger.info("✅ EFetch abstracts mapping fix working correctly")
            else:
                logger.error(f"❌ EFetch abstracts mapping fix not working: abstract='{abstract}', content_type='{content_type}'")
                return False
        else:
            logger.error("❌ EFetch abstracts mapping failed")
            return False
        
        # Test 4: PMC fulltext mapping
        logger.info("Testing PMC fulltext mapping fix...")
        existing_docs_with_pmcid = [{"pmcid": "PMC12345", "text": {"fulltext_text": None}}]
        pmc_data = {"PMC12345": "This is the full text content from PMC."}
        
        updated_pmc_docs = mapper.map_pmc_fulltext(pmc_data, existing_docs_with_pmcid)
        
        if updated_pmc_docs and len(updated_pmc_docs) == 1:
            updated_pmc_doc = updated_pmc_docs[0]
            fulltext = updated_pmc_doc.get('text', {}).get('fulltext_text', '')
            content_type = updated_pmc_doc.get('content_type', '')
            ttl_date = updated_pmc_doc.get('text', {}).get('fulltext_ttl_date', '')
            
            if (fulltext == "This is the full text content from PMC." and 
                content_type == "fulltext" and 
                ttl_date):
                logger.info("✅ PMC fulltext mapping fix working correctly")
            else:
                logger.error(f"❌ PMC fulltext mapping fix not working: fulltext='{fulltext}', content_type='{content_type}'")
                return False
        else:
            logger.error("❌ PMC fulltext mapping failed")
            return False
        
        # Test 5: PMCID validation
        logger.info("Testing PMCID validation fix...")
        elink_data = {"12345": "PMC12345", "67890": "INVALID123"}
        existing_docs_for_elink = [
            {"pmid": "12345", "pmcid": None},
            {"pmid": "67890", "pmcid": None}
        ]
        
        updated_elink_docs = mapper.map_elink_result(elink_data, existing_docs_for_elink)
        
        if updated_elink_docs and len(updated_elink_docs) == 2:
            # Check that valid PMCID gets PMC metadata
            valid_doc = next(doc for doc in updated_elink_docs if doc['pmid'] == '12345')
            invalid_doc = next(doc for doc in updated_elink_docs if doc['pmid'] == '67890')
            
            if 'pmc_meta' in valid_doc and 'pmc_meta' not in invalid_doc:
                logger.info("✅ PMCID validation fix working correctly")
            else:
                logger.error("❌ PMCID validation fix not working")
                return False
        else:
            logger.error("❌ ELink mapping failed")
            return False
        
        logger.info("🎉 All PubMedMapper fixes working correctly!")
        return True
        
    except Exception as e:
        logger.error(f"❌ PubMedMapper test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    logger.info("🚀 Testing Fixes for TrialQueryBuilder and PubMedMapper")
    logger.info("=" * 60)
    
    # Test TrialQueryBuilder fixes
    trial_builder_success = test_trial_query_builder_fixes()
    
    # Test PubMedMapper fixes
    mapper_success = test_mapper_fixes()
    
    # Summary
    logger.info("\n" + "=" * 60)
    if trial_builder_success and mapper_success:
        logger.info("🎉 ALL FIXES WORKING CORRECTLY!")
        logger.info("✅ List truncation fix")
        logger.info("✅ Publication type tag fix")
        logger.info("✅ Field tags fix")
        logger.info("✅ NCT boost fix")
        logger.info("✅ Safe query trimming")
        logger.info("✅ ESummary abstract fix")
        logger.info("✅ DOI extraction fix")
        logger.info("✅ MeSH/substances fix")
        logger.info("✅ Date parsing fix")
        logger.info("✅ EFetch abstracts mapping fix")
        logger.info("✅ PMC fulltext mapping fix")
        logger.info("✅ PMCID validation fix")
    else:
        logger.error("❌ Some fixes are not working. Check the logs above.")
    
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
