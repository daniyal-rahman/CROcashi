"""
Facts Normalizer

Deterministic post-processing to extract structured canonical facts
from free text factsheet sections. This makes gating and comparisons reliable.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BiomarkerObservation:
    """Structured biomarker observation."""
    name: str
    direction: str  # 'increase', 'decrease', 'no_change'
    magnitude: Optional[float] = None
    unit: Optional[str] = None
    confidence: float = 0.8


@dataclass
class DoseRegimen:
    """Structured dose regimen."""
    dose: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    route: Optional[str] = None


class FactsNormalizer:
    """Normalizes free text facts into structured canonical facts."""
    
    def __init__(self):
        # Common mechanism targets
        self.mechanism_patterns = [
            r'\bFLNA\b',
            r'\bfilamin\s+A\b',
            r'\bmTOR\b',
            r'\bAKT\b',
            r'\bPI3K\b',
            r'\bERK\b',
            r'\bJNK\b',
            r'\bp38\b',
            r'\bNF-?κB\b',
            r'\bSTAT3\b',
            r'\bTNF-?α\b',
            r'\bIL-?1β\b',
            r'\bIL-?6\b',
            r'\bTGF-?β\b',
            r'\bVEGF\b',
            r'\bEGFR\b',
            r'\bHER2\b',
            r'\bPD-?1\b',
            r'\bPD-?L1\b',
            r'\bCTLA-?4\b'
        ]
        
        # Biomarker patterns
        self.biomarker_patterns = [
            r'\bpTau181\b',
            r'\bpTau217\b',
            r'\bAβ42\b',
            r'\bAβ40\b',
            r'\bAβ\b',
            r'\bamyloid\s+β\b',
            r'\btau\b',
            r'\bphosphorylated\s+tau\b',
            r'\bCSF\b',
            r'\bplasma\b',
            r'\bserum\b',
            r'\bCSF\s+tau\b',
            r'\bCSF\s+Aβ\b',
            r'\bFDG-?PET\b',
            r'\bPET\b',
            r'\bMRI\b',
            r'\bCT\b',
            r'\bMMSE\b',
            r'\bADAS-?Cog\b',
            r'\bCDR\b',
            r'\bNPI\b'
        ]
        
        # Population patterns
        self.population_patterns = [
            r'\bAD\s+patients?\b',
            r'\bAlzheimer\'?s\s+patients?\b',
            r'\bmild\s+to\s+moderate\s+AD\b',
            r'\bearly\s+stage\s+AD\b',
            r'\blate\s+stage\s+AD\b',
            r'\bmice\b',
            r'\brats?\b',
            r'\banimals?\b',
            r'\bcell\s+line\b',
            r'\bculture\b',
            r'\bin\s+vitro\b',
            r'\bin\s+vivo\b'
        ]
        
        # Dose patterns
        self.dose_patterns = [
            r'(\d+(?:\.\d+)?)\s*mg',
            r'(\d+(?:\.\d+)?)\s*g',
            r'(\d+(?:\.\d+)?)\s*μg',
            r'(\d+(?:\.\d+)?)\s*ng',
            r'(\d+(?:\.\d+)?)\s*μM',
            r'(\d+(?:\.\d+)?)\s*mM',
            r'(\d+(?:\.\d+)?)\s*nM'
        ]
        
        # Frequency patterns
        self.frequency_patterns = [
            r'\bdaily\b',
            r'\bbid\b',
            r'\btid\b',
            r'\bqid\b',
            r'\bweekly\b',
            r'\bmonthly\b',
            r'\btwice\s+daily\b',
            r'\bthree\s+times\s+daily\b',
            r'\bfour\s+times\s+daily\b'
        ]
        
        # Duration patterns
        self.duration_patterns = [
            r'(\d+)\s*weeks?',
            r'(\d+)\s*months?',
            r'(\d+)\s*years?',
            r'(\d+)\s*days?',
            r'(\d+)\s*hours?'
        ]
    
    def normalize_facts(self, factsheet_sections: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize factsheet sections into structured canonical facts.
        
        Args:
            factsheet_sections: The factsheet sections from extraction
            
        Returns:
            Dictionary with normalized facts
        """
        normalized = {
            'mechanism_targets': [],
            'biomarkers_observed': [],
            'population_kind': None,
            'dose_regimen': None,
            'efficacy_summary': None,
            'safety_summary': None
        }
        
        # Combine all text for analysis
        all_text = ' '.join([
            str(section) for section in factsheet_sections.values() 
            if isinstance(section, str) and section.strip()
        ]).lower()
        
        # Extract mechanism targets
        normalized['mechanism_targets'] = self._extract_mechanism_targets(all_text)
        
        # Extract biomarker observations
        normalized['biomarkers_observed'] = self._extract_biomarker_observations(all_text)
        
        # Extract population kind
        normalized['population_kind'] = self._extract_population_kind(all_text)
        
        # Extract dose regimen
        normalized['dose_regimen'] = self._extract_dose_regimen(all_text)
        
        # Extract efficacy summary
        normalized['efficacy_summary'] = self._extract_efficacy_summary(factsheet_sections)
        
        # Extract safety summary
        normalized['safety_summary'] = self._extract_safety_summary(factsheet_sections)
        
        logger.debug(f"Normalized facts: {normalized}")
        return normalized
    
    def _extract_mechanism_targets(self, text: str) -> List[str]:
        """Extract mechanism targets from text."""
        targets = []
        for pattern in self.mechanism_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                target = match.upper()
                if target not in targets:
                    targets.append(target)
        return targets
    
    def _extract_biomarker_observations(self, text: str) -> List[Dict[str, Any]]:
        """Extract biomarker observations from text."""
        observations = []
        
        for biomarker_pattern in self.biomarker_patterns:
            # Find biomarker mentions
            biomarker_matches = re.finditer(biomarker_pattern, text, re.IGNORECASE)
            
            for match in biomarker_matches:
                biomarker_name = match.group().upper()
                
                # Look for direction indicators around the biomarker
                start_pos = max(0, match.start() - 100)
                end_pos = min(len(text), match.end() + 100)
                context = text[start_pos:end_pos]
                
                # Extract direction
                direction = self._extract_direction(context)
                
                # Extract magnitude if present
                magnitude = self._extract_magnitude(context)
                
                # Extract unit if present
                unit = self._extract_unit(context)
                
                observation = {
                    'name': biomarker_name,
                    'direction': direction,
                    'magnitude': magnitude,
                    'unit': unit,
                    'confidence': 0.8
                }
                
                # Avoid duplicates
                if not any(obs['name'] == biomarker_name for obs in observations):
                    observations.append(observation)
        
        return observations
    
    def _extract_direction(self, context: str) -> str:
        """Extract direction (increase/decrease/no_change) from context."""
        increase_words = ['increase', 'elevated', 'higher', 'up', 'rise', 'boost']
        decrease_words = ['decrease', 'reduced', 'lower', 'down', 'decline', 'suppress']
        
        for word in increase_words:
            if word in context:
                return 'increase'
        
        for word in decrease_words:
            if word in context:
                return 'decrease'
        
        return 'no_change'
    
    def _extract_magnitude(self, context: str) -> Optional[float]:
        """Extract magnitude from context."""
        # Look for percentage changes
        percentage_match = re.search(r'(\d+(?:\.\d+)?)\s*%', context)
        if percentage_match:
            return float(percentage_match.group(1))
        
        # Look for fold changes
        fold_match = re.search(r'(\d+(?:\.\d+)?)\s*fold', context)
        if fold_match:
            return float(fold_match.group(1))
        
        # Look for ratio changes
        ratio_match = re.search(r'(\d+(?:\.\d+)?)\s*times', context)
        if ratio_match:
            return float(ratio_match.group(1))
        
        return None
    
    def _extract_unit(self, context: str) -> Optional[str]:
        """Extract unit from context."""
        units = ['%', 'fold', 'times', 'mg/dl', 'ng/ml', 'pg/ml', 'IU/ml', 'U/ml']
        
        for unit in units:
            if unit in context:
                return unit
        
        return None
    
    def _extract_population_kind(self, text: str) -> Optional[str]:
        """Extract population kind from text."""
        for pattern in self.population_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group().strip()
        return None
    
    def _extract_dose_regimen(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract dose regimen from text."""
        regimen = {}
        
        # Extract dose
        for pattern in self.dose_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                regimen['dose'] = match.group(1) + ' ' + match.group(0).split()[1]
                break
        
        # Extract frequency
        for pattern in self.frequency_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                regimen['frequency'] = match.group().strip()
                break
        
        # Extract duration
        for pattern in self.duration_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                regimen['duration'] = match.group().strip()
                break
        
        # Extract route
        route_patterns = ['oral', 'iv', 'intravenous', 'subcutaneous', 'intramuscular', 'topical']
        for pattern in route_patterns:
            if pattern in text:
                regimen['route'] = pattern
                break
        
        return regimen if regimen else None
    
    def _extract_efficacy_summary(self, factsheet_sections: Dict[str, Any]) -> Optional[str]:
        """Extract efficacy summary from factsheet sections."""
        efficacy_fields = ['efficacy_data', 'key_findings', 'primary_endpoint_results']
        
        for field in efficacy_fields:
            if field in factsheet_sections and factsheet_sections[field]:
                return str(factsheet_sections[field])[:200] + '...' if len(str(factsheet_sections[field])) > 200 else str(factsheet_sections[field])
        
        return None
    
    def _extract_safety_summary(self, factsheet_sections: Dict[str, Any]) -> Optional[str]:
        """Extract safety summary from factsheet sections."""
        safety_fields = ['safety_data', 'safety_results']
        
        for field in safety_fields:
            if field in factsheet_sections and factsheet_sections[field]:
                return str(factsheet_sections[field])[:200] + '...' if len(str(factsheet_sections[field])) > 200 else str(factsheet_sections[field])
        
        return None
