"""
Study Type Classifier

Rules-based classifier to determine study type before extraction.
This helps tailor the extraction prompt to the appropriate study type.
"""

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class StudyTypeClassifier:
    """Rules-based classifier for study types."""
    
    def __init__(self):
        # Clinical trial indicators
        self.clinical_indicators = [
            r'\brandomized\b',
            r'\bplacebo\b',
            r'\bNCT\d+\b',  # Clinical trial registry numbers
            r'\bphase\s+[IVX]+',  # Phase I, II, III, IV
            r'\bdouble.?blind\b',
            r'\bsingle.?blind\b',
            r'\bcontrolled\b',
            r'\bclinical\s+trial\b',
            r'\bpatients?\b',
            r'\bparticipants?\b',
            r'\bcohort\b',
            r'\barm\b',
            r'\btreatment\s+group\b',
            r'\bcontrol\s+group\b'
        ]
        
        # Preclinical indicators
        self.preclinical_indicators = [
            r'\bmice?\b',
            r'\brats?\b',
            r'\bmouse\b',
            r'\brat\b',
            r'\banimal\b',
            r'\bin\s+vitro\b',
            r'\bin\s+vivo\b',
            r'\bcell\s+line\b',
            r'\bculture\b',
            r'\bwestern\s+blot\b',
            r'\bimmunostaining\b',
            r'\bimmunohistochemistry\b',
            r'\bflow\s+cytometry\b',
            r'\bPCR\b',
            r'\bqPCR\b',
            r'\bELISA\b',
            r'\bdose.?response\b',
            r'\bIC50\b',
            r'\bEC50\b',
            r'\bLD50\b'
        ]
        
        # Review indicators
        self.review_indicators = [
            r'\breview\b',
            r'\bmeta.?analysis\b',
            r'\bsystematic\s+review\b',
            r'\bliterature\s+review\b',
            r'\bcomprehensive\s+review\b',
            r'\boverview\b',
            r'\bsummary\b',
            r'\bperspective\b',
            r'\bcommentary\b',
            r'\beditorial\b',
            r'\bopinion\b',
            r'\bposition\s+paper\b'
        ]
        
        # Case study indicators
        self.case_study_indicators = [
            r'\bcase\s+study\b',
            r'\bcase\s+report\b',
            r'\bcase\s+series\b',
            r'\bsingle\s+case\b',
            r'\bpatient\s+report\b',
            r'\bclinical\s+case\b',
            r'\bcase\s+presentation\b'
        ]
    
    def classify(self, doc_text: str, doc_title: str = "", doc_abstract: str = "") -> str:
        """
        Classify study type based on text content.
        
        Args:
            doc_text: Full document text
            doc_title: Document title
            doc_abstract: Document abstract
            
        Returns:
            Study type: 'clinical_trial', 'preclinical', 'review', 'case_study', or 'other'
        """
        # Combine all text for analysis
        combined_text = f"{doc_title} {doc_abstract} {doc_text}".lower()
        
        # Count indicators for each type
        clinical_score = self._count_indicators(combined_text, self.clinical_indicators)
        preclinical_score = self._count_indicators(combined_text, self.preclinical_indicators)
        review_score = self._count_indicators(combined_text, self.review_indicators)
        case_study_score = self._count_indicators(combined_text, self.case_study_indicators)
        
        logger.debug(f"Study type scores - Clinical: {clinical_score}, Preclinical: {preclinical_score}, Review: {review_score}, Case Study: {case_study_score}")
        
        # Determine study type based on scores
        scores = {
            'clinical_trial': clinical_score,
            'preclinical': preclinical_score,
            'review': review_score,
            'case_study': case_study_score
        }
        
        # Get the highest scoring type
        max_score = max(scores.values())
        if max_score == 0:
            return 'other'
        
        # Return the type with the highest score
        study_type = max(scores, key=scores.get)
        
        # Special rules for edge cases
        if study_type == 'clinical_trial' and preclinical_score > 0:
            # If it mentions both clinical and preclinical, check context
            if 'preclinical' in combined_text or 'animal' in combined_text:
                # If preclinical is mentioned as background, still clinical
                if 'background' in combined_text or 'introduction' in combined_text:
                    pass  # Keep as clinical
                else:
                    # Otherwise, might be preclinical
                    study_type = 'preclinical'
        
        logger.info(f"Classified study type as: {study_type} (scores: {scores})")
        return study_type
    
    def _count_indicators(self, text: str, indicators: list) -> int:
        """Count how many indicators are found in the text."""
        count = 0
        for pattern in indicators:
            if re.search(pattern, text, re.IGNORECASE):
                count += 1
        return count
    
    def get_study_type_context(self, study_type: str) -> Dict[str, Any]:
        """
        Get context information for a study type to help with extraction.
        
        Args:
            study_type: The classified study type
            
        Returns:
            Dictionary with context information for extraction
        """
        contexts = {
            'clinical_trial': {
                'focus_areas': ['primary_endpoint_results', 'secondary_endpoint_results', 'safety_results', 'total_enrolled', 'dropout_rate'],
                'extraction_guidance': 'Focus on clinical trial endpoints, safety data, enrollment numbers, and completion rates.',
                'expected_fields': ['efficacy_data', 'safety_data', 'population_data']
            },
            'preclinical': {
                'focus_areas': ['mechanism_data', 'efficacy_data', 'safety_data', 'dosing_data', 'biomarker_data'],
                'extraction_guidance': 'Focus on mechanism of action, efficacy in animal models, safety profile, dosing information, and biomarker data.',
                'expected_fields': ['mechanism_data', 'efficacy_data', 'safety_data', 'dosing_data', 'biomarker_data']
            },
            'review': {
                'focus_areas': ['key_findings', 'mechanism_data', 'efficacy_data', 'safety_data', 'limitations'],
                'extraction_guidance': 'Focus on key findings, conclusions, mechanism summaries, efficacy overview, and limitations.',
                'expected_fields': ['key_findings', 'mechanism_data', 'efficacy_data', 'safety_data', 'limitations']
            },
            'case_study': {
                'focus_areas': ['key_findings', 'efficacy_data', 'safety_data', 'population_data', 'dosing_data'],
                'extraction_guidance': 'Focus on patient outcomes, treatment details, safety observations, and dosing information.',
                'expected_fields': ['key_findings', 'efficacy_data', 'safety_data', 'population_data', 'dosing_data']
            },
            'other': {
                'focus_areas': ['key_findings', 'mechanism_data', 'efficacy_data', 'safety_data'],
                'extraction_guidance': 'Extract any important findings, mechanism information, efficacy data, and safety information.',
                'expected_fields': ['key_findings', 'mechanism_data', 'efficacy_data', 'safety_data']
            }
        }
        
        return contexts.get(study_type, contexts['other'])
