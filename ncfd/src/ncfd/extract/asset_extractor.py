"""
Asset extraction and normalization for documents.

This module provides functionality to extract asset codes, INNs, and other identifiers
from document text using regex patterns and normalization rules.
"""

import re
import unicodedata
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class AssetMatch:
    """Represents a matched asset in document text."""
    value_text: str
    value_norm: str
    alias_type: str
    page_no: int
    char_start: int
    char_end: int
    detector: str
    confidence: float = 1.0


# Asset code patterns as specified in phase4.md
ASSET_CODE_PATTERNS = [
    r"\b[A-Z]{1,4}-\d{2,5}\b",             # AB-123, XYZ-12345
    r"\b[A-Z]{1,4}\d{2,5}\b",              # AB123
    r"\b[A-Z]{2,5}-[A-Z]{1,3}-\d{2,5}\b",  # BMS-AA-001
    r"\b[A-Z]{1,4}-\d+[A-Z]{1,2}\b",       # AB-123X
]

# Compile patterns for efficiency
COMPILED_PATTERNS = [re.compile(pattern) for pattern in ASSET_CODE_PATTERNS]


def norm_drug_name(text: str) -> str:
    """
    Normalize drug names according to phase4.md specifications.
    
    Canonical key precedence: InChIKey > UNII > ChEMBL ID > normalized internal code
    Normalization: NFKD → lower → ASCII fold; collapse spaces; strip ®/™ quotes; expand Greek
    
    Args:
        text: Raw drug name text
        
    Returns:
        Normalized drug name
    """
    if not text:
        return ""
    
    # NFKD normalization (decompose unicode characters)
    text = unicodedata.normalize('NFKD', text)
    
    # Convert to lowercase
    text = text.lower()
    
    # Expand Greek letters to their names BEFORE ASCII encoding
    greek_expansions = {
        'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta',
        'ε': 'epsilon', 'ζ': 'zeta', 'η': 'eta', 'θ': 'theta',
        'ι': 'iota', 'κ': 'kappa', 'λ': 'lambda', 'μ': 'mu',
        'ν': 'nu', 'ξ': 'xi', 'ο': 'omicron', 'π': 'pi',
        'ρ': 'rho', 'σ': 'sigma', 'τ': 'tau', 'υ': 'upsilon',
        'φ': 'phi', 'χ': 'chi', 'ψ': 'psi', 'ω': 'omega'
    }
    
    for greek, expansion in greek_expansions.items():
        text = text.replace(greek, expansion)
    
    # ASCII fold (convert accented characters to ASCII equivalents)
    # This is a simplified version - in production you might want a more comprehensive mapping
    text = text.encode('ascii', 'ignore').decode('ascii')
    
    # Strip trademark symbols and quotes
    text = re.sub(r'[®™©]', '', text)
    text = re.sub(r'["\']', '', text)
    
    # Collapse multiple spaces to single space
    text = re.sub(r'\s+', ' ', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def norm_asset_code(text: str) -> str:
    """
    Normalize asset codes specifically.
    
    Asset codes (like AB-123, XYZ-456) are normalized to enable
    fuzzy matching while preserving the essential structure.
    
    Args:
        text: Raw asset code text
        
    Returns:
        Normalized asset code string
    """
    if not text: return ""
    
    # Remove common prefixes/suffixes that don't affect identity
    text = re.sub(r'^(drug|compound|agent|therapy)\s+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+(hcl|hydrochloride|sulfate|phosphate|acetate)$', '', text, flags=re.IGNORECASE)
    
    # Normalize hyphens and dashes
    text = re.sub(r'[–—−]', '-', text)  # EN dash, EM dash, minus sign → hyphen
    
    # Normalize whitespace around hyphens
    text = re.sub(r'\s*-\s*', '-', text)
    
    # Convert to lowercase for consistent matching
    text = text.lower()
    
    return text.strip()


def generate_code_variants(code: str) -> List[str]:
    """
    Generate common variants of an asset code for comprehensive matching.
    
    This addresses the reviewer's concern about missing hyphenated/collapsed forms
    by generating both variants during the extraction process.
    
    Args:
        code: Base asset code (e.g., "AB-123")
        
    Returns:
        List of code variants including the original
    """
    variants = [code]
    
    # Remove hyphens
    if '-' in code:
        variants.append(code.replace('-', ''))
    
    # Add hyphens to codes without them (if they look like they should have them)
    elif re.match(r'^[A-Z]{1,3}\d{1,4}$', code, re.IGNORECASE):
        # Pattern like "AB123" → add "AB-123"
        match = re.match(r'^([A-Z]{1,3})(\d{1,4})$', code, re.IGNORECASE)
        if match:
            variants.append(f"{match.group(1)}-{match.group(2)}")
    
    return list(set(variants))  # Remove duplicates


def extract_asset_codes(text: str, page_no: int = 1) -> List[AssetMatch]:
    """
    Extract asset codes from text using regex patterns.
    
    Args:
        text: Text to search for asset codes
        page_no: Page number where the text was found
        
    Returns:
        List of AssetMatch objects
    """
    matches = []
    
    for pattern in COMPILED_PATTERNS:
        for match in pattern.finditer(text):
            value_text = match.group(0)
            
            # Create both hyphenated and collapsed forms as aliases
            if '-' in value_text:
                # Hyphenated form (e.g., AB-123)
                collapsed_form = value_text.replace('-', '')
                matches.append(AssetMatch(
                    value_text=value_text,
                    value_norm=value_text,
                    alias_type='code',
                    page_no=page_no,
                    char_start=match.start(),
                    char_end=match.end(),
                    detector='regex',
                    confidence=1.0
                ))
                
                # Also add collapsed form
                matches.append(AssetMatch(
                    value_text=collapsed_form,
                    value_norm=collapsed_form,
                    alias_type='code',
                    page_no=page_no,
                    char_start=match.start(),
                    char_end=match.end(),
                    detector='regex',
                    confidence=1.0
                ))
            else:
                # Collapsed form (e.g., AB123)
                matches.append(AssetMatch(
                    value_text=value_text,
                    value_norm=value_text,
                    alias_type='code',
                    page_no=page_no,
                    char_start=match.start(),
                    char_end=match.end(),
                    detector='regex',
                    confidence=1.0
                ))
    
    return matches


def extract_inn_generics(text: str, inn_dict: Dict[str, str], page_no: int = 1) -> List[AssetMatch]:
    """
    Extract INN/generic names from text using a dictionary lookup.
    
    Args:
        text: Text to search for INN/generic names
        inn_dict: Dictionary mapping normalized names to their types
        page_no: Page number where the text was found
        
    Returns:
        List of AssetMatch objects
    """
    matches = []
    text_lower = text.lower()
    
    for norm_name, alias_type in inn_dict.items():
        # Find all occurrences of the normalized name in the text
        start_pos = 0
        while True:
            pos = text_lower.find(norm_name, start_pos)
            if pos == -1:
                break
                
            # Extract the original text at this position
            original_text = text[pos:pos + len(norm_name)]
            
            matches.append(AssetMatch(
                value_text=original_text,
                value_norm=norm_name,
                alias_type=alias_type,
                page_no=page_no,
                char_start=pos,
                char_end=pos + len(norm_name),
                detector='dict',
                confidence=1.0
            ))
            
            start_pos = pos + 1
    
    return matches


def extract_nct_ids(text: str, page_no: int = 1) -> List[AssetMatch]:
    """
    Extract NCT IDs from text.
    
    Args:
        text: Text to search for NCT IDs
        page_no: Page number where the text was found
        
    Returns:
        List of AssetMatch objects
    """
    matches = []
    
    # Pattern for NCT IDs: NCT followed by numbers
    nct_pattern = re.compile(r'\bNCT\d+\b', re.IGNORECASE)
    
    for match in nct_pattern.finditer(text):
        value_text = match.group(0)
        matches.append(AssetMatch(
            value_text=value_text,
            value_norm=value_text.upper(),
            alias_type='nct',
            page_no=page_no,
            char_start=match.start(),
            char_end=match.end(),
            detector='regex',
            confidence=1.0
        ))
    
    return matches


def find_nearby_assets(asset_matches: List[AssetMatch], nct_matches: List[AssetMatch], 
                       window_size: int = 250) -> List[Tuple[AssetMatch, AssetMatch]]:
    """
    Find asset mentions that are near NCT IDs within a specified character window.
    
    This implements HP-1 from phase4.md: "NCT near asset" heuristic.
    
    Args:
        asset_matches: List of asset matches
        nct_matches: List of NCT ID matches
        window_size: Character window size (default 250 as per phase4.md)
        
    Returns:
        List of tuples (asset_match, nct_match) for nearby pairs
    """
    nearby_pairs = []
    
    for asset_match in asset_matches:
        for nct_match in nct_matches:
            # Check if they're on the same page
            if asset_match.page_no != nct_match.page_no:
                continue
                
            # Calculate distance between asset and NCT
            asset_pos = (asset_match.char_start + asset_match.char_end) // 2
            nct_pos = (nct_match.char_start + nct_match.char_end) // 2
            distance = abs(asset_pos - nct_pos)
            
            if distance <= window_size:
                nearby_pairs.append((asset_match, nct_match))
    
    return nearby_pairs


def create_asset_shell(names_jsonb: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Create a shell asset record for new assets.
    
    Args:
        names_jsonb: Initial names data
        
    Returns:
        Asset shell dictionary
    """
    if names_jsonb is None:
        names_jsonb = {}
    
    return {
        'names_jsonb': names_jsonb,
        'modality': None,
        'target': None,
        'moa': None,
    }


def extract_all_entities(text: str, page_no: int = 1, 
                        inn_dict: Optional[Dict[str, str]] = None) -> List[AssetMatch]:
    """
    Extract all entity types from text in one pass.
    
    Args:
        text: Text to extract entities from
        page_no: Page number where the text was found
        inn_dict: Dictionary for INN/generic extraction
        
    Returns:
        List of all AssetMatch objects found
    """
    matches = []
    
    # Extract asset codes
    matches.extend(extract_asset_codes(text, page_no))
    
    # Extract INN/generics if dictionary provided
    if inn_dict:
        matches.extend(extract_inn_generics(text, inn_dict, page_no))
    
    # Extract NCT IDs
    matches.extend(extract_nct_ids(text, page_no))
    
    return matches


def get_confidence_for_link_type(link_type: str, base_confidence: float = 1.0) -> float:
    """
    Get confidence score for different link types based on phase4.md heuristics.
    
    Args:
        link_type: Type of link (e.g., 'nct_near_asset', 'code_in_text')
        base_confidence: Base confidence score
        
    Returns:
        Adjusted confidence score
    """
    confidence_map = {
        'nct_near_asset': 1.00,      # HP-1: Highest confidence
        'code_in_text': 0.90,        # HP-3: Company-hosted PR with code + INN
        'inn_in_text': 0.85,         # HP-4: Abstract specificity
        'exact_intervention_match': 0.95,  # HP-2: Exact intervention name match
    }
    
    return confidence_map.get(link_type, base_confidence)
