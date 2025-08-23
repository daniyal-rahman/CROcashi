"""
LangExtract integration for SEC filings using Google Gemini.

This module provides robust narrative parsing with:
- Strict schema validation
- Evidence span tracking
- Hallucination prevention
- Fallback strategies
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass

import google.generativeai as genai
from pydantic import BaseModel, ValidationError, Field

from .sec_types import (
    EightKItem, TenKSection, DocumentSection, 
    ExtractionResult, SecIngestionResult
)

logger = logging.getLogger(__name__)


class TrialEventSchema(BaseModel):
    """Schema for trial event extraction from 8-K filings."""
    
    # Trial identification
    trial_identifier: Optional[str] = Field(None, description="NCT ID or trial name if mentioned")
    trial_phase: Optional[str] = Field(None, description="Trial phase if mentioned")
    
    # Event details
    event_type: str = Field(..., description="Type of trial event (e.g., 'endpoint_met', 'safety_signal', 'program_discontinuation')")
    event_description: str = Field(..., description="Detailed description of the event")
    
    # Clinical details
    primary_endpoint_outcome: Optional[str] = Field(None, description="Primary endpoint result if applicable")
    safety_events: List[str] = Field(default_factory=list, description="List of safety events mentioned")
    enrollment_impact: Optional[str] = Field(None, description="Impact on enrollment if mentioned")
    
    # Evidence tracking
    evidence_spans: List[Dict[str, Any]] = Field(default_factory=list, description="Evidence spans with start/end positions and quotes")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    
    # Validation
    is_verbatim: bool = Field(False, description="Whether this information is directly stated in the text")
    requires_review: bool = Field(False, description="Whether this extraction requires human review")


class ClinicalDevelopmentSchema(BaseModel):
    """Schema for clinical development information from 10-K filings."""
    
    # Pipeline information
    pipeline_stage: Optional[str] = Field(None, description="Current pipeline stage")
    pivotal_status: Optional[str] = Field(None, description="Whether trial is pivotal")
    enrollment_target: Optional[str] = Field(None, description="Enrollment target if mentioned")
    enrollment_current: Optional[str] = Field(None, description="Current enrollment if mentioned")
    
    # Regulatory information
    fda_interactions: List[str] = Field(default_factory=list, description="FDA interactions mentioned")
    regulatory_milestones: List[str] = Field(default_factory=list, description="Regulatory milestones")
    
    # Clinical details
    primary_endpoints: List[str] = Field(default_factory=list, description="Primary endpoints mentioned")
    secondary_endpoints: List[str] = Field(default_factory=list, description="Secondary endpoints mentioned")
    
    # Evidence tracking
    evidence_spans: List[Dict[str, Any]] = Field(default_factory=list, description="Evidence spans with start/end positions and quotes")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    
    # Validation
    is_verbatim: bool = Field(False, description="Whether this information is directly stated in the text")
    requires_review: bool = Field(False, description="Whether this extraction requires human review")


class SecLangExtractor:
    """
    LangExtract integration for SEC filings using Google Gemini.
    
    Features:
    - Strict schema validation
    - Evidence span tracking
    - Hallucination prevention
    - Multiple extraction strategies
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the LangExtract extractor.
        
        Args:
            config: Configuration with Gemini API key and settings
        """
        self.config = config
        self.api_key = config.get('gemini_api_key')
        self.model_name = config.get('model_name', 'gemini-1.5-pro')
        self.max_retries = config.get('max_retries', 3)
        self.temperature = config.get('temperature', 0.1)  # Low temperature for consistency
        
        # Initialize Gemini
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
        else:
            logger.warning("No Gemini API key provided, LangExtract will be disabled")
            self.model = None
    
    def extract_trial_events_from_8k(
        self, 
        section: DocumentSection,
        filing_metadata: Dict[str, Any]
    ) -> Optional[EightKItem]:
        """
        Extract trial events from 8-K section using LangExtract.
        
        Args:
            section: Document section to analyze
            filing_metadata: Filing metadata for context
            
        Returns:
            Extracted 8-K item or None if extraction failed
        """
        if not self.model:
            logger.warning("LangExtract disabled, skipping extraction")
            return None
        
        try:
            # Build prompt with strict constraints
            prompt = self._build_8k_prompt(section, filing_metadata)
            
            # Extract with validation
            extraction_result = self._extract_with_validation(
                prompt, 
                TrialEventSchema,
                max_retries=self.max_retries
            )
            
            if not extraction_result:
                return None
            
            # Convert to EightKItem
            item = EightKItem(
                item_number=section.item_number or "unknown",
                title=section.title,
                content=section.content,
                content_hash=section.content_hash,
                trial_events=[extraction_result.event_description] if extraction_result.event_description else [],
                endpoints_mentioned=[extraction_result.primary_endpoint_outcome] if extraction_result.primary_endpoint_outcome else [],
                safety_signals=extraction_result.safety_events,
                program_changes=[extraction_result.event_description] if "discontinuation" in extraction_result.event_type.lower() else [],
                extracted_at=datetime.utcnow(),
                extraction_method="langextract_gemini",
                confidence=extraction_result.confidence,
                evidence_spans=extraction_result.evidence_spans
            )
            
            return item
            
        except Exception as e:
            logger.error(f"Error extracting trial events from 8-K: {e}")
            return None
    
    def extract_clinical_development_from_10k(
        self, 
        section: DocumentSection,
        filing_metadata: Dict[str, Any]
    ) -> Optional[TenKSection]:
        """
        Extract clinical development information from 10-K section.
        
        Args:
            section: Document section to analyze
            filing_metadata: Filing metadata for context
            
        Returns:
            Extracted 10-K section or None if extraction failed
        """
        if not self.model:
            logger.warning("LangExtract disabled, skipping extraction")
            return None
        
        try:
            # Build prompt with strict constraints
            prompt = self._build_10k_prompt(section, filing_metadata)
            
            # Extract with validation
            extraction_result = self._extract_with_validation(
                prompt, 
                ClinicalDevelopmentSchema,
                max_retries=self.max_retries
            )
            
            if not extraction_result:
                return None
            
            # Convert to TenKSection
            tenk_section = TenKSection(
                section_name=section.title,
                content=section.content,
                content_hash=section.content_hash,
                clinical_development=[extraction_result.pipeline_stage] if extraction_result.pipeline_stage else [],
                regulatory_updates=extraction_result.fda_interactions + extraction_result.regulatory_milestones,
                pipeline_changes=[extraction_result.pipeline_stage] if extraction_result.pipeline_stage else [],
                risk_factors=[],  # Not extracted in this schema
                extracted_at=datetime.utcnow(),
                extraction_method="langextract_gemini",
                confidence=extraction_result.confidence,
                evidence_spans=extraction_result.evidence_spans
            )
            
            return tenk_section
            
        except Exception as e:
            logger.error(f"Error extracting clinical development from 10-K: {e}")
            return None
    
    def _build_8k_prompt(self, section: DocumentSection, filing_metadata: Dict[str, Any]) -> str:
        """Build prompt for 8-K trial event extraction."""
        company_name = filing_metadata.get('company_name', 'Unknown Company')
        filing_date = filing_metadata.get('filing_date', 'Unknown Date')
        
        prompt = f"""
