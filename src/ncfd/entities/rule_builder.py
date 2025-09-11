"""
Rule builder for generating must/should/cannot rules from entity packs.
"""

import logging
from typing import Dict, List, Set
from .schema import EntityPack

logger = logging.getLogger(__name__)


class RuleBuilder:
    """Builds must/should/cannot rules from entity packs."""
    
    def __init__(self):
        """Initialize rule builder with domain profiles."""
        self.domain_profiles = {
            "oncology": {
                "cannot_terms": [
                    "zebrafish", "murine", "mouse model", "rat model",
                    "in vitro", "in vivo", "cell line", "xenograft"
                ],
                "should_terms": [
                    "randomized", "placebo", "double-blind", "phase", "trial",
                    "efficacy", "safety", "tumor response", "survival"
                ]
            },
            "neurology": {
                "cannot_terms": [
                    "carcinoma", "melanoma", "glioblastoma", "chemoradiotherapy", "oncology",
                    "zebrafish", "murine", "mouse model", "rat model",
                    "in vitro", "in vivo", "cell line"
                ],
                "should_terms": [
                    "randomized", "placebo", "double-blind", "phase", "trial",
                    "cognitive", "dementia", "alzheimer", "parkinson", "ms"
                ]
            },
            "cardiology": {
                "cannot_terms": [
                    "carcinoma", "melanoma", "glioblastoma", "chemoradiotherapy", "oncology",
                    "zebrafish", "murine", "mouse model", "rat model",
                    "in vitro", "in vivo", "cell line"
                ],
                "should_terms": [
                    "randomized", "placebo", "double-blind", "phase", "trial",
                    "cardiovascular", "heart", "cardiac", "myocardial", "stroke"
                ]
            },
            "general": {
                "cannot_terms": [
                    "carcinoma", "melanoma", "glioblastoma", "chemoradiotherapy", "oncology",
                    "zebrafish", "murine", "mouse model", "rat model",
                    "in vitro", "in vivo", "cell line", "xenograft"
                ],
                "should_terms": [
                    "randomized", "placebo", "double-blind", "phase", "trial",
                    "efficacy", "safety", "clinical"
                ]
            }
        }
    
    def build_rules(self, pack: EntityPack, domain: str = "general") -> Dict[str, List[str]]:
        """
        Build must/should/cannot rules from entity pack.
        
        Args:
            pack: Entity pack to build rules from
            domain: Domain profile to use (oncology, neurology, cardiology, general)
            
        Returns:
            Dictionary containing must, should, cannot, and mechanism rules
        """
        if domain not in self.domain_profiles:
            logger.warning(f"Unknown domain '{domain}', using 'general'")
            domain = "general"
        
        # Must-link terms (at least one required)
        must = list(set(pack.get_must_link_terms()))
        
        # Should-link terms (boost score)
        should = list(set(pack.get_should_link_terms()))
        
        # Add domain-specific should terms
        domain_should = self.domain_profiles[domain]["should_terms"]
        should.extend(domain_should)
        should = list(set(should))  # Remove duplicates
        
        # Cannot-link terms (drop unless must-link present)
        cannot = self.domain_profiles[domain]["cannot_terms"].copy()
        
        # Remove oncology terms if indication is oncology
        if self._is_oncology_indication(pack.indications.primary):
            oncology_terms = {
                "oncology", "carcinoma", "melanoma", "glioblastoma", "chemoradiotherapy"
            }
            cannot = [t for t in cannot if t not in oncology_terms]
            logger.info(f"Removed oncology cannot-terms for oncology indication")
        
        # Add indication-specific cannot terms
        cannot.extend(self._get_indication_specific_cannot_terms(pack.indications.primary))
        cannot = list(set(cannot))  # Remove duplicates
        
        rules = {
            "must": must,
            "should": should,
            "cannot": cannot,
            "mechanism": pack.mechanism.targets
        }
        
        logger.info(f"Built rules for {pack.entity_id}: {len(must)} must, {len(should)} should, {len(cannot)} cannot")
        return rules
    
    def _is_oncology_indication(self, indications: List[str]) -> bool:
        """Check if any indication is oncology-related."""
        oncology_terms = [
            "cancer", "carcinoma", "tumor", "tumour", "neoplasm", "oncology",
            "melanoma", "glioblastoma", "leukemia", "lymphoma", "sarcoma"
        ]
        return any(any(term in ind.lower() for term in oncology_terms) for ind in indications)
    
    def _get_indication_specific_cannot_terms(self, indications: List[str]) -> List[str]:
        """Get indication-specific cannot terms."""
        cannot_terms = []
        
        for indication in indications:
            indication_lower = indication.lower()
            
            # Alzheimer's specific cannot terms
            if any(term in indication_lower for term in ["alzheimer", "dementia", "cognitive"]):
                cannot_terms.extend([
                    "cancer", "tumor", "oncology", "cardiac", "heart", "stroke"
                ])
            
            # Cancer specific cannot terms
            elif any(term in indication_lower for term in ["cancer", "carcinoma", "tumor", "oncology"]):
                cannot_terms.extend([
                    "alzheimer", "dementia", "cognitive", "parkinson", "ms"
                ])
            
            # Cardiac specific cannot terms
            elif any(term in indication_lower for term in ["cardiac", "heart", "cardiovascular"]):
                cannot_terms.extend([
                    "cancer", "tumor", "oncology", "alzheimer", "dementia"
                ])
        
        return list(set(cannot_terms))
    
    def validate_rules(self, rules: Dict[str, List[str]]) -> bool:
        """
        Validate that rules are properly formed.
        
        Args:
            rules: Rules dictionary to validate
            
        Returns:
            True if rules are valid, False otherwise
        """
        required_keys = ["must", "should", "cannot", "mechanism"]
        
        # Check required keys
        if not all(key in rules for key in required_keys):
            logger.error(f"Missing required rule keys: {required_keys}")
            return False
        
        # Check that must terms exist
        if not rules["must"]:
            logger.error("Must terms cannot be empty")
            return False
        
        # Check that lists are actually lists
        for key in required_keys:
            if not isinstance(rules[key], list):
                logger.error(f"Rule '{key}' must be a list")
                return False
        
        logger.info("Rules validation passed")
        return True
    
    def get_domain_profiles(self) -> Dict[str, Dict[str, List[str]]]:
        """Get available domain profiles."""
        return self.domain_profiles.copy()
    
    def add_domain_profile(self, domain: str, profile: Dict[str, List[str]]):
        """
        Add a new domain profile.
        
        Args:
            domain: Domain name
            profile: Profile dictionary with cannot_terms and should_terms
        """
        if "cannot_terms" not in profile or "should_terms" not in profile:
            raise ValueError("Profile must contain 'cannot_terms' and 'should_terms'")
        
        self.domain_profiles[domain] = profile
        logger.info(f"Added domain profile: {domain}")
    
    def remove_domain_profile(self, domain: str):
        """
        Remove a domain profile.
        
        Args:
            domain: Domain name to remove
        """
        if domain in self.domain_profiles:
            del self.domain_profiles[domain]
            logger.info(f"Removed domain profile: {domain}")
        else:
            logger.warning(f"Domain profile not found: {domain}")
