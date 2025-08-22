"""
Study card processing for trial failure detection.

This module handles the processing, validation, and enrichment of study cards
including data transformation, quality checks, and metadata extraction.
"""

import json
import logging
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, asdict
import re
from pathlib import Path

from ..db.models import Trial, TrialVersion, Study
from ..db.session import get_session
from ..signals import evaluate_all_signals
from ..scoring import ScoringEngine


@dataclass
class ProcessingResult:
    """Result of study card processing."""
    success: bool
    processed_study_card: Optional[Dict[str, Any]] = None
    extracted_metadata: Optional[Dict[str, Any]] = None
    validation_errors: List[str] = None
    enrichment_data: Optional[Dict[str, Any]] = None
    processing_time: float = 0.0
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class EnrichmentData:
    """Data enriched during processing."""
    sponsor_experience: str
    indication_category: str
    phase_category: str
    endpoint_complexity: str
    statistical_complexity: str
    risk_factors: List[str]
    quality_indicators: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class StudyCardProcessor:
    """Comprehensive study card processing and enrichment."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the study card processor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.auto_enrich = self.config.get("auto_enrich", True)
        self.quality_checks = self.config.get("quality_checks", True)
        self.normalize_data = self.config.get("normalize_data", True)
        self.extract_metadata = self.config.get("extract_metadata", True)
        
        # Sponsor experience mapping
        self.experienced_sponsors = {
            "merck", "pfizer", "novartis", "roche", "astrazeneca", "johnson & johnson",
            "abbvie", "gilead", "amgen", "eli lilly", "glaxosmithkline", "sanofi",
            "biogen", "regeneron", "bristol-myers squibb", "moderna", "biontech"
        }
        
        # Indication categories
        self.indication_categories = {
            "oncology": ["cancer", "tumor", "neoplasm", "carcinoma", "leukemia", "lymphoma"],
            "cardiovascular": ["cardio", "heart", "vascular", "stroke", "myocardial"],
            "neurology": ["neuro", "brain", "spinal", "cerebral", "cognitive"],
            "immunology": ["immune", "autoimmune", "inflammation", "rheumatoid"],
            "rare_disease": ["rare", "orphan", "genetic", "inherited"],
            "dermatology": ["skin", "dermat", "psoriasis", "eczema"],
            "respiratory": ["lung", "respiratory", "asthma", "copd"],
            "metabolic": ["diabetes", "obesity", "metabolic", "endocrine"]
        }
        
        # Phase categories
        self.phase_categories = {
            "early_development": ["phase_1", "phase_1b", "phase_2a"],
            "proof_of_concept": ["phase_2", "phase_2b"],
            "confirmatory": ["phase_3", "pivotal"],
            "post_approval": ["phase_4", "post_marketing"]
        }
    
    def process_study_card(self, 
                          study_card: Dict[str, Any],
                          trial_metadata: Optional[Dict[str, Any]] = None,
                          run_id: Optional[str] = None) -> ProcessingResult:
        """
        Process and enrich a study card.
        
        Args:
            study_card: Raw study card data
            trial_metadata: Additional trial metadata
            run_id: Run identifier for tracking
            
        Returns:
            ProcessingResult with processed data
        """
        start_time = datetime.now()
        
        try:
            # Validate input
            if not study_card:
                return ProcessingResult(
                    success=False,
                    error_message="Study card is empty or None"
                )
            
            # Normalize data if enabled
            if self.normalize_data:
                study_card = self._normalize_study_card(study_card)
            
            # Validate study card
            validation_errors = []
            if self.quality_checks:
                validation_errors = self._validate_study_card(study_card)
            
            # Extract metadata
            extracted_metadata = {}
            if self.extract_metadata:
                extracted_metadata = self._extract_trial_metadata(study_card, trial_metadata)
            
            # Enrich data
            enrichment_data = None
            if self.auto_enrich:
                enrichment_data = self._enrich_study_card(study_card, extracted_metadata)
            
            # Apply enrichments to study card
            processed_study_card = study_card.copy()
            if enrichment_data:
                processed_study_card["enrichment"] = asdict(enrichment_data)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            self.logger.info(f"Successfully processed study card: {extracted_metadata.get('trial_id', 'unknown')}")
            
            return ProcessingResult(
                success=True,
                processed_study_card=processed_study_card,
                extracted_metadata=extracted_metadata,
                validation_errors=validation_errors,
                enrichment_data=enrichment_data,
                processing_time=processing_time,
                metadata={
                    "run_id": run_id,
                    "processing_config": {
                        "auto_enrich": self.auto_enrich,
                        "quality_checks": self.quality_checks,
                        "normalize_data": self.normalize_data,
                        "extract_metadata": self.extract_metadata
                    }
                }
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            self.logger.error(f"Study card processing failed: {e}")
            
            return ProcessingResult(
                success=False,
                error_message=str(e),
                processing_time=processing_time
            )
    
    def extract_trial_metadata(self, 
                              study_card: Dict[str, Any],
                              additional_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract comprehensive trial metadata from study card.
        
        Args:
            study_card: Study card data
            additional_metadata: Additional metadata to merge
            
        Returns:
            Extracted metadata dictionary
        """
        metadata = {
            "trial_id": study_card.get("study_id"),
            "is_pivotal": study_card.get("is_pivotal", False),
            "indication": study_card.get("indication", "unknown"),
            "phase": study_card.get("phase", "unknown"),
            "sponsor": study_card.get("sponsor", "unknown"),
            "drug_name": study_card.get("drug_name", "unknown"),
            "primary_endpoint_type": study_card.get("primary_type", "unknown"),
            "extracted_at": datetime.now().isoformat(),
            "source": "study_card_processing"
        }
        
        # Extract sample size information
        if "arms" in study_card:
            arms = study_card["arms"]
            if isinstance(arms, dict):
                total_sample_size = 0
                arm_details = {}
                
                for arm_key, arm_data in arms.items():
                    if isinstance(arm_data, dict) and "n" in arm_data:
                        arm_size = arm_data.get("n", 0)
                        total_sample_size += arm_size
                        arm_details[arm_key] = {
                            "sample_size": arm_size,
                            "dropout_rate": arm_data.get("dropout", 0.0)
                        }
                
                metadata["total_sample_size"] = total_sample_size
                metadata["arm_details"] = arm_details
                metadata["arm_count"] = len(arms)
        
        # Extract analysis plan information
        if "analysis_plan" in study_card:
            plan = study_card["analysis_plan"]
            if isinstance(plan, dict):
                metadata["analysis_plan"] = {
                    "alpha": plan.get("alpha"),
                    "one_sided": plan.get("one_sided", False),
                    "planned_interims": plan.get("planned_interims", 0),
                    "alpha_spending": plan.get("alpha_spending"),
                    "assumed_p_c": plan.get("assumed_p_c"),
                    "assumed_delta_abs": plan.get("assumed_delta_abs")
                }
        
        # Extract primary result information
        if "primary_result" in study_card:
            result = study_card["primary_result"]
            if isinstance(result, dict):
                metadata["primary_result"] = {}
                
                for analysis_type, analysis_data in result.items():
                    if isinstance(analysis_data, dict):
                        metadata["primary_result"][analysis_type] = {
                            "p_value": analysis_data.get("p"),
                            "estimate": analysis_data.get("estimate"),
                            "ci_lower": analysis_data.get("ci_lower"),
                            "ci_upper": analysis_data.get("ci_upper")
                        }
        
        # Extract subgroup information
        if "subgroups" in study_card:
            subgroups = study_card["subgroups"]
            if isinstance(subgroups, list):
                metadata["subgroup_count"] = len(subgroups)
                metadata["subgroup_types"] = []
                
                for subgroup in subgroups:
                    if isinstance(subgroup, dict):
                        subgroup_type = subgroup.get("name", "unknown")
                        metadata["subgroup_types"].append(subgroup_type)
        
        # Add additional metadata if provided
        if additional_metadata:
            metadata.update(additional_metadata)
        
        return metadata
    
    def validate_study_card(self, study_card: Dict[str, Any]) -> List[str]:
        """
        Validate study card data quality.
        
        Args:
            study_card: Study card data to validate
            
        Returns:
            List of validation error messages
        """
        return self._validate_study_card(study_card)
    
    def _normalize_study_card(self, study_card: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize study card data for consistency."""
        normalized = study_card.copy()
        
        # Normalize string fields
        string_fields = ["study_id", "indication", "phase", "sponsor", "drug_name", "primary_type"]
        for field in string_fields:
            if field in normalized and normalized[field]:
                if isinstance(normalized[field], str):
                    normalized[field] = normalized[field].strip().lower()
        
        # Normalize boolean fields
        boolean_fields = ["is_pivotal", "single_arm"]
        for field in boolean_fields:
            if field in normalized:
                if isinstance(normalized[field], str):
                    normalized[field] = normalized[field].lower() in ["true", "1", "yes", "on"]
                elif isinstance(normalized[field], int):
                    normalized[field] = bool(normalized[field])
        
        # Normalize numeric fields
        numeric_fields = ["sample_size"]
        for field in numeric_fields:
            if field in normalized and normalized[field]:
                try:
                    normalized[field] = int(float(normalized[field]))
                except (ValueError, TypeError):
                    normalized[field] = None
        
        # Normalize arms data
        if "arms" in normalized and isinstance(normalized["arms"], dict):
            for arm_key, arm_data in normalized["arms"].items():
                if isinstance(arm_data, dict):
                    # Normalize sample size
                    if "n" in arm_data:
                        try:
                            arm_data["n"] = int(float(arm_data["n"]))
                        except (ValueError, TypeError):
                            arm_data["n"] = None
                    
                    # Normalize dropout rate
                    if "dropout" in arm_data:
                        try:
                            dropout = float(arm_data["dropout"])
                            arm_data["dropout"] = max(0.0, min(1.0, dropout))  # Clamp to [0, 1]
                        except (ValueError, TypeError):
                            arm_data["dropout"] = 0.0
        
        # Normalize analysis plan
        if "analysis_plan" in normalized and isinstance(normalized["analysis_plan"], dict):
            plan = normalized["analysis_plan"]
            
            # Normalize alpha
            if "alpha" in plan:
                try:
                    alpha = float(plan["alpha"])
                    plan["alpha"] = max(0.001, min(0.999, alpha))  # Clamp to (0, 1)
                except (ValueError, TypeError):
                    plan["alpha"] = 0.05
            
            # Normalize planned interims
            if "planned_interims" in plan:
                try:
                    plan["planned_interims"] = max(0, int(float(plan["planned_interims"])))
                except (ValueError, TypeError):
                    plan["planned_interims"] = 0
        
        # Normalize primary result
        if "primary_result" in normalized and isinstance(normalized["primary_result"], dict):
            for analysis_type, analysis_data in normalized["primary_result"].items():
                if isinstance(analysis_data, dict):
                    # Normalize p-value
                    if "p" in analysis_data:
                        try:
                            p_val = float(analysis_data["p"])
                            analysis_data["p"] = max(0.0, min(1.0, p_val))  # Clamp to [0, 1]
                        except (ValueError, TypeError):
                            analysis_data["p"] = None
                    
                    # Normalize estimate
                    if "estimate" in analysis_data:
                        try:
                            analysis_data["estimate"] = float(analysis_data["estimate"])
                        except (ValueError, TypeError):
                            analysis_data["estimate"] = None
        
        return normalized
    
    def _validate_study_card(self, study_card: Dict[str, Any]) -> List[str]:
        """Validate study card data quality."""
        errors = []
        
        # Required fields validation
        required_fields = ["study_id", "is_pivotal", "primary_type"]
        for field in required_fields:
            if field not in study_card or study_card[field] is None:
                errors.append(f"Missing required field: {field}")
        
        # Study ID validation
        if "study_id" in study_card and study_card["study_id"]:
            study_id = str(study_card["study_id"])
            if len(study_id.strip()) == 0:
                errors.append("Study ID cannot be empty")
            elif len(study_id) > 100:
                errors.append("Study ID too long (max 100 characters)")
        
        # Arms validation
        if "arms" in study_card:
            arms = study_card["arms"]
            if not isinstance(arms, dict):
                errors.append("Arms must be a dictionary")
            else:
                if not arms:
                    errors.append("Arms dictionary cannot be empty")
                else:
                    for arm_key, arm_data in arms.items():
                        if not isinstance(arm_data, dict):
                            errors.append(f"Arm {arm_key} must be a dictionary")
                        elif "n" not in arm_data:
                            errors.append(f"Arm {arm_key} missing sample size (n)")
                        elif arm_data["n"] is not None:
                            try:
                                sample_size = int(arm_data["n"])
                                if sample_size <= 0:
                                    errors.append(f"Arm {arm_key} sample size must be positive")
                                elif sample_size > 100000:
                                    errors.append(f"Arm {arm_key} sample size too large (max 100,000)")
                            except (ValueError, TypeError):
                                errors.append(f"Arm {arm_key} sample size must be a valid integer")
        
        # Analysis plan validation
        if "analysis_plan" in study_card:
            plan = study_card["analysis_plan"]
            if not isinstance(plan, dict):
                errors.append("Analysis plan must be a dictionary")
            else:
                if "alpha" in plan and plan["alpha"] is not None:
                    try:
                        alpha = float(plan["alpha"])
                        if alpha <= 0 or alpha >= 1:
                            errors.append("Alpha must be between 0 and 1")
                    except (ValueError, TypeError):
                        errors.append("Alpha must be a valid number")
                
                if "planned_interims" in plan and plan["planned_interims"] is not None:
                    try:
                        interims = int(plan["planned_interims"])
                        if interims < 0:
                            errors.append("Planned interims cannot be negative")
                        if interims > 10:
                            errors.append("Planned interims too high (max 10)")
                    except (ValueError, TypeError):
                        errors.append("Planned interims must be a valid integer")
        
        # Primary result validation
        if "primary_result" in study_card:
            result = study_card["primary_result"]
            if not isinstance(result, dict):
                errors.append("Primary result must be a dictionary")
            else:
                for analysis_type, analysis_data in result.items():
                    if not isinstance(analysis_data, dict):
                        errors.append(f"Primary result {analysis_type} must be a dictionary")
                    else:
                        if "p" in analysis_data and analysis_data["p"] is not None:
                            try:
                                p_val = float(analysis_data["p"])
                                if p_val < 0 or p_val > 1:
                                    errors.append(f"P-value in {analysis_type} must be between 0 and 1")
                            except (ValueError, TypeError):
                                errors.append(f"P-value in {analysis_type} must be a valid number")
        
        # Subgroups validation
        if "subgroups" in study_card:
            subgroups = study_card["subgroups"]
            if not isinstance(subgroups, list):
                errors.append("Subgroups must be a list")
            else:
                for i, subgroup in enumerate(subgroups):
                    if not isinstance(subgroup, dict):
                        errors.append(f"Subgroup {i} must be a dictionary")
                    elif "name" not in subgroup:
                        errors.append(f"Subgroup {i} missing name")
                    elif "n" not in subgroup:
                        errors.append(f"Subgroup {i} missing sample size")
        
        return errors
    
    def _enrich_study_card(self, 
                           study_card: Dict[str, Any],
                           metadata: Dict[str, Any]) -> EnrichmentData:
        """Enrich study card with additional derived information."""
        
        # Determine sponsor experience
        sponsor = metadata.get("sponsor", "").lower()
        sponsor_experience = "experienced" if sponsor in self.experienced_sponsors else "novice"
        
        # Categorize indication
        indication = metadata.get("indication", "").lower()
        indication_category = "other"
        for category, keywords in self.indication_categories.items():
            if any(keyword in indication for keyword in keywords):
                indication_category = category
                break
        
        # Categorize phase
        phase = metadata.get("phase", "").lower()
        phase_category = "unknown"
        for category, phases in self.phase_categories.items():
            if phase in phases:
                phase_category = category
                break
        
        # Assess endpoint complexity
        endpoint_complexity = "simple"
        if "subgroups" in study_card and len(study_card["subgroups"]) > 3:
            endpoint_complexity = "complex"
        elif "primary_result" in study_card and len(study_card["primary_result"]) > 2:
            endpoint_complexity = "moderate"
        
        # Assess statistical complexity
        statistical_complexity = "simple"
        plan = study_card.get("analysis_plan", {})
        if plan.get("planned_interims", 0) > 2:
            statistical_complexity = "complex"
        elif plan.get("planned_interims", 0) > 0:
            statistical_complexity = "moderate"
        
        # Identify risk factors
        risk_factors = []
        
        # Sample size risk
        total_sample_size = metadata.get("total_sample_size", 0)
        if total_sample_size < 100:
            risk_factors.append("small_sample_size")
        elif total_sample_size > 10000:
            risk_factors.append("very_large_sample_size")
        
        # Interim analysis risk
        if plan.get("planned_interims", 0) > 3:
            risk_factors.append("multiple_interim_analyses")
        
        # Subgroup risk
        if metadata.get("subgroup_count", 0) > 5:
            risk_factors.append("many_subgroups")
        
        # Endpoint change risk
        if study_card.get("endpoint_changed_after_lpr", False):
            risk_factors.append("endpoint_changed_after_lpr")
        
        # Quality indicators
        quality_indicators = {
            "has_sample_size": total_sample_size > 0,
            "has_analysis_plan": bool(plan),
            "has_primary_result": bool(study_card.get("primary_result")),
            "has_subgroups": bool(study_card.get("subgroups")),
            "completeness_score": self._calculate_completeness_score(study_card),
            "data_quality_score": self._calculate_data_quality_score(study_card)
        }
        
        return EnrichmentData(
            sponsor_experience=sponsor_experience,
            indication_category=indication_category,
            phase_category=phase_category,
            endpoint_complexity=endpoint_complexity,
            statistical_complexity=statistical_complexity,
            risk_factors=risk_factors,
            quality_indicators=quality_indicators,
            metadata={
                "enrichment_timestamp": datetime.now().isoformat(),
                "enrichment_version": "1.0"
            }
        )
    
    def _calculate_completeness_score(self, study_card: Dict[str, Any]) -> float:
        """Calculate completeness score for study card."""
        required_fields = [
            "study_id", "is_pivotal", "primary_type", "arms", "analysis_plan"
        ]
        
        optional_fields = [
            "primary_result", "subgroups", "inclusion_criteria", "exclusion_criteria",
            "secondary_endpoints", "safety_endpoints"
        ]
        
        required_score = sum(1 for field in required_fields if field in study_card and study_card[field]) / len(required_fields)
        optional_score = sum(1 for field in optional_fields if field in study_card and study_card[field]) / len(optional_fields)
        
        # Weight required fields more heavily
        return 0.7 * required_score + 0.3 * optional_score
    
    def _calculate_data_quality_score(self, study_card: Dict[str, Any]) -> float:
        """Calculate data quality score for study card."""
        quality_score = 1.0
        
        # Check for data type consistency
        if "arms" in study_card and isinstance(study_card["arms"], dict):
            for arm_data in study_card["arms"].values():
                if isinstance(arm_data, dict):
                    if "n" in arm_data and not isinstance(arm_data["n"], (int, float)):
                        quality_score -= 0.1
                    if "dropout" in arm_data and not isinstance(arm_data["dropout"], (int, float)):
                        quality_score -= 0.1
        
        # Check for valid numeric ranges
        if "analysis_plan" in study_card and isinstance(study_card["analysis_plan"], dict):
            plan = study_card["analysis_plan"]
            if "alpha" in plan:
                try:
                    alpha = float(plan["alpha"])
                    if alpha <= 0 or alpha >= 1:
                        quality_score -= 0.2
                except (ValueError, TypeError):
                    quality_score -= 0.2
        
        # Check for logical consistency
        if "primary_result" in study_card and isinstance(study_card["primary_result"], dict):
            for analysis_data in study_card["primary_result"].values():
                if isinstance(analysis_data, dict):
                    if "p" in analysis_data:
                        try:
                            p_val = float(analysis_data["p"])
                            if p_val < 0 or p_val > 1:
                                quality_score -= 0.2
                        except (ValueError, TypeError):
                            quality_score -= 0.2
        
        return max(0.0, quality_score)


# Convenience functions
def process_study_card(study_card: Dict[str, Any],
                      trial_metadata: Optional[Dict[str, Any]] = None,
                      run_id: Optional[str] = None) -> ProcessingResult:
    """Process a study card."""
    processor = StudyCardProcessor()
    return processor.process_study_card(study_card, trial_metadata, run_id)


def extract_trial_metadata(study_card: Dict[str, Any],
                          additional_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extract trial metadata from study card."""
    processor = StudyCardProcessor()
    return processor.extract_trial_metadata(study_card, additional_metadata)


def validate_study_card(study_card: Dict[str, Any]) -> List[str]:
    """Validate study card data."""
    processor = StudyCardProcessor()
    return processor.validate_study_card(study_card)
