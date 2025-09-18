"""
Asset and indication normalization utilities.

Provides functions for normalizing drug names, indications, and other clinical terms
for consistent matching and searching.
"""

import logging
import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple, Any
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class AssetIndicationNormalizer:
    """Normalizes asset names and indications for consistent matching."""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize normalizer.
        
        Args:
            config: Configuration dictionary with normalization parameters
        """
        self.config = config or {}
        self.similarity_threshold = self.config.get('similarity_threshold', 0.8)
        
        # Common drug name patterns
        self.drug_patterns = {
            'salt_forms': [
                r'\b(hydrochloride|hcl|sulfate|sulphate|citrate|phosphate|acetate|sodium|potassium)\b',
                r'\b(maleate|fumarate|tartrate|succinate|gluconate|lactate)\b'
            ],
            'stereochemistry': [
                r'\b((R|S|D|L)-|(R|S|D|L)\s*|(R|S|D|L)$)',
                r'\b(trans-|cis-|E-|Z-|endo-|exo-)'
            ],
            'formulations': [
                r'\b(tablet|capsule|injection|solution|suspension|cream|gel|ointment)\b',
                r'\b(oral|intravenous|intramuscular|subcutaneous|topical|inhalation)\b'
            ],
            'strengths': [
                r'\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|mM|nM|μM|pM)\b',
                r'\b(\d+(?:\.\d+)?)\s*percent|%'
            ],
            'pharmaceutical_suffixes': [
                r'\b(-mab|-nib|-zumab|-cept|-ximab|-zomab|-mab)\b',
                r'\b(-ol|-ole|-ine|-in|-ate|-ide|-ine|-in)\b'
            ],
            'chemical_prefixes': [
                r'\b(N-|O-|S-|C-|H-)\b'
            ]
        }
        
        # Common indication patterns
        self.indication_patterns = {
            'severity': [
                r'\b(mild|moderate|severe|advanced|early|late|acute|chronic)\b',
                r'\b(refractory|resistant|relapsed|recurrent|metastatic|locally advanced)\b'
            ],
            'staging': [
                r'\b(stage\s*[0-4]|grade\s*[1-5]|class\s*[A-C])\b',
                r'\b(T[0-4]|N[0-3]|M[0-1])\b'  # TNM staging
            ],
            'demographics': [
                r'\b(pediatric|pediatric|geriatric|elderly|adult|adolescent|child|infant)\b',
                r'\b(male|female|pregnant|postmenopausal|premenopausal)\b'
            ]
        }
    
    def normalize_asset_name(self, asset_name: str) -> Dict[str, str]:
        """
        Normalize an asset name for consistent matching.
        
        Args:
            asset_name: Raw asset name
            
        Returns:
            Dictionary with normalized versions
        """
        if not asset_name:
            return {}
        
        normalized = asset_name.strip()
        
        # 1. Basic normalization
        basic_norm = self._basic_normalization(normalized)
        
        # 2. ASCII folding
        ascii_norm = self._ascii_folding(normalized)
        
        # 3. Hyphen variants
        hyphen_variants = self._generate_hyphen_variants(normalized)
        
        # 4. Remove common drug patterns
        clean_norm = self._remove_drug_patterns(normalized)
        
        # 5. Generate phonetic representation
        phonetic_norm = self._phonetic_normalization(normalized)
        
        # 6. Generate fuzzy variants
        fuzzy_variants = self._generate_fuzzy_variants(normalized)
        
        return {
            'original': asset_name,
            'normalized': basic_norm,
            'ascii': ascii_norm,
            'clean': clean_norm,
            'phonetic': phonetic_norm,
            'hyphen_variants': hyphen_variants,
            'fuzzy_variants': fuzzy_variants
        }
    
    def normalize_indication(self, indication: str) -> Dict[str, str]:
        """
        Normalize an indication for consistent matching.
        
        Args:
            indication: Raw indication text
            
        Returns:
            Dictionary with normalized versions
        """
        if not indication:
            return {}
        
        normalized = indication.strip()
        
        # 1. Basic normalization
        basic_norm = self._basic_normalization(normalized)
        
        # 2. ASCII folding
        ascii_norm = self._ascii_folding(normalized)
        
        # 3. Remove common indication patterns
        clean_norm = self._remove_indication_patterns(normalized)
        
        # 4. Generate acronyms
        acronyms = self._generate_acronyms(normalized)
        
        # 5. Generate synonyms
        synonyms = self._generate_synonyms(normalized)
        
        return {
            'original': indication,
            'normalized': basic_norm,
            'ascii': ascii_norm,
            'clean': clean_norm,
            'acronyms': acronyms,
            'synonyms': synonyms
        }
    
    def _basic_normalization(self, text: str) -> str:
        """Apply basic text normalization."""
        # Convert to lowercase
        normalized = text.lower()
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Remove leading/trailing whitespace
        normalized = normalized.strip()
        
        # Remove punctuation (except hyphens and spaces)
        normalized = re.sub(r'[^\w\s\-]', '', normalized)
        
        return normalized
    
    def _ascii_folding(self, text: str) -> str:
        """Convert Unicode characters to ASCII equivalents."""
        # Normalize Unicode characters
        normalized = unicodedata.normalize('NFKD', text)
        
        # Convert to ASCII
        ascii_text = ''
        for char in normalized:
            if ord(char) < 128:
                ascii_text += char
            else:
                # Handle common Unicode mappings
                ascii_char = self._unicode_to_ascii_mapping(char)
                if ascii_char:
                    ascii_text += ascii_char
        
        return ascii_text
    
    def _unicode_to_ascii_mapping(self, char: str) -> Optional[str]:
        """Map Unicode characters to ASCII equivalents."""
        # Common pharmaceutical and medical Unicode mappings
        unicode_mappings = {
            'α': 'alpha',
            'β': 'beta',
            'γ': 'gamma',
            'δ': 'delta',
            'ε': 'epsilon',
            'ζ': 'zeta',
            'η': 'eta',
            'θ': 'theta',
            'ι': 'iota',
            'κ': 'kappa',
            'λ': 'lambda',
            'μ': 'mu',
            'ν': 'nu',
            'ξ': 'xi',
            'ο': 'omicron',
            'π': 'pi',
            'ρ': 'rho',
            'σ': 'sigma',
            'τ': 'tau',
            'υ': 'upsilon',
            'φ': 'phi',
            'χ': 'chi',
            'ψ': 'psi',
            'ω': 'omega',
            '°': ' degrees',
            '±': ' plus minus',
            '≤': ' less than or equal to ',
            '≥': ' greater than or equal to ',
            '×': ' x ',
            '÷': ' divided by ',
            '≈': ' approximately ',
            '≠': ' not equal to ',
            '∞': ' infinity ',
            '²': '2',
            '³': '3',
            '¹': '1',
            '₀': '0',
            '₁': '1',
            '₂': '2',
            '₃': '3',
            '₄': '4',
            '₅': '5',
            '₆': '6',
            '₇': '7',
            '₈': '8',
            '₉': '9',
            '′': "'",
            '″': '"',
            '‴': '"',
            '–': '-',
            '—': '-',
            '…': '...',
            '•': '*',
            '◦': 'o',
            '▪': '*',
            '▫': '*'
        }
        
        return unicode_mappings.get(char)
    
    def _generate_hyphen_variants(self, text: str) -> List[str]:
        """Generate variants with different hyphen placements."""
        variants = [text]
        
        # Add hyphenated version
        if ' ' in text:
            hyphenated = text.replace(' ', '-')
            variants.append(hyphenated)
        
        # Remove hyphens
        if '-' in text:
            no_hyphen = text.replace('-', ' ')
            variants.append(no_hyphen)
            no_hyphen_compact = text.replace('-', '')
            variants.append(no_hyphen_compact)
        
        # Add common pharmaceutical hyphenations
        if 'hydrochloride' in text.lower():
            variants.append(text.replace('hydrochloride', 'hydro-chloride'))
            variants.append(text.replace('hydrochloride', 'hydro chloride'))
        
        if 'sulfate' in text.lower():
            variants.append(text.replace('sulfate', 'sul-fate'))
            variants.append(text.replace('sulfate', 'sul fate'))
        
        return list(set(variants))  # Remove duplicates
    
    def _remove_drug_patterns(self, text: str) -> str:
        """Remove common drug name patterns to get core name."""
        cleaned = text
        
        # Remove salt forms
        for pattern in self.drug_patterns['salt_forms']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove stereochemistry
        for pattern in self.drug_patterns['stereochemistry']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove formulations
        for pattern in self.drug_patterns['formulations']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove strengths
        for pattern in self.drug_patterns['strengths']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove pharmaceutical suffixes
        for pattern in self.drug_patterns['pharmaceutical_suffixes']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove chemical prefixes
        for pattern in self.drug_patterns['chemical_prefixes']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _remove_indication_patterns(self, text: str) -> str:
        """Remove common indication patterns to get core condition."""
        cleaned = text
        
        # Remove severity modifiers
        for pattern in self.indication_patterns['severity']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove staging information
        for pattern in self.indication_patterns['staging']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove demographic modifiers
        for pattern in self.indication_patterns['demographics']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _phonetic_normalization(self, text: str) -> str:
        """Generate phonetic representation of text."""
        # Improved phonetic normalization using Soundex-like algorithm
        if not text:
            return ""
        
        # Convert to lowercase and remove non-alphabetic characters
        text = re.sub(r'[^a-z]', '', text.lower())
        
        if not text:
            return ""
        
        # Soundex-like algorithm for pharmaceutical names
        # Keep first letter
        phonetic = text[0]
        
        # Map consonants to numbers
        consonant_map = {
            'b': '1', 'f': '1', 'p': '1', 'v': '1',
            'c': '2', 'g': '2', 'j': '2', 'k': '2', 'q': '2', 's': '2', 'x': '2', 'z': '2',
            'd': '3', 't': '3',
            'l': '4',
            'm': '5', 'n': '5',
            'r': '6'
        }
        
        # Process remaining characters
        for char in text[1:]:
            if char in consonant_map:
                phonetic += consonant_map[char]
            # Skip vowels and other characters
        
        # Remove consecutive duplicates
        phonetic = re.sub(r'(.)\1+', r'\1', phonetic)
        
        # Pad or truncate to 4 characters
        phonetic = (phonetic + '0000')[:4]
        
        return phonetic
    
    def _generate_fuzzy_variants(self, text: str) -> List[str]:
        """Generate fuzzy matching variants."""
        variants = [text]
        
        # Common misspellings and variations
        common_variations = {
            'cancer': ['canser', 'cancr'],
            'diabetes': ['diabetis', 'diabete', 'diabet'],
            'arthritis': ['arthritus', 'arthriti', 'arthrit'],
            'leukemia': ['leukaemia', 'leukemi'],
            'tumor': ['tumour', 'tumr'],
            'therapy': ['theraphy', 'therapi', 'therap'],
            'treatment': ['treatmant', 'treatmnt', 'treat'],
            'clinical': ['clinacal', 'clinic'],
            'trial': ['trail', 'tri'],
            'study': ['studdy', 'stud'],
            'patient': ['patiant', 'patien', 'pati'],
            'disease': ['diseas', 'dise'],
            'syndrome': ['syndrom', 'syndr'],
            'infection': ['infecton', 'infecti', 'infect'],
            'inflammation': ['inflamation', 'inflammat', 'inflamm'],
            'alzheimer': ['alzheimers', 'alzheimers', 'alzheim'],
            'dementia': ['dementa', 'dementi', 'dement'],
            'simufilam': ['simufilam', 'simufilam', 'simufil'],
            'pti': ['pt', 'p-t-i', 'p t i'],
            'pt125': ['pt-125', 'pt 125', 'pti125']
        }
        
        # Generate variations based on word matching
        words = text.lower().split()
        for word in words:
            # Clean word for matching
            clean_word = re.sub(r'[^\w]', '', word)
            
            for pattern, variations in common_variations.items():
                if clean_word == pattern or clean_word in variations:
                    for variation in variations:
                        if variation != clean_word:
                            # Replace the word with variation
                            new_text = text.replace(word, variation)
                            variants.append(new_text)
        
        # Add common pharmaceutical variations
        if 'pt' in text.lower() and '125' in text.lower():
            # PTI-125 variations
            variants.extend([
                text.replace('PTI', 'PT'),
                text.replace('PTI', 'P-T-I'),
                text.replace('PTI', 'P T I'),
                text.replace('125', '125'),
                text.replace('-', ' '),
                text.replace(' ', '-'),
                text.replace('-', '')
            ])
        
        return list(set(variants))  # Remove duplicates
    
    def _generate_acronyms(self, text: str) -> List[str]:
        """Generate acronyms from indication text."""
        acronyms = []
        
        # Extract words that could form acronyms
        words = text.split()
        if len(words) >= 2:
            # Generate acronym from first letters
            acronym = ''.join(word[0].upper() for word in words if word)
            if len(acronym) >= 2:
                acronyms.append(acronym)
            
            # Generate acronyms from key words
            key_words = [word for word in words if len(word) > 3]
            if len(key_words) >= 2:
                key_acronym = ''.join(word[0].upper() for word in key_words)
                if len(key_acronym) >= 2:
                    acronyms.append(key_acronym)
        
        return acronyms
    
    def _generate_synonyms(self, text: str) -> List[str]:
        """Generate synonyms for indication text."""
        synonyms = []
        
        # Common medical synonyms
        synonym_mappings = {
            'cancer': ['carcinoma', 'malignancy', 'neoplasm', 'tumor'],
            'diabetes': ['diabetes mellitus', 'diabetic', 'diabet'],
            'arthritis': ['arthritic', 'joint inflammation', 'joint disease'],
            'leukemia': ['leukaemia', 'blood cancer', 'hematologic malignancy'],
            'tumor': ['tumour', 'mass', 'lesion', 'growth'],
            'therapy': ['treatment', 'intervention', 'management'],
            'treatment': ['therapy', 'intervention', 'management', 'care'],
            'clinical': ['medical', 'therapeutic', 'interventional'],
            'trial': ['study', 'investigation', 'research', 'experiment'],
            'study': ['trial', 'investigation', 'research', 'experiment'],
            'patient': ['subject', 'participant', 'individual', 'case'],
            'disease': ['condition', 'disorder', 'syndrome', 'illness'],
            'syndrome': ['disease', 'condition', 'disorder', 'illness'],
            'infection': ['infectious disease', 'contagion', 'disease'],
            'inflammation': ['inflammatory', 'swelling', 'irritation']
        }
        
        # Find synonyms for words in the text
        for word in text.lower().split():
            for pattern, synonym_list in synonym_mappings.items():
                if word in pattern or pattern in word:
                    synonyms.extend(synonym_list)
        
        return list(set(synonyms))  # Remove duplicates
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two normalized texts.
        
        Args:
            text1: First normalized text
            text2: Second normalized text
            
        Returns:
            Similarity score between 0 and 1
        """
        if not text1 or not text2:
            return 0.0
        
        # Use SequenceMatcher for similarity
        similarity = SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
        
        return similarity
    
    def find_matches(
        self, 
        query: str, 
        candidates: List[str], 
        threshold: Optional[float] = None
    ) -> List[Tuple[str, float]]:
        """
        Find matches for a query among candidates.
        
        Args:
            query: Query text to match
            candidates: List of candidate texts
            threshold: Minimum similarity threshold
            
        Returns:
            List of (candidate, similarity_score) tuples
        """
        if threshold is None:
            threshold = self.similarity_threshold
        
        matches = []
        normalized_query = self._basic_normalization(query)
        
        for candidate in candidates:
            normalized_candidate = self._basic_normalization(candidate)
            similarity = self.calculate_similarity(normalized_query, normalized_candidate)
            
            if similarity >= threshold:
                matches.append((candidate, similarity))
        
        # Sort by similarity score (descending)
        matches.sort(key=lambda x: x[1], reverse=True)
        
        return matches
    
    def normalize_batch(
        self, 
        texts: List[str], 
        text_type: str = 'asset'
    ) -> List[Dict[str, str]]:
        """
        Normalize a batch of texts.
        
        Args:
            texts: List of texts to normalize
            text_type: Type of text ('asset' or 'indication')
            
        Returns:
            List of normalized text dictionaries
        """
        normalized = []
        
        for text in texts:
            if text_type == 'asset':
                norm_dict = self.normalize_asset_name(text)
            else:
                norm_dict = self.normalize_indication(text)
            
            normalized.append(norm_dict)
        
        return normalized
    
    def get_normalization_stats(self, normalized_texts: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Get statistics about normalization results.
        
        Args:
            normalized_texts: List of normalized text dictionaries
            
        Returns:
            Dictionary with normalization statistics
        """
        if not normalized_texts:
            return {}
        
        total_texts = len(normalized_texts)
        
        # Count variants
        total_variants = sum(
            len(norm.get('hyphen_variants', [])) + len(norm.get('fuzzy_variants', []))
            for norm in normalized_texts
        )
        
        # Count patterns removed
        patterns_removed = sum(
            1 for norm in normalized_texts
            if norm.get('clean') != norm.get('normalized')
        )
        
        # Count ASCII conversions
        ascii_conversions = sum(
            1 for norm in normalized_texts
            if norm.get('ascii') != norm.get('normalized')
        )
        
        return {
            'total_texts': total_texts,
            'total_variants': total_variants,
            'avg_variants_per_text': total_variants / total_texts if total_texts > 0 else 0,
            'patterns_removed': patterns_removed,
            'ascii_conversions': ascii_conversions,
            'normalization_coverage': {
                'basic': total_texts,
                'ascii': ascii_conversions,
                'clean': patterns_removed,
                'phonetic': total_texts,
                'variants': total_variants
            }
        }
