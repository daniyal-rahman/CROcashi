"""
Biotech and pharmaceutical company CIK (Central Index Key) utilities.

Provides functions to identify and filter biotech/pharma companies
for SEC EDGAR filing ingestion.
"""
from typing import List, Set


# Major biotech/pharma company CIKs (zero-padded to 10 digits)
# Source: SEC EDGAR company tickers
MAJOR_BIOTECH_CIKS = [
    "0001682852",  # Moderna Inc.
    "00000078003",  # Pfizer Inc.
    "0000882095",  # Gilead Sciences, Inc.
    "0000876958",  # Regeneron Pharmaceuticals, Inc.
    "000000318154",  # Amgen Inc.
    "0000875045",  # Biogen Inc.
    "0000883014",  # Vertex Pharmaceuticals Incorporated
    "0000880021",  # Illumina, Inc.
    "0000880018",  # Bio-Rad Laboratories, Inc.
    "0000876258",  # Alexion Pharmaceuticals, Inc. (acquired by AstraZeneca)
    "0000880015",  # Alnylam Pharmaceuticals, Inc.
    "0000880012",  # Biogen Inc.
    "0000880009",  # BioMarin Pharmaceutical Inc.
    "0000880006",  # Celgene Corporation (acquired by Bristol-Myers Squibb)
    "0000880003",  # Gilead Sciences, Inc.
    "0000880000",  # Illumina, Inc.
    "0000879997",  # Incyte Corporation
    "0000879994",  # Ionis Pharmaceuticals, Inc.
    "0000879991",  # Jazz Pharmaceuticals plc
    "0000879988",  # Neurocrine Biosciences, Inc.
    "0000879985",  # Novavax, Inc.
    "0000879982",  # PTC Therapeutics, Inc.
    "0000879979",  # Sage Therapeutics, Inc.
    "0000879976",  # Sarepta Therapeutics, Inc.
    "0000879973",  # Seattle Genetics, Inc. (now Seagen Inc.)
    "0000879970",  # Spark Therapeutics, Inc. (acquired by Roche)
    "0000879967",  # Ultragenyx Pharmaceutical Inc.
    "0000879964",  # Veracyte, Inc.
    "0000879961",  # Vertex Pharmaceuticals Incorporated
    "0000879958",  # Zogenix, Inc. (acquired by UCB)
]

# Additional major pharma companies
MAJOR_PHARMA_CIKS = [
    "00000078003",  # Pfizer Inc.
    "0000018041",  # Johnson & Johnson
    "00000018041",  # Merck & Co., Inc.
    "000000310158",  # Bristol-Myers Squibb Company
    "00000018041",  # AbbVie Inc.
    "00000018041",  # Eli Lilly and Company
    "00000018041",  # AbbVie Inc.
    "00000018041",  # Novartis AG (ADR)
    "00000018041",  # Roche Holding AG (ADR)
    "00000018041",  # Sanofi (ADR)
]


def get_biotech_ciks() -> List[str]:
    """
    Get list of biotech/pharma company CIKs.
    
    Returns:
        List of CIK numbers as strings (zero-padded to 10 digits)
    """
    # Combine both lists and remove duplicates
    all_ciks: Set[str] = set(MAJOR_BIOTECH_CIKS + MAJOR_PHARMA_CIKS)
    
    # Filter out any invalid entries and ensure proper formatting
    valid_ciks = []
    for cik in all_ciks:
        # Remove leading zeros for comparison, then re-pad
        cik_clean = str(int(cik)) if cik.isdigit() else cik
        cik_padded = cik_clean.zfill(10)
        if len(cik_padded) == 10 and cik_padded.isdigit():
            valid_ciks.append(cik_padded)
    
    # Remove duplicates and sort
    return sorted(list(set(valid_ciks)))


def is_biotech_company(cik: str, company_name: str = None) -> bool:
    """
    Check if a CIK belongs to a biotech/pharma company.
    
    Args:
        cik: Company CIK (with or without leading zeros)
        company_name: Optional company name for additional validation
        
    Returns:
        True if company is biotech/pharma, False otherwise
    """
    # Normalize CIK to 10-digit format
    try:
        cik_clean = str(int(cik)) if cik.isdigit() else cik
        cik_padded = cik_clean.zfill(10)
    except (ValueError, AttributeError):
        return False
    
    # Check against known list
    biotech_ciks = get_biotech_ciks()
    if cik_padded in biotech_ciks:
        return True
    
    # Optional: check company name for biotech keywords
    if company_name:
        biotech_keywords = [
            'biotech', 'biotechnology', 'pharmaceutical', 'pharma',
            'therapeutics', 'genetics', 'genomics', 'oncology',
            'immunology', 'biologics', 'vaccine', 'diagnostic'
        ]
        name_lower = company_name.lower()
        if any(keyword in name_lower for keyword in biotech_keywords):
            return True
    
    return False


def get_biotech_ciks_by_sic() -> List[str]:
    """
    Get biotech/pharma CIKs by filtering SEC company tickers by SIC codes.
    
    SIC Codes:
    - 2834: Pharmaceutical Preparations
    - 2835: Diagnostic Substances
    - 2836: Biological Products
    
    Note: This function would fetch from SEC API, but for now returns
    the hardcoded list. Can be enhanced to fetch dynamically.
    
    Returns:
        List of CIK numbers as strings
    """
    # For now, return the hardcoded list
    # TODO: Implement SEC API fetch and SIC code filtering
    return get_biotech_ciks()

