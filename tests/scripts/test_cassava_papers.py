#!/usr/bin/env python3
"""
Test Cassava papers processing.
"""

import json
import sys
from pathlib import Path

from ncfd.ingest.pubmed.pipeline import PubMedPipeline
from ncfd.ingest.pubmed.query_builder import PubMedQueryBuilder
from ncfd.ingest.pubmed.client import PubMedClient
from ncfd.ingest.pubmed.mapper import PubMedMapper
import asyncio


async def test_cassava_papers():
    """Test what papers were found for the Cassava trial."""
    
    # Cassava trial configuration
    config = {
        "asset_names": [
            "simufilam",
            "PTI-125", 
            "filamin A inhibitor",
            "Cassava Sciences"
        ],
        "indications": [
            "Alzheimer's disease",
            "AD",
            "dementia", 
            "cognitive decline"
        ],
        "max_results": 1000,
        "enable_stages": ['U0'],
        "client_config": {
            "rate_limit_requests_per_minute": 300,
            "timeout_seconds": 30,
            "max_retries": 3
        },
        "query_config": {
            "max_terms": 50,
            "enable_boolean_operators": True
        },
        "mapper_config": {
            "enable_entity_extraction": True,
            "enable_citation_parsing": True
        },
        "max_concurrent_requests": 3,
        "batch_size": 50
    }
    
    print("🔬 Testing PubMed Pipeline for Cassava Trial (NCT04388254)")
    print("=" * 60)
    
    # Initialize components
    client_config = config.get('client_config', {})
    client = PubMedClient(
        api_key=client_config.get('api_key'),
        rate_limit_per_sec=client_config.get('rate_limit_requests_per_minute', 8) // 60,
        batch_size=client_config.get('batch_size', 100),
        max_retries=client_config.get('max_retries', 3),
        timeout_seconds=client_config.get('timeout_seconds', 30),
        circuit_breaker_threshold=client_config.get('circuit_breaker_threshold', 5),
        email=client_config.get('email', 'ncfd@example.com'),
        tool=client_config.get('tool', 'NCFD')
    )
    
    mapper = PubMedMapper(config.get('mapper_config', {}))
    query_builder = PubMedQueryBuilder(config.get('query_config', {}))
    
    async with client:
        # Build query
        query_string = query_builder.build_trial_query(
            asset_names=config["asset_names"],
            indications=config["indications"],
            trial_phases=["phase_2"],
            date_range=("2020/01/01", "2024/12/31")
        )
        
        print(f"🔍 Search Query: {query_string[:200]}...")
        print()
        
        # Execute search
        print("📊 Executing PubMed search...")
        search_result = await client.esearch(query_string, max_results=config["max_results"])
        
        pmids = search_result.get('idlist', [])
        print(f"✅ Found {len(pmids)} PMIDs")
        print()
        
        if pmids:
            # Fetch metadata
            print("📋 Fetching document metadata...")
            summary_result = await client.esummary_batch(pmids)
            
            # Map results
            mapped_docs = mapper.map_esummary_result(summary_result)
            print(f"✅ Mapped {len(mapped_docs)} documents")
            print()
            
            # Display results
            print("📚 Papers Found:")
            print("-" * 60)
            
            for i, doc in enumerate(mapped_docs[:10], 1):  # Show first 10
                pmid = doc.get('pmid', 'Unknown')
                title = doc.get('title', 'No title')
                authors = doc.get('authors', 'Unknown')
                journal = doc.get('publisher', 'Unknown')
                year = doc.get('published_at', 'Unknown')
                
                print(f"{i}. PMID: {pmid}")
                print(f"   Title: {title}")
                print(f"   Authors: {authors}")
                print(f"   Journal: {journal}")
                print(f"   Year: {year}")
                print()
            
            if len(mapped_docs) > 10:
                print(f"... and {len(mapped_docs) - 10} more papers")
                print()
            
            # Analyze relevance
            print("🎯 Relevance Analysis:")
            print("-" * 60)
            
            cassava_related = 0
            simufilam_related = 0
            filamin_related = 0
            
            for doc in mapped_docs:
                title = doc.get('title', '').lower()
                if 'cassava' in title:
                    cassava_related += 1
                if 'simufilam' in title or 'pti-125' in title:
                    simufilam_related += 1
                if 'filamin' in title:
                    filamin_related += 1
            
            print(f"Papers mentioning 'Cassava': {cassava_related}")
            print(f"Papers mentioning 'Simufilam/PTI-125': {simufilam_related}")
            print(f"Papers mentioning 'Filamin': {filamin_related}")
            print(f"Total papers: {len(mapped_docs)}")
            print()
            
            # Overall assessment
            print("📈 Overall Assessment:")
            print("-" * 60)
            
            if simufilam_related > 0:
                print("✅ Found papers directly related to Simufilam/PTI-125")
            else:
                print("❌ No papers found directly mentioning Simufilam/PTI-125")
            
            if cassava_related > 0:
                print("✅ Found papers mentioning Cassava Sciences")
            else:
                print("❌ No papers found mentioning Cassava Sciences")
            
            if filamin_related > 0:
                print("✅ Found papers related to filamin A inhibition")
            else:
                print("❌ No papers found related to filamin A inhibition")
            
            print()
            print(f"🎯 Pipeline Performance: {len(mapped_docs)} relevant papers found")
            
            if len(mapped_docs) >= 5:
                print("✅ Good coverage - found multiple relevant papers")
            elif len(mapped_docs) >= 2:
                print("⚠️  Moderate coverage - found some relevant papers")
            else:
                print("❌ Poor coverage - found few relevant papers")


if __name__ == "__main__":
    asyncio.run(test_cassava_papers())