You are analyzing an SEC 8-K filing for {company_name} filed on {filing_date}.

TASK: Extract trial-related information from the following text. ONLY extract information that is EXPLICITLY stated in the text. If information is not present, use null.

IMPORTANT CONSTRAINTS:
1. ONLY extract VERBATIM information from the text
2. If something is not explicitly stated, output null
3. Do not infer, assume, or guess any information
4. Provide evidence spans (start/end positions) for every non-null field
5. Confidence should be 1.0 for verbatim text, lower for inferred information

TEXT TO ANALYZE:
{section.content}

EXTRACTION SCHEMA:
{{
    "trial_identifier": "NCT ID or trial name if explicitly mentioned, otherwise null",
    "trial_phase": "Trial phase if explicitly mentioned, otherwise null",
    "event_type": "Type of trial event (endpoint_met, safety_signal, program_discontinuation, enrollment_update, etc.)",
    "event_description": "Detailed description of the event as stated in the text",
    "primary_endpoint_outcome": "Primary endpoint result if explicitly mentioned, otherwise null",
    "safety_events": ["List of safety events explicitly mentioned"],
    "enrollment_impact": "Impact on enrollment if explicitly mentioned, otherwise null",
    "evidence_spans": [
        {{
            "field": "field_name",
            "start": start_position,
            "end": end_position,
            "quote": "exact quote from text"
        }}
    ],
    "confidence": confidence_score_0_to_1,
    "is_verbatim": true_if_all_information_is_directly_stated,
    "requires_review": false_unless_low_confidence_or_validation_issues
}}

