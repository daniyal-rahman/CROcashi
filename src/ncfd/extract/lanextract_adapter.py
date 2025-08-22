"""
LangExtract adapter for Gemini integration with Study Card extraction.

This module provides the interface between the document processing pipeline
and Gemini via LangExtract for extracting structured study information.
"""

from __future__ import annotations
import os
import json
import logging
from typing import Dict, Any, Optional, List
import langextract as lx
from langextract.data import ExampleData, Extraction
from pathlib import Path
from .validator import validate_card, validate_evidence_spans

logger = logging.getLogger(__name__)

# Custom exception for extraction errors
class ExtractionError(Exception):
    """Raised when extraction fails or returns invalid data."""
    pass

# Freeze model choice and environment variable
MODEL_ID = "gemini-1.5-pro"  # Single, stable model choice
ENV_VAR = "LANGEXTRACT_API_KEY_GEMINI"  # Clear, provider-specific naming

def load_prompts() -> str:
    """Load the study card prompts and embed the minified JSON schema."""
    prompts_file = Path(__file__).parent / "prompts" / "study_card_prompts.md"
    
    if not prompts_file.exists():
        raise FileNotFoundError(f"Prompts file not found: {prompts_file}")
    
    with open(prompts_file, 'r') as f:
        prompts = f.read()
    
    # Load and minify the JSON schema
    schema_file = Path(__file__).parent / "study_card.schema.json"
    with open(schema_file, 'r') as f:
        schema = json.load(f)
    
    # Embed the minified schema in the prompts
    minified_schema = json.dumps(schema, separators=(',', ':'))
    prompts = prompts.replace("{{SCHEMA_JSON}}", minified_schema)
    
    return prompts

def build_payload(doc_meta: Dict[str, Any], chunks: List[Dict[str, Any]], trial_hint: Dict[str, Any]) -> Dict[str, Any]:
    """Build the payload for LangExtract processing."""
    return {
        "document_metadata": doc_meta,
        "text_chunks": chunks,
        "trial_context": trial_hint
    }

