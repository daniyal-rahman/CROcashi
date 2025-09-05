"""
Shared text normalization utilities for extraction workers.

This module provides centralized text normalization functions to eliminate
duplication across different extraction workers and ensure consistent behavior.
"""

import re
from typing import Dict, Any, Optional


class TextNormalizer:
    """Centralized text normalization utilities."""
    
    # Roman numeral to Arabic mapping for phase text
    ROMAN_TO_ARABIC = {
        'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
        'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10'
    }
    
    # Common OCR noise mapping
    OCR_NOISE_MAP = {
        '0': 'O', '1': 'I', '5': 'S', '8': 'B', '9': 'g',
        'l': 'I', 'I': 'l', 'O': '0', 'S': '5', 'B': '8'
    }
    
    @staticmethod
    def normalize_text(
        text: str, 
        config: Optional[Dict[str, Any]] = None,
        aggressive: bool = False
    ) -> str:
        """
        Normalize text for comparison and matching.
        
        Args:
            text: Input text to normalize
            config: Configuration dictionary with normalization options
            aggressive: Whether to use aggressive normalization (punctuation, OCR fixes)
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        normalized = text
        
        # Use config if provided, otherwise use defaults
        if config:
            normalize_text = config.get('normalize_text', True)
            preserve_case = config.get('preserve_case', False)
        else:
            normalize_text = True
            preserve_case = False
        
        if normalize_text:
            # Remove extra whitespace
            normalized = re.sub(r'\s+', ' ', normalized)
            normalized = normalized.strip()
        
        if aggressive:
            # Convert to lowercase
            normalized = normalized.lower()
            
            # Remove punctuation except for numbers
            normalized = re.sub(r'[^\w\s\d\.\-%]', ' ', normalized)
            
            # Fix common OCR errors
            for wrong_char, correct_char in TextNormalizer.OCR_NOISE_MAP.items():
                normalized = normalized.replace(wrong_char, correct_char)
        elif not preserve_case:
            # Simple case normalization
            normalized = normalized.lower()
        
        return normalized
    
    @staticmethod
    def normalize_phase_text(text: str) -> str:
        """
        Normalize phase text by converting Roman numerals to Arabic numerals.
        This helps ensure consistent phase extraction.
        
        Args:
            text: Input text containing phase information
            
        Returns:
            Text with Roman numerals converted to Arabic numerals
        """
        if not text:
            return text
        
        # Pattern to match "phase" followed by Roman numerals (including mixed patterns)
        # Handle patterns like "phase I/II", "phase I and II", etc.
        phase_roman_pattern = r'phase\s*([IiVvXx]+(?:\s*[/\s+and\s+]+\s*[IiVvXx]+)*)'
        
        def replace_roman(match):
            roman_text = match.group(1).upper()
            
            # Handle mixed patterns like "I/II" or "I and II"
            if '/' in roman_text:
                parts = roman_text.split('/')
                normalized_parts = []
                for part in parts:
                    part = part.strip()
                    if part in TextNormalizer.ROMAN_TO_ARABIC:
                        normalized_parts.append(TextNormalizer.ROMAN_TO_ARABIC[part])
                    else:
                        normalized_parts.append(part)
                return f"phase {'/'.join(normalized_parts)}"
            elif 'AND' in roman_text:
                parts = roman_text.split('AND')
                normalized_parts = []
                for part in parts:
                    part = part.strip()
                    if part in TextNormalizer.ROMAN_TO_ARABIC:
                        normalized_parts.append(TextNormalizer.ROMAN_TO_ARABIC[part])
                    else:
                        normalized_parts.append(part)
                return f"phase {' and '.join(normalized_parts)}"
            else:
                # Single Roman numeral
                if roman_text in TextNormalizer.ROMAN_TO_ARABIC:
                    return f"phase {TextNormalizer.ROMAN_TO_ARABIC[roman_text]}"
                return match.group(0)  # Return original if not found
        
        # Replace Roman numerals with Arabic numerals
        normalized_text = re.sub(phase_roman_pattern, replace_roman, text, flags=re.IGNORECASE)
        
        return normalized_text
    
    @staticmethod
    def normalize_unit(unit_text: str) -> str:
        """
        Normalize unit text for consistent comparison.
        
        Args:
            unit_text: Input unit text
            
        Returns:
            Normalized unit text
        """
        if not unit_text:
            return ""
        
        # Convert to lowercase
        normalized = unit_text.lower().strip()
        
        # Common unit normalizations
        unit_mappings = {
            'months': 'months',
            'mo': 'months',
            'm': 'months',
            'weeks': 'weeks', 
            'wks': 'weeks',
            'w': 'weeks',
            'days': 'days',
            'd': 'days',
            'years': 'years',
            'yrs': 'years',
            'y': 'years',
            'percent': '%',
            'pct': '%',
            'percentage': '%',
            'mg': 'mg',
            'milligrams': 'mg',
            'g': 'g',
            'grams': 'g',
            'kg': 'kg',
            'kilograms': 'kg',
            'ml': 'ml',
            'milliliters': 'ml',
            'l': 'l',
            'liters': 'l',
            'mm': 'mm',
            'millimeters': 'mm',
            'cm': 'cm',
            'centimeters': 'cm',
            'm': 'm',
            'meters': 'm'
        }
        
        return unit_mappings.get(normalized, normalized)
    
    @staticmethod
    def extract_numbers_from_text(text: str) -> list:
        """
        Extract all numeric values from text.
        
        Args:
            text: Input text
            
        Returns:
            List of extracted numbers
        """
        numbers = []
        
        # Match percentages
        for match in re.finditer(r'(\d+\.?\d*)\s*%', text):
            numbers.append(float(match.group(1)))
        
        # Match fractions
        for match in re.finditer(r'(\d+)/(\d+)', text):
            try:
                numbers.append(float(match.group(1)))
                numbers.append(float(match.group(2)))
            except ValueError:
                continue
        
        # Match decimal numbers
        for match in re.finditer(r'\b(\d+\.\d+)\b', text):
            try:
                numbers.append(float(match.group(1)))
            except ValueError:
                continue
        
        # Match integers
        for match in re.finditer(r'\b(\d+)\b', text):
            try:
                numbers.append(float(match.group(1)))
            except ValueError:
                continue
        
        return numbers
    
    @staticmethod
    def numbers_match(num1: float, num2: float, tolerance: float = 0.01) -> bool:
        """
        Check if two numbers match within tolerance.
        
        Args:
            num1: First number
            num2: Second number
            tolerance: Tolerance for comparison
            
        Returns:
            True if numbers match within tolerance
        """
        return abs(num1 - num2) <= tolerance