Remember: ONLY extract what is explicitly stated. If in doubt, use null.
"""
        return prompt
    
    def _build_10k_prompt(self, section: DocumentSection, filing_metadata: Dict[str, Any]) -> str:
        """Build prompt for 10-K clinical development extraction."""
        company_name = filing_metadata.get('company_name', 'Unknown Company')
        filing_date = filing_metadata.get('filing_date', 'Unknown Date')
        
        prompt = f"""
You are analyzing an SEC 10-K filing for {company_name} filed on {filing_date}.

TASK: Extract clinical development information from the following text. ONLY extract information that is EXPLICITLY stated in the text. If information is not present, use null.

IMPORTANT CONSTRAINTS:
1. ONLY extract VERBATIM information from the text
2. If something is not explicitly stated, output null
3. Do not infer, assume, or guess any information
4. Provide evidence spans (start/end positions) for every non-null field
5. Confidence should be 1.0 for verbatim text, lower for inferred information

TEXT TO ANALYZE:
{section.content}

EXTRACTION SCHEMA:
{{
    "pipeline_stage": "Current pipeline stage if explicitly mentioned, otherwise null",
    "pivotal_status": "Whether trial is pivotal if explicitly mentioned, otherwise null",
    "enrollment_target": "Enrollment target if explicitly mentioned, otherwise null",
    "enrollment_current": "Current enrollment if explicitly mentioned, otherwise null",
    "fda_interactions": ["List of FDA interactions explicitly mentioned"],
    "regulatory_milestones": ["List of regulatory milestones explicitly mentioned"],
    "primary_endpoints": ["List of primary endpoints explicitly mentioned"],
    "secondary_endpoints": ["List of secondary endpoints explicitly mentioned"],
    "evidence_spans": [
        {{
            "field": "field_name",
            "start": start_position,
            "end": end_position,
            "quote": "exact quote from text"
        }}
    ],
    "confidence": confidence_score_0_to_1,
    "is_verbatim": true_if_all_information_is_directly_stated,
    "requires_review": false_unless_low_confidence_or_validation_issues
}}

Remember: ONLY extract what is explicitly stated. If in doubt, use null.
"""
        return prompt
    
    def _extract_with_validation(
        self, 
        prompt: str, 
        schema_class: type,
        max_retries: int = 3
    ) -> Optional[Any]:
        """
        Extract information with schema validation and retry logic.
        
        Args:
            prompt: Extraction prompt
            schema_class: Pydantic schema class for validation
            max_retries: Maximum number of retry attempts
            
        Returns:
            Validated extraction result or None if failed
        """
        for attempt in range(max_retries):
            try:
                # Generate response from Gemini
                response = self.model.generate_content(prompt)
                
                if not response.text:
                    logger.warning(f"Empty response from Gemini (attempt {attempt + 1})")
                    continue
                
                # Extract JSON from response
                json_text = self._extract_json_from_response(response.text)
                if not json_text:
                    logger.warning(f"No JSON found in response (attempt {attempt + 1})")
                    continue
                
                # Parse and validate JSON
                data = json.loads(json_text)
                
                # Validate against schema
                validated_result = schema_class(**data)
                
                # Additional validation checks
                if self._validate_extraction_result(validated_result):
                    logger.info(f"Successful extraction on attempt {attempt + 1}")
                    return validated_result
                else:
                    logger.warning(f"Validation failed on attempt {attempt + 1}")
                    continue
                    
            except ValidationError as e:
                logger.warning(f"Schema validation failed on attempt {attempt + 1}: {e}")
                continue
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parsing failed on attempt {attempt + 1}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Extraction failed on attempt {attempt + 1}: {e}")
                continue
        
        logger.error(f"All {max_retries} extraction attempts failed")
        return None
    
    def _extract_json_from_response(self, response_text: str) -> Optional[str]:
        """Extract JSON from Gemini response text."""
        # Look for JSON blocks
        json_patterns = [
            r'```json\s*(.*?)\s*```',  # Markdown JSON blocks
            r'```\s*(.*?)\s*```',       # Generic code blocks
            r'\{.*\}',                  # JSON object
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, response_text, re.DOTALL)
            if matches:
                return matches[0].strip()
        
        return None
    
    def _validate_extraction_result(self, result: Any) -> bool:
        """Additional validation beyond schema validation."""
        try:
            # Check that evidence spans exist for non-null fields
            if hasattr(result, 'evidence_spans'):
                non_null_fields = []
                for field_name, field_value in result.dict().items():
                    if field_value and field_name not in ['evidence_spans', 'confidence', 'is_verbatim', 'requires_review']:
                        non_null_fields.append(field_name)
                
                # Check that evidence spans exist for non-null fields
                if non_null_fields and not result.evidence_spans:
                    logger.warning("Non-null fields found but no evidence spans provided")
                    return False
            
            # Check confidence score
            if hasattr(result, 'confidence'):
                if result.confidence < 0.5:
                    logger.warning(f"Low confidence score: {result.confidence}")
                    result.requires_review = True
            
            # Check verbatim flag
            if hasattr(result, 'is_verbatim'):
                if not result.is_verbatim and result.confidence > 0.8:
                    logger.warning("High confidence but not marked as verbatim")
                    result.requires_review = True
            
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    def batch_extract(
        self, 
        sections: List[DocumentSection], 
        filing_metadata: Dict[str, Any],
        form_type: str
    ) -> ExtractionResult:
        """
        Batch extract information from multiple sections.
        
        Args:
            sections: List of document sections
            filing_metadata: Filing metadata
            form_type: SEC form type
            
        Returns:
            Extraction result with all extracted items
        """
        start_time = datetime.utcnow()
        extracted_items = []
        errors = []
        warnings = []
        
        for section in sections:
            try:
                if form_type == '8-K':
                    item = self.extract_trial_events_from_8k(section, filing_metadata)
                    if item:
                        extracted_items.append(item)
                elif form_type in ['10-K', '10-Q']:
                    item = self.extract_clinical_development_from_10k(section, filing_metadata)
                    if item:
                        extracted_items.append(item)
                        
            except Exception as e:
                error_msg = f"Error extracting from section '{section.title}': {e}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Create extraction result
        result = ExtractionResult(
            filing_id=f"{filing_metadata.get('cik')}_{filing_metadata.get('accession')}",
            extraction_type=f"{form_type.lower()}_extraction",
            extracted_items=extracted_items,
            processing_time_seconds=processing_time,
            extraction_errors=errors,
            extraction_warnings=warnings
        )
        
        # Validate overall result
        result.validation_passed = len(errors) == 0 and len(extracted_items) > 0
        
        return result