class StudyCardAdapter:
    """
    Thin, typed adapter for Study Card extraction via LangExtract.
    
    This adapter provides a stable interface with strict validation
    and fails hard on non-JSON or invalid data.
    """
    
    def __init__(self):
        """Initialize the adapter with prompts and validation."""
        self.prompts = load_prompts()
        
        # Verify API key is available
        api_key = os.getenv(ENV_VAR)
        if not api_key:
            raise ValueError(
                f"{ENV_VAR} environment variable not set. "
                f"Please set your Google Gemini API key for LangExtract."
            )
    
    def extract(self, text: str, prompt: str) -> Dict[str, Any]:
        """
        Extract Study Card data from text using LangExtract.
        
        Args:
            text: The text to extract from
            prompt: The extraction prompt
            
        Returns:
            Validated Study Card data as a dictionary
            
        Raises:
            ExtractionError: If extraction fails or returns invalid data
        """
        try:
            # Build example data for consistent extraction
            examples = [
                ExampleData(
                    text="Methods: Adults with COPD randomized 2:1 to Drug X vs placebo. Primary endpoint: Annualized exacerbation rate at Week 52 (ITT analysis). Results: n=660 (Drug X n=440; placebo n=220). Annualized exacerbation rate: 0.85 vs 1.23 (rate ratio 0.69, 95% CI 0.58-0.82, p<0.001).",
                    extractions=[
                        Extraction(
                            extraction_class="StudyCard",
                            extraction_text=json.dumps({
                                "doc": {"doc_type": "Abstract", "title": "Phase 3 Study of Drug X in COPD", "year": 2024, "url": "https://example.com", "source_id": "example_001"},
                                "trial": {"nct_id": "NCT12345678", "phase": "3", "indication": "COPD", "is_pivotal": True},
                                "primary_endpoints": [{"name": "Annualized exacerbation rate", "evidence": [{"loc": {"scheme": "page_paragraph", "page": 1, "paragraph": 1}}]}],
                                "populations": {"itt": {"defined": True, "evidence": [{"loc": {"scheme": "page_paragraph", "page": 1, "paragraph": 1}}]}, "pp": {"defined": False, "evidence": []}, "analysis_primary_on": "ITT"},
                                "arms": [{"label": "Drug X", "n": 440, "evidence": [{"loc": {"scheme": "page_paragraph", "page": 1, "paragraph": 2}}]}, {"label": "Placebo", "n": 220, "evidence": [{"loc": {"scheme": "page_paragraph", "page": 1, "paragraph": 2}}]}],
                                "sample_size": {"total_n": 660, "evidence": [{"loc": {"scheme": "page_paragraph", "page": 1, "paragraph": 2}}]},
                                "results": {"primary": [{"endpoint": "Annualized exacerbation rate", "effect_size": {"metric": "Rate Ratio", "value": 0.69, "ci_low": 0.58, "ci_high": 0.82, "ci_level": 95, "evidence": [{"loc": {"scheme": "page_paragraph", "page": 1, "paragraph": 2}}]}, "p_value": 0.001, "evidence": [{"loc": {"scheme": "page_paragraph", "page": 1, "paragraph": 2}}]}]},
                                "coverage_level": "high", "coverage_rationale": "All required fields present with evidence: primary endpoint, total N, ITT analysis, and effect size with p-value."
                            }),
                            attributes={}
                        )
                    ]
                )
            ]
            
            # Run extraction with single model choice
            result = lx.extract(
                text_or_documents=text,
                prompt_description=prompt,
                examples=examples,
                model_id=MODEL_ID
            )
            
            # Single, consistent result shape - fail hard if not found
            if not result or not hasattr(result, 'extractions') or not result.extractions:
                raise ExtractionError("No extractions returned from LangExtract")
            
            extraction = result.extractions[0]
            if not hasattr(extraction, 'extraction_text'):
                raise ExtractionError("Extraction missing extraction_text field")
            
            study_card_text = extraction.extraction_text
            if not study_card_text:
                raise ExtractionError("Extraction text is empty")
            
            # Single-pass JSON parse - no repairs, no fallbacks
            try:
                data = json.loads(study_card_text)
            except json.JSONDecodeError as e:
                raise ExtractionError(f"Invalid JSON returned: {e}")
            
            # Validate against schema
            try:
                validate_card(data, is_pivotal=data.get("trial", {}).get("is_pivotal", False))
            except Exception as e:
                raise ExtractionError(f"Schema validation failed: {e}")
            
            # Post-extract validation: every numeric field must have evidence
            evidence_issues = validate_evidence_spans(data)
            if evidence_issues:
                raise ExtractionError(f"Missing evidence spans: {', '.join(evidence_issues)}")
            
            return data
            
        except ExtractionError:
            # Re-raise our custom errors
            raise
        except Exception as e:
            # Wrap unexpected errors
            raise ExtractionError(f"Extraction failed: {e}") from e

def run_langextract(prompt_text: str, payload: Dict[str, Any], model_id: str = None) -> Dict[str, Any]:
    """
    Run LangExtract extraction using the StudyCardAdapter.
    
    Args:
        prompt_text: The system prompt and instructions
        payload: The document data to extract from
        model_id: Ignored - uses fixed MODEL_ID for consistency
        
    Returns:
        Parsed StudyCard data as a dictionary
        
    Raises:
        ExtractionError: If extraction fails
    """
    # Convert payload to text format for LangExtract
    input_text = json.dumps(payload, indent=2)
    
    # Use the adapter for consistent extraction
    adapter = StudyCardAdapter()
    return adapter.extract(input_text, prompt_text)

