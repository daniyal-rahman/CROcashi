"""
Entity pack schema definitions.

Defines the canonical data model for assets, companies, and their relationships.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class CompanyInfo:
    """Company information with canonical name and aliases."""
    canonical: str
    aliases: List[str]


@dataclass
class AssetInfo:
    """Asset information with canonical name and aliases."""
    canonical: str
    aliases: List[str]


@dataclass
class MechanismInfo:
    """Mechanism of action information."""
    targets: List[str]


@dataclass
class IndicationInfo:
    """Indication information with primary and synonym terms."""
    primary: List[str]
    synonyms: List[str]


@dataclass
class RegistryInfo:
    """Registry information including NCT IDs and other identifiers."""
    nct_ids: List[str]
    cas_rn: Optional[str] = None
    uspto_ids: List[str] = None
    
    def __post_init__(self):
        if self.uspto_ids is None:
            self.uspto_ids = []


@dataclass
class PublisherInfo:
    """Publisher and sponsor information."""
    sponsor_strings: List[str]


@dataclass
class AuthorInfo:
    """Author information for key researchers."""
    primary: List[str]
    aliases: List[str]


@dataclass
class DateRangeInfo:
    """Date range information for the entity."""
    active_since: int
    active_until: Optional[int] = None


@dataclass
class EntityPack:
    """Complete entity pack containing all information about an asset."""
    entity_id: str
    company: CompanyInfo
    asset: AssetInfo
    mechanism: MechanismInfo
    indications: IndicationInfo
    registries: RegistryInfo
    publishers: PublisherInfo
    date_ranges: DateRangeInfo
    authors: Optional[AuthorInfo] = None
    notes: Optional[str] = None
    
    def get_all_asset_terms(self) -> List[str]:
        """Get all asset terms (canonical + aliases)."""
        return [self.asset.canonical] + self.asset.aliases
    
    def get_all_company_terms(self) -> List[str]:
        """Get all company terms (canonical + aliases)."""
        return [self.company.canonical] + self.company.aliases
    
    def get_all_indication_terms(self) -> List[str]:
        """Get all indication terms (primary + synonyms)."""
        return self.indications.primary + self.indications.synonyms
    
    def get_all_author_terms(self) -> List[str]:
        """Get all author terms (primary + aliases)."""
        if self.authors is None:
            return []
        return self.authors.primary + self.authors.aliases
    
    def get_must_link_terms(self) -> List[str]:
        """Get all must-link terms (asset + company + NCT IDs)."""
        return (self.get_all_asset_terms() + 
                self.get_all_company_terms() + 
                self.registries.nct_ids)
    
    def get_should_link_terms(self) -> List[str]:
        """Get all should-link terms (indications + trial terms)."""
        trial_terms = ["randomized", "placebo", "double-blind", "phase", "trial"]
        return self.get_all_indication_terms() + trial_terms
    
    def get_cannot_link_terms(self) -> List[str]:
        """Get oncology/cancer terms that require must-link validation."""
        return [
            "carcinoma", "esophageal", "melanoma", "chemoradiotherapy", 
            "oncology", "cancer", "tumor", "neoplasm", "metastasis", 
            "chemotherapy", "radiation", "radiotherapy", "sarcoma",
            "lymphoma", "leukemia", "adenocarcinoma", "squamous cell"
        ]