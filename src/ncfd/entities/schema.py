"""
Entity Pack Schema - Simplified In-Memory Data Structures.

Defines the canonical data model for literature retrieval without database dependencies.
All entity packs are created and managed in-memory.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class CompanyInfo:
    """Company information for entity packs."""
    canonical: str
    aliases: List[str]


@dataclass
class AssetInfo:
    """Asset/drug information for entity packs."""
    canonical: str
    aliases: List[str]


@dataclass
class MechanismInfo:
    """Mechanism of action information."""
    targets: List[str]


@dataclass
class IndicationInfo:
    """Disease/indication information."""
    primary: List[str]
    synonyms: List[str]


@dataclass
class RegistryInfo:
    """Clinical trial registry information."""
    nct_ids: List[str]


@dataclass
class PublisherInfo:
    """Publisher/journal information."""
    sponsor_strings: List[str]


@dataclass
class DateRangeInfo:
    """Date range information."""
    active_since: int


@dataclass
class EntityPack:
    """Complete entity pack for literature retrieval."""
    entity_id: str
    company: CompanyInfo
    asset: AssetInfo
    mechanism: MechanismInfo
    indications: IndicationInfo
    registries: RegistryInfo
    publishers: PublisherInfo
    date_ranges: DateRangeInfo
    
    def get_all_asset_terms(self) -> List[str]:
        """Get all asset terms (canonical + aliases)."""
        return [self.asset.canonical] + self.asset.aliases
    
    def get_all_indication_terms(self) -> List[str]:
        """Get all indication terms (primary + synonyms)."""
        return self.indications.primary + self.indications.synonyms
    
    def get_all_company_terms(self) -> List[str]:
        """Get all company terms (canonical + aliases)."""
        return [self.company.canonical] + self.company.aliases
    
    def get_all_mechanism_targets(self) -> List[str]:
        """Get all mechanism targets."""
        return self.mechanism.targets
    
    def get_all_nct_ids(self) -> List[str]:
        """Get all NCT IDs."""
        return self.registries.nct_ids
    
    def get_all_author_terms(self) -> List[str]:
        """Get all author-related terms."""
        # Author terms are typically company names and researcher names
        author_terms = []
        
        # Add company canonical and aliases
        author_terms.append(self.company.canonical)
        author_terms.extend(self.company.aliases)
        
        # Add publisher strings if available
        author_terms.extend(self.publishers.sponsor_strings)
        
        # Remove duplicates and empty strings
        author_terms = [term for term in author_terms if term and term.strip()]
        return list(set(author_terms))
    
    def get_must_link_terms(self) -> List[str]:
        """Get all must-link terms for policy engine."""
        must_link_terms = []
        must_link_terms.extend(self.asset.aliases)
        must_link_terms.extend(self.company.aliases)
        must_link_terms.extend(self.registries.nct_ids)
        must_link_terms.append(self.asset.canonical)
        must_link_terms.append(self.company.canonical)
        # Add indication terms as must-link terms
        must_link_terms.extend(self.indications.primary)
        must_link_terms.extend(self.indications.synonyms)
        # Add mechanism targets as must-link terms
        must_link_terms.extend(self.mechanism.targets)
        return must_link_terms
    
    def get_should_link_terms(self) -> List[str]:
        """Get should-link terms for policy engine scoring."""
        # Should-link terms are related but not absolutely required terms
        # These provide bonus scoring but aren't mandatory like must-link terms
        should_link_terms = []
        
        # Add related indication terms (broader disease categories)
        if self.indications.primary:
            primary_indication = self.indications.primary[0].lower()
            if "alzheimer" in primary_indication:
                should_link_terms.extend([
                    "dementia", "cognitive", "memory", "neurodegenerative", 
                    "brain", "neurological", "cognitive decline", "mild cognitive impairment"
                ])
            elif "diabetes" in primary_indication:
                should_link_terms.extend([
                    "glucose", "insulin", "metabolic", "glycemic", "blood sugar",
                    "pancreas", "beta cell", "diabetic"
                ])
            elif "cancer" in primary_indication or "tumor" in primary_indication:
                should_link_terms.extend([
                    "oncology", "tumor", "cancer", "malignancy", "metastasis",
                    "chemotherapy", "radiation", "immunotherapy"
                ])
        
        # Add related mechanism terms (broader target categories)
        if self.mechanism.targets:
            for target in self.mechanism.targets:
                target_lower = target.lower()
                if "amyloid" in target_lower:
                    should_link_terms.extend([
                        "beta-amyloid", "aβ", "plaques", "aggregation", "oligomers"
                    ])
                elif "tau" in target_lower:
                    should_link_terms.extend([
                        "neurofibrillary", "tangles", "phosphorylation", "microtubule"
                    ])
                elif "filamin" in target_lower:
                    should_link_terms.extend([
                        "actin", "cytoskeleton", "cell adhesion", "integrin"
                    ])
        
        # Add general clinical trial terms
        should_link_terms.extend([
            "clinical trial", "randomized", "placebo", "double-blind", "phase",
            "efficacy", "safety", "tolerability", "adverse events", "endpoint",
            "primary endpoint", "secondary endpoint", "biomarker", "pharmacokinetics"
        ])
        
        # Remove duplicates and return
        return list(set(should_link_terms))
    
    def get_cannot_link_terms(self) -> List[str]:
        """Get oncology terms that should trigger cannot-link penalties."""
        # This should return oncology-specific terms that indicate non-relevant content
        # For now, return a basic set of oncology terms
        oncology_terms = [
            "cancer", "tumor", "tumour", "carcinoma", "sarcoma", "lymphoma", 
            "leukemia", "leukaemia", "melanoma", "metastasis", "metastatic",
            "oncology", "chemotherapy", "radiation", "radiotherapy", "immunotherapy",
            "targeted therapy", "biomarker", "prognosis", "survival", "progression-free"
        ]
        return oncology_terms