def _parse_study_card_text(study_card_text: str) -> Dict[str, Any]:
    """
    Parse StudyCard text using single-pass validation.
    
    This replaces the fragile multi-method JSON parsing with a robust
    single-pass approach that validates the structure as it parses.
    
    Args:
        study_card_text: The StudyCard text to parse
        
    Returns:
        Parsed StudyCard data as a dictionary
        
    Raises:
        ValueError: If the text cannot be parsed as valid StudyCard JSON
    """
    logger.info(f"Parsing StudyCard text: {study_card_text[:200]}...")
    
    # Single-pass parsing with validation
    try:
        # Attempt to parse the JSON
        parsed = json.loads(study_card_text)
        
        if not isinstance(parsed, dict):
            raise ValueError("StudyCard must be a JSON object")
        
        # Validate required top-level fields
        required_fields = ['doc', 'trial', 'primary_endpoints', 'populations', 'arms', 'results', 'coverage_level']
        missing_fields = [field for field in required_fields if field not in parsed]
        
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")
        
        # Validate document metadata
        doc = parsed.get('doc', {})
        if not isinstance(doc, dict):
            raise ValueError("'doc' field must be an object")
        
        doc_required = ['doc_type', 'title', 'year', 'url', 'source_id']
        doc_missing = [field for field in doc_required if field not in doc]
        if doc_missing:
            raise ValueError(f"Missing required doc fields: {doc_missing}")
        
        # Validate trial information
        trial = parsed.get('trial', {})
        if not isinstance(trial, dict):
            raise ValueError("'trial' field must be an object")
        
        trial_required = ['nct_id', 'phase', 'indication', 'is_pivotal']
        trial_missing = [field for field in trial_required if field not in trial]
        if trial_missing:
            raise ValueError(f"Missing required trial fields: {trial_missing}")
        
        # Validate primary endpoints
        primary_endpoints = parsed.get('primary_endpoints', [])
        if not isinstance(primary_endpoints, list) or len(primary_endpoints) == 0:
            raise ValueError("'primary_endpoints' must be a non-empty array")
        
        # Validate populations
        populations = parsed.get('populations', {})
        if not isinstance(populations, dict):
            raise ValueError("'populations' field must be an object")
        
        # Validate arms
        arms = parsed.get('arms', [])
        if not isinstance(arms, list) or len(arms) == 0:
            raise ValueError("'arms' must be a non-empty array")
        
        # Validate results
        results = parsed.get('results', {})
        if not isinstance(results, dict):
            raise ValueError("'results' field must be an object")
        
        # Validate coverage level
        coverage_level = parsed.get('coverage_level')
        if not isinstance(coverage_level, str) or coverage_level not in ['low', 'medium', 'high']:
            raise ValueError("'coverage_level' must be one of: low, medium, high")
        
        logger.info("Successfully parsed and validated StudyCard")
        return parsed
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {e}")
        logger.error(f"Text preview: {study_card_text[:500]}...")
        raise ValueError(f"Invalid JSON format: {e}")
        
    except ValueError as e:
        # Re-raise validation errors
        raise
        
    except Exception as e:
        logger.error(f"Unexpected error during parsing: {e}")
        logger.error(f"Text preview: {study_card_text[:500]}...")
        raise ValueError(f"Parsing failed: {e}")

