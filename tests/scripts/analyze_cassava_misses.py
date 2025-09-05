#!/usr/bin/env python3
"""
Analyze Cassava trial misses.
"""

import json
import sys
from pathlib import Path

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.config import get_config


async def analyze_cassava_misses():
    """Analyze what studies might have been missed."""
    
    print("🔍 Analyzing Cassava Trial Literature Coverage")
    print("=" * 60)
    
    # Initialize components
    client = PubMedClient(
        rate_limit_per_sec=5,
        batch_size=100,
        max_retries=3,
        timeout_seconds=30
    )
    
    mapper = PubMedMapper()
    query_builder = PubMedQueryBuilder()
    
    # Known Cassava/Simufilam studies that should be found
    known_studies = [
        "NCT04388254",  # The main Cassava trial
        "NCT04994483",  # Simufilam Phase 2b
        "NCT05026177",  # Simufilam Phase 3
        "35542991",     # PMID from our results
        "39800452",     # PMID from our results
        "37874099",     # PMID from our results
        "40545559",     # PMID from our results
        "32920628",     # PMID from our results
        "39495531",     # PMID from our results
        "40621876"      # PMID from our results
    ]
    
    async with client:
        print("📊 Testing Different Search Strategies")
        print("-" * 60)
        
        # Strategy 1: Broad search for Simufilam
        print("1. Broad Simufilam Search:")
        broad_query = "simufilam"
        broad_result = await client.esearch(broad_query, max_results=50)
        broad_pmids = broad_result.get('idlist', [])
        print(f"   Found {len(broad_pmids)} PMIDs")
        
        # Strategy 2: PTI-125 search
        print("2. PTI-125 Search:")
        pti_query = "PTI-125"
        pti_result = await client.esearch(pti_query, max_results=50)
        pti_pmids = pti_result.get('idlist', [])
        print(f"   Found {len(pti_pmids)} PMIDs")
        
        # Strategy 3: Cassava Sciences search
        print("3. Cassava Sciences Search:")
        cassava_query = '"Cassava Sciences"'
        cassava_result = await client.esearch(cassava_query, max_results=50)
        cassava_pmids = cassava_result.get('idlist', [])
        print(f"   Found {len(cassava_pmids)} PMIDs")
        
        # Strategy 4: Filamin A inhibitor search
        print("4. Filamin A Inhibitor Search:")
        filamin_query = '"filamin A inhibitor"'
        filamin_result = await client.esearch(filamin_query, max_results=50)
        filamin_pmids = filamin_result.get('idlist', [])
        print(f"   Found {len(filamin_pmids)} PMIDs")
        
        # Strategy 5: Alzheimer's + Simufilam
        print("5. Alzheimer's + Simufilam Search:")
        alz_sim_query = 'simufilam AND "Alzheimer disease"'
        alz_sim_result = await client.esearch(alz_sim_query, max_results=50)
        alz_sim_pmids = alz_sim_result.get('idlist', [])
        print(f"   Found {len(alz_sim_pmids)} PMIDs")
        
        print()
        
        # Combine all results
        all_pmids = set()
        all_pmids.update(broad_pmids)
        all_pmids.update(pti_pmids)
        all_pmids.update(cassava_pmids)
        all_pmids.update(filamin_pmids)
        all_pmids.update(alz_sim_pmids)
        
        print(f"📈 Total Unique PMIDs Found: {len(all_pmids)}")
        print()
        
        # Check against known studies
        print("🎯 Checking Against Known Studies:")
        print("-" * 60)
        
        found_known = 0
        missed_known = []
        
        for study in known_studies:
            if study in all_pmids:
                found_known += 1
                print(f"✅ Found: {study}")
            else:
                missed_known.append(study)
                print(f"❌ Missed: {study}")
        
        print()
        print(f"📊 Coverage: {found_known}/{len(known_studies)} known studies found")
        print()
        
        # Analyze the papers we found
        if all_pmids:
            print("📋 Analyzing Found Papers:")
            print("-" * 60)
            
            # Get metadata for all papers
            summary_result = await client.esummary_batch(list(all_pmids))
            mapped_docs = mapper.map_esummary_result(summary_result)
            
            # Categorize papers
            simufilam_papers = []
            cassava_papers = []
            filamin_papers = []
            alzheimer_papers = []
            
            for doc in mapped_docs:
                title = doc.get('title', '').lower()
                abstract = doc.get('abstract', '').lower()
                
                if 'simufilam' in title or 'pti-125' in title:
                    simufilam_papers.append(doc)
                if 'cassava' in title:
                    cassava_papers.append(doc)
                if 'filamin' in title:
                    filamin_papers.append(doc)
                if 'alzheimer' in title:
                    alzheimer_papers.append(doc)
            
            print(f"Papers mentioning Simufilam/PTI-125: {len(simufilam_papers)}")
            print(f"Papers mentioning Cassava: {len(cassava_papers)}")
            print(f"Papers mentioning Filamin: {len(filamin_papers)}")
            print(f"Papers mentioning Alzheimer: {len(alzheimer_papers)}")
            print()
            
            # Show key papers
            print("🔑 Key Papers Found:")
            print("-" * 60)
            
            for i, doc in enumerate(simufilam_papers[:5], 1):
                pmid = doc.get('pmid', 'Unknown')
                title = doc.get('title', 'No title')
                authors = doc.get('authors', 'Unknown')
                year = doc.get('published_at', 'Unknown')
                
                print(f"{i}. PMID: {pmid}")
                print(f"   Title: {title}")
                print(f"   Authors: {authors}")
                print(f"   Year: {year}")
                print()
        
        # Identify potential misses
        print("🚨 Potential Misses:")
        print("-" * 60)
        
        if missed_known:
            print("Known studies that were missed:")
            for study in missed_known:
                print(f"  - {study}")
        else:
            print("✅ All known studies were found!")
        
        # Suggest improvements
        print()
        print("💡 Suggested Improvements:")
        print("-" * 60)
        
        if len(all_pmids) < 10:
            print("1. Expand search terms to include:")
            print("   - 'PTI-125' (drug code)")
            print("   - 'filamin A' (mechanism)")
            print("   - 'Cassava Sciences Inc' (company)")
            print("   - 'Alzheimer' (disease)")
        
        if len(simufilam_papers) < 3:
            print("2. Add alternative spellings:")
            print("   - 'Simufilam' vs 'simufilam'")
            print("   - 'PTI-125' vs 'PTI125'")
        
        print("3. Consider broader date ranges")
        print("4. Include non-clinical trial publications")
        print("5. Search for related compounds")


if __name__ == "__main__":
    asyncio.run(analyze_cassava_misses())
