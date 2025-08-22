"""
Asset extraction and normalization for documents.

This module provides functionality to extract asset codes, INNs, and other identifiers
from document text using regex patterns and normalization rules.
"""

import re
import unicodedata
import hashlib
from datetime import datetime, timezone
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
    # Source versioning and deduplication fields
    source_version: str = "1.0"  # Version of extraction rules used
    extraction_timestamp: str = ""  # When this extraction was performed
    deduplication_key: str = ""  # Key for deduplication (hash of content + position)
    source_document_id: str = ""  # ID of source document
    source_page_hash: str = ""  # Hash of source page content for change detection


# Asset code patterns as specified in phase4.md
ASSET_CODE_PATTERNS = [
    r"\b[A-Z]{1,4}-\d{2,5}\b",             # AB-123, XYZ-12345
    r"\b[A-Z]{1,4}\d{2,5}\b",              # AB123
    r"\b[A-Z]{2,5}-[A-Z]{1,3}-\d{2,5}\b",  # BMS-AA-001
    r"\b[A-Z]{1,4}-\d+[A-Z]{1,2}\b",       # AB-123X
    r"\b[A-Z]{1,4}\d+[A-Z]{1,2}\b",        # AB123X (without hyphen)
]

# Compile patterns for efficiency
COMPILED_PATTERNS = [re.compile(pattern) for pattern in ASSET_CODE_PATTERNS]

# Current version of extraction rules
EXTRACTION_RULES_VERSION = "1.0.0"

def generate_deduplication_key(value_text: str, page_no: int, char_start: int, 
                              char_end: int, source_document_id: str = "") -> str:
    """
    Generate a deduplication key for an asset match.
    
    This key combines the normalized value, position, and source document
    to identify duplicate extractions across different runs.
    
    Args:
        value_text: The extracted text value
        page_no: Page number
        char_start: Character start position
        char_end: Character end position
        source_document_id: Source document identifier
        
    Returns:
        SHA256 hash string for deduplication
    """
    # Create a unique string combining all identifying information
    key_string = f"{value_text.lower()}:{page_no}:{char_start}:{char_end}:{source_document_id}"
    return hashlib.sha256(key_string.encode('utf-8')).hexdigest()

def generate_page_hash(page_content: str) -> str:
    """
    Generate a hash of page content for change detection.
    
    Args:
        page_content: Raw page text content
        
    Returns:
        SHA256 hash of the page content
    """
    return hashlib.sha256(page_content.encode('utf-8')).hexdigest()

def deduplicate_asset_matches(matches: List[AssetMatch], 
                             strategy: str = "strict") -> List[AssetMatch]:
    """
    Remove duplicate asset matches based on deduplication strategy.
    
    Args:
        matches: List of AssetMatch objects
        strategy: Deduplication strategy ("strict", "position_based", "content_based")
        
    Returns:
        Deduplicated list of AssetMatch objects
    """
    if not matches:
        return []
    
    if strategy == "strict":
        # Use deduplication keys (most strict)
        seen_keys = set()
        unique_matches = []
        
        for match in matches:
            if match.deduplication_key and match.deduplication_key not in seen_keys:
                seen_keys.add(match.deduplication_key)
                unique_matches.append(match)
        
        return unique_matches
        
    elif strategy == "position_based":
        # Group by position and keep highest confidence
        position_groups = {}
        
        for match in matches:
            pos_key = (match.page_no, match.char_start, match.char_end)
            if pos_key not in position_groups or match.confidence > position_groups[pos_key].confidence:
                position_groups[pos_key] = match
        
        return list(position_groups.values())
        
    elif strategy == "content_based":
        # Group by normalized value and keep highest confidence
        content_groups = {}
        
        for match in matches:
            norm_key = match.value_norm
            if norm_key not in content_groups or match.confidence > content_groups[norm_key].confidence:
                content_groups[norm_key] = match
        
        return list(content_groups.values())
    
    else:
        # Default to strict deduplication
        return deduplicate_asset_matches(matches, "strict")


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
    
    # Strip trademark symbols and quotes BEFORE NFKD normalization
    text = re.sub(r'[®™©]', '', text)   # Remove original trademark symbols
    text = re.sub(r'["\']', '', text)
    
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


def extract_asset_codes(text: str, page_no: int = 1, source_document_id: str = "", 
                        page_content: str = "") -> List[AssetMatch]:
    """
    Extract asset codes from text using regex patterns.
    
    Args:
        text: Text to search for asset codes
        page_no: Page number where the text was found
        source_document_id: Source document identifier for deduplication
        page_content: Raw page content for change detection
        
    Returns:
        List of AssetMatch objects with versioning and deduplication
    """
    matches = []
    current_timestamp = datetime.now(timezone.utc).isoformat()
    page_hash = generate_page_hash(page_content) if page_content else ""
    
    for pattern in COMPILED_PATTERNS:
        for match in pattern.finditer(text):
            value_text = match.group(0)
            char_start = match.start()
            char_end = match.end()
            
            # Create both hyphenated and collapsed forms as aliases
            if '-' in value_text:
                # Hyphenated form (e.g., AB-123)
                collapsed_form = value_text.replace('-', '')
                matches.append(AssetMatch(
                    value_text=value_text,
                    value_norm=value_text,
                    alias_type='code',
                    page_no=page_no,
                    char_start=char_start,
                    char_end=char_end,
                    detector='regex',
                    confidence=1.0,
                    source_version=EXTRACTION_RULES_VERSION,
                    extraction_timestamp=current_timestamp,
                    deduplication_key=generate_deduplication_key(
                        value_text, page_no, char_start, char_end, source_document_id
                    ),
                    source_document_id=source_document_id,
                    source_page_hash=page_hash
                ))
                
                # Also add collapsed form
                matches.append(AssetMatch(
                    value_text=collapsed_form,
                    value_norm=collapsed_form,
                    alias_type='code',
                    page_no=page_no,
                    char_start=char_start,
                    char_end=char_end,
                    detector='regex',
                    confidence=1.0,
                    source_version=EXTRACTION_RULES_VERSION,
                    extraction_timestamp=current_timestamp,
                    deduplication_key=generate_deduplication_key(
                        collapsed_form, page_no, char_start, char_end, source_document_id
                    ),
                    source_document_id=source_document_id,
                    source_page_hash=page_hash
                ))
            else:
                # Collapsed form (e.g., AB123)
                matches.append(AssetMatch(
                    value_text=value_text,
                    value_norm=value_text,
                    alias_type='code',
                    page_no=page_no,
                    char_start=char_start,
                    char_end=char_end,
                    detector='regex',
                    confidence=1.0,
                    source_version=EXTRACTION_RULES_VERSION,
                    extraction_timestamp=current_timestamp,
                    deduplication_key=generate_deduplication_key(
                        value_text, page_no, char_start, char_end, source_document_id
                    ),
                    source_document_id=source_document_id,
                    source_page_hash=page_hash
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
