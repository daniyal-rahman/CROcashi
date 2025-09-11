#!/usr/bin/env python3
"""
Search for the 6 notable Cassava papers by their PMCID values.
"""

import requests
import json
from typing import Dict, List, Any

# Notable papers with their PMCID values
NOTABLE_PAPERS = [
    {
        "title": "Simufilam Reverses Aberrant Receptor Interactions of Filamin A in Alzheimer's Disease",
        "pmcid": "PMC10531384",
        "year": 2023
    },
    {
        "title": "Simufilam suppresses overactive mTOR and restores its ...",
        "pmcid": "PMC10339288", 
        "year": 2023
    },
    {
        "title": "Reducing amyloid-related Alzheimer's disease pathogenesis by a small molecule targeting filamin A",
        "pmcid": "PMC6621293",
        "year": 2012
    },
    {
        "title": "PTI-125 binds and reverses an altered conformation of filamin A to reduce Alzheimer's disease pathogenesis",
        "pmcid": "No PMCID",
        "year": 2017
    },
    {
        "title": "PTI-125 Reduces Biomarkers of Alzheimer's Disease in Patients",
        "pmcid": "No PMCID",
        "year": 2020
    },
    {
        "title": "Effects of simufilam on cerebrospinal fluid biomarkers in …",
        "pmcid": "No PMCID",
        "year": 2021
    }
]

def search_pubmed_by_pmcid(pmcid: str) -> Dict[str, Any]:
    """Search PubMed for a specific PMCID."""
    if pmcid == "No PMCID":
        return {"found": False, "reason": "No PMCID provided"}
    
    # Search using ESearch with PMCID
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": f"{pmcid}[pmcid]",
        "retmode": "json",
        "retmax": 1
    }
    
    try:
        response = requests.get(esearch_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        pmids = data.get("esearchresult", {}).get("idlist", [])
        
        if not pmids:
            return {"found": False, "reason": "No PMID found for PMCID"}
        
        # Get details using ESummary
        pmid = pmids[0]
        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        esummary_params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "json"
        }
        
        esummary_response = requests.get(esummary_url, params=esummary_params, timeout=30)
        esummary_response.raise_for_status()
        esummary_data = esummary_response.json()
        
        result = esummary_data.get("result", {}).get(pmid, {})
        
        return {
            "found": True,
            "pmid": pmid,
            "pmcid": pmcid,
            "title": result.get("title", "Unknown"),
            "authors": result.get("authors", []),
            "pubdate": result.get("pubdate", "Unknown"),
            "source": result.get("source", "Unknown"),
            "doi": result.get("elocationid", "Unknown")
        }
        
    except Exception as e:
        return {"found": False, "reason": f"Error: {str(e)}"}


def search_pubmed_by_title_keywords(title: str, year: int) -> Dict[str, Any]:
    """Search PubMed using title keywords and year."""
    # Extract key terms from title
    keywords = []
    if "simufilam" in title.lower():
        keywords.append("simufilam")
    if "pti-125" in title.lower() or "pti 125" in title.lower():
        keywords.append("PTI-125")
    if "filamin" in title.lower():
        keywords.append("filamin")
    if "alzheimer" in title.lower():
        keywords.append("Alzheimer")
    if "biomarkers" in title.lower():
        keywords.append("biomarkers")
    if "mtor" in title.lower():
        keywords.append("mTOR")
    
    if not keywords:
        return {"found": False, "reason": "No searchable keywords found"}
    
    # Build search query
    query = " AND ".join([f'"{kw}"[tiab]' for kw in keywords])
    query += f" AND {year}[dp]"
    
    # Search using ESearch
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": 10
    }
    
    try:
        response = requests.get(esearch_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        pmids = data.get("esearchresult", {}).get("idlist", [])
        
        if not pmids:
            return {"found": False, "reason": "No results found"}
        
        # Get details for the first result
        pmid = pmids[0]
        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        esummary_params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "json"
        }
        
        esummary_response = requests.get(esummary_url, params=esummary_params, timeout=30)
        esummary_response.raise_for_status()
        esummary_data = esummary_response.json()
        
        result = esummary_data.get("result", {}).get(pmid, {})
        
        return {
            "found": True,
            "pmid": pmid,
            "title": result.get("title", "Unknown"),
            "authors": result.get("authors", []),
            "pubdate": result.get("pubdate", "Unknown"),
            "source": result.get("source", "Unknown"),
            "doi": result.get("elocationid", "Unknown"),
            "search_method": "title_keywords"
        }
        
    except Exception as e:
        return {"found": False, "reason": f"Error: {str(e)}"}


def main():
    """Search for all 6 notable papers."""
    print("🔍 Searching for 6 Notable Cassava Papers")
    print("=" * 60)
    
    results = []
    
    for i, paper in enumerate(NOTABLE_PAPERS, 1):
        print(f"\n{i}. {paper['title']} ({paper['year']})")
        print(f"   PMCID: {paper['pmcid']}")
        
        # Try PMCID search first if available
        if paper['pmcid'] != "No PMCID":
            result = search_pubmed_by_pmcid(paper['pmcid'])
            if result['found']:
                print(f"   ✅ FOUND via PMCID: PMID {result['pmid']}")
                print(f"   📄 Title: {result['title']}")
                print(f"   📅 Date: {result['pubdate']}")
                print(f"   📖 Source: {result['source']}")
                results.append({
                    "paper": paper,
                    "result": result,
                    "method": "pmcid"
                })
                continue
        
        # Fall back to title/keyword search
        print(f"   🔍 Searching by title keywords...")
        result = search_pubmed_by_title_keywords(paper['title'], paper['year'])
        if result['found']:
            print(f"   ✅ FOUND via title search: PMID {result['pmid']}")
            print(f"   📄 Title: {result['title']}")
            print(f"   📅 Date: {result['pubdate']}")
            print(f"   📖 Source: {result['source']}")
            results.append({
                "paper": paper,
                "result": result,
                "method": "title_keywords"
            })
        else:
            print(f"   ❌ NOT FOUND: {result['reason']}")
            results.append({
                "paper": paper,
                "result": result,
                "method": "none"
            })
    
    # Summary
    print(f"\n📊 SUMMARY:")
    found_count = sum(1 for r in results if r['result']['found'])
    print(f"   • Papers found: {found_count}/6")
    print(f"   • Papers not found: {6 - found_count}/6")
    
    if found_count > 0:
        print(f"\n📋 FOUND PAPERS:")
        for i, result in enumerate(results, 1):
            if result['result']['found']:
                print(f"   {i}. PMID {result['result']['pmid']} - {result['result']['title'][:80]}...")
    
    # Save results
    with open('/Users/danirahman/Repos/CROcashi/tests/logs/notable_papers_search.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to: tests/logs/notable_papers_search.json")


if __name__ == "__main__":
    main()