def extract_study_card_from_document(
    document_text: str,
    document_metadata: Dict[str, Any],
    trial_context: Optional[Dict[str, Any]] = None,
    model_id: str = None
) -> Dict[str, Any]:
    """
    Extract a StudyCard from document text using LangExtract.
    
    This is the stable, thin adapter interface that provides comprehensive
    validation and error handling for StudyCard extraction.
    
    Args:
        document_text: The full document text
        document_metadata: Metadata about the document
        trial_context: Optional trial context information
        model_id: Ignored - uses fixed MODEL_ID for consistency
        
    Returns:
        Parsed StudyCard data as a dictionary
        
    Raises:
        ValueError: If input validation fails
        ExtractionError: If extraction fails
    """
    # Input validation
    if not document_text or not isinstance(document_text, str):
        raise ValueError("document_text must be a non-empty string")
    
    if not document_metadata or not isinstance(document_metadata, dict):
        raise ValueError("document_metadata must be a non-empty dictionary")
    
    # Validate required metadata fields
    required_metadata = ['doc_type', 'title', 'year', 'url', 'source_id']
    missing_metadata = [field for field in required_metadata if field not in document_metadata]
    if missing_metadata:
        raise ValueError(f"Missing required metadata fields: {missing_metadata}")
    
    # Validate trial context if provided
    if trial_context is not None:
        if not isinstance(trial_context, dict):
            raise ValueError("trial_context must be a dictionary or None")
        
        # Validate trial context fields if present
        if trial_context:
            trial_fields = ['nct_id', 'phase', 'indication']
            missing_trial = [field for field in trial_fields if field not in trial_context]
            if missing_trial:
                logger.warning(f"Missing trial context fields: {missing_trial}")
    
    try:
        # Load prompts
        from .prompts.study_card_prompts import load_prompts
        prompts = load_prompts()
        
        # Build payload with validation
        payload = {
            "document_metadata": document_metadata,
            "text_chunks": [
                {
                    "page": 1,
                    "paragraph": 1,
                    "text": document_text,
                    "start": 0,
                    "end": len(document_text)
                }
            ],
            "trial_context": trial_context or {}
        }
        
        # Validate payload structure
        if not payload["text_chunks"] or len(payload["text_chunks"]) == 0:
            raise ValueError("No text chunks provided for extraction")
        
        # Run extraction with error handling
        result = run_langextract(prompts, payload)
        
        # Validate result structure
        if not isinstance(result, dict):
            raise ExtractionError(f"Expected dictionary result, got {type(result)}")
        
        # Final validation of extracted data
        if not result:
            raise ExtractionError("Extraction returned empty result")
        
        return result
        
    except ImportError as e:
        raise ExtractionError(f"Failed to import required modules: {e}")
        
    except FileNotFoundError as e:
        raise ExtractionError(f"Required prompt files not found: {e}")
        
    except Exception as e:
        if isinstance(e, ExtractionError):
            raise
        logger.error(f"StudyCard extraction failed: {e}")
        raise ExtractionError(f"Extraction failed: {e}")

def create_text_chunks_from_pages(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert document pages to text chunks for LangExtract processing.
    
    Args:
        pages: List of page dictionaries with text and positioning
        
    Returns:
        List of text chunks with positioning information
    """
    chunks = []
    
    for page in pages:
        page_no = page.get('page_no', 1)
        text = page.get('text', '')
        
        if text.strip():
            # Split text into paragraphs for better processing
            paragraphs = text.split('\n\n')
            
            for i, paragraph in enumerate(paragraphs):
                if paragraph.strip():
                    chunk = {
                        'page': page_no,
                        'paragraph': i + 1,
                        'text': paragraph.strip(),
                        'start': len('\n\n'.join(paragraphs[:i])) if i > 0 else 0,
                        'end': len('\n\n'.join(paragraphs[:i+1]))
                    }
                    chunks.append(chunk)
    
    return chunks

def extract_study_card_from_document_pages(
    doc_meta: Dict[str, Any], 
    pages: List[Dict[str, Any]], 
    trial_hint: Dict[str, Any],
    model_id: str = None
) -> Dict[str, Any]:
    """
    Convenience function to extract study card directly from document pages.
    
    Args:
        doc_meta: Document metadata
        pages: List of page dictionaries
        trial_hint: Trial context
        model_id: Ignored - uses fixed MODEL_ID for consistency
        
    Returns:
        Validated study card dictionary
    """
    chunks = create_text_chunks_from_pages(pages)
    return extract_study_card_from_document(doc_meta, chunks, trial_hint)

# Legacy mock client for backward compatibility (can be removed in production)
class MockGeminiClient:
    """Legacy mock client - use real LangExtract instead."""
    
    def __init__(self):
        logger.warning("MockGeminiClient is deprecated. Use real LangExtract integration.")
    
    def generate_json(self, prompt: str) -> str:
        """Legacy method - raises warning."""
        logger.warning("MockGeminiClient.generate_json() called. Use extract_study_card_from_document() instead.")
        raise NotImplementedError("Use real LangExtract integration instead of mock client")
