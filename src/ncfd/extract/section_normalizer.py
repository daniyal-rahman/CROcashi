"""
Section Normalization Module

Handles section aliases and provides normalized section enums for consistent
section matching across the system.
"""

from enum import Enum
from typing import Dict, List, Optional, Set
import yaml
from pathlib import Path


class NormalizedSection(Enum):
    """Normalized section enum for consistent section handling."""
    METHODS = "methods"
    RESULTS = "results"
    SAFETY = "safety"
    ABSTRACT = "abstract"
    DISCUSSION = "discussion"
    MIXED = "mixed"
    TABLE = "table"
    UNKNOWN = "unknown"


class SectionNormalizer:
    """Handles section normalization and alias matching."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize with section constraints configuration."""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "section_constraints.yaml"
        
        self.config_path = Path(config_path)
        self.section_aliases = self._load_section_aliases()
        self._build_reverse_mapping()
    
    def _load_section_aliases(self) -> Dict[str, List[str]]:
        """Load section aliases from configuration file."""
        if not self.config_path.exists():
            # Fallback to default aliases
            return self._get_default_aliases()
        
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
                return config.get('section_aliases', self._get_default_aliases())
        except Exception as e:
            print(f"Warning: Could not load section constraints from {self.config_path}: {e}")
            return self._get_default_aliases()
    
    def _get_default_aliases(self) -> Dict[str, List[str]]:
        """Get default section aliases if config file is not available."""
        return {
            "methods": [
                "Methods", "Materials and Methods", "Patients and Methods",
                "Protocol", "Statistical Analysis", "SAP", "Study Design",
                "Trial Design", "Randomization", "Sample Size"
            ],
            "results": [
                "Results", "Efficacy Results", "Outcome", "Findings",
                "Primary Results", "Secondary Results", "Efficacy",
                "Response", "Survival"
            ],
            "safety": [
                "Safety", "Adverse Events", "Toxicity", "Safety Results",
                "Adverse Reactions", "Tolerability"
            ],
            "abstract": [
                "Abstract", "Background", "Objective", "Conclusions", "Summary"
            ],
            "discussion": [
                "Discussion", "Interpretation", "Clinical Implications",
                "Conclusions", "Limitations"
            ],
            "mixed": [
                "Results and Discussion", "Discussion and Results",
                "Findings and Discussion"
            ]
        }
    
    def _build_reverse_mapping(self):
        """Build reverse mapping from alias to normalized section."""
        self.alias_to_normalized = {}
        for normalized_section, aliases in self.section_aliases.items():
            for alias in aliases:
                self.alias_to_normalized[alias.lower()] = normalized_section
    
    def normalize_section(self, section: str) -> NormalizedSection:
        """Normalize a section string to the enum value."""
        if not section:
            return NormalizedSection.UNKNOWN
        
        section_lower = section.lower().strip()
        
        # Direct mapping
        if section_lower in self.alias_to_normalized:
            return NormalizedSection(self.alias_to_normalized[section_lower])
        
        # Try exact match with enum values
        try:
            return NormalizedSection(section_lower)
        except ValueError:
            pass
        
        # Try partial matching
        for alias, normalized in self.alias_to_normalized.items():
            if section_lower in alias or alias in section_lower:
                return NormalizedSection(normalized)
        
        return NormalizedSection.UNKNOWN
    
    def get_section_aliases(self, normalized_section: NormalizedSection) -> List[str]:
        """Get all aliases for a normalized section."""
        return self.section_aliases.get(normalized_section.value, [])
    
    def is_valid_section(self, section: str) -> bool:
        """Check if a section is valid (can be normalized)."""
        normalized = self.normalize_section(section)
        return normalized != NormalizedSection.UNKNOWN
    
    def get_primary_section_name(self, normalized_section: NormalizedSection) -> str:
        """Get the primary (canonical) name for a normalized section."""
        aliases = self.get_section_aliases(normalized_section)
        if aliases:
            return aliases[0]  # First alias is considered primary
        return normalized_section.value.title()


# Global instance for easy access
section_normalizer = SectionNormalizer()
