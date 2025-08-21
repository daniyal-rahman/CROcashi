"""
LangExtract adapter for Gemini integration with Study Card extraction.

This module provides the interface between the document processing pipeline
and Gemini via LangExtract for extracting structured study information.
"""

from __future__ import annotations
import os
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from .validator import validate_card

logger = logging.getLogger(__name__)


class MockGeminiClient:
    """
    Mock Gemini client for testing and development.
    
    In production, this would be replaced with the actual Gemini client.
    """
    
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        self.model_name = model_name
        logger.info(f"Initialized mock Gemini client with model: {model_name}")
    
    def generate_json(self, prompt: str) -> str:
        """
        Mock JSON generation for testing.
        
        In production, this would call the actual Gemini API.
        """
        logger.info("Mock Gemini client called - returning sample response")
        
        # Return a sample study card for testing
        sample_card = {
            "doc": {
                "doc_type": "Abstract",
                "title": "Sample Study Results",
                "year": 2024,
                "url": "https://example.com/study",
                "source_id": "test_001"
            },
            "trial": {
                "nct_id": "NCT12345678",
                "phase": "3",
                "indication": "Sample Indication",
                "is_pivotal": True
            },
            "primary_endpoints": [
                {
                    "name": "Primary Endpoint",
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 1,
                                "paragraph": 1
                            }
                        }
                    ]
                }
            ],
            "populations": {
                "itt": {
                    "defined": True,
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 1,
                                "paragraph": 2
                            }
                        }
                    ]
                },
                "pp": {
                    "defined": False,
                    "evidence": []
                },
                "analysis_primary_on": "ITT"
            },
            "arms": [
                {
                    "label": "Treatment",
                    "n": 100,
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 1,
                                "paragraph": 3
                            }
                        }
                    ]
                },
                {
                    "label": "Control",
                    "n": 100,
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 1,
                                "paragraph": 3
                            }
                        }
                    ]
                }
            ],
            "sample_size": {
                "total_n": 200,
                "evidence": [
                    {
                        "loc": {
                            "scheme": "page_paragraph",
                            "page": 1,
                            "paragraph": 3
                        }
                    }
                ]
            },
            "results": {
                "primary": [
                    {
                        "endpoint": "Primary Endpoint",
                        "p_value": 0.05,
                        "evidence": [
                            {
                                "loc": {
                                    "scheme": "page_paragraph",
                                    "page": 1,
                                    "paragraph": 4
                                }
                            }
                        ]
                    }
                ]
            },
            "coverage_level": "high",
            "coverage_rationale": "All required fields present with evidence"
        }
        
        return json.dumps(sample_card, indent=2)


def load_prompts() -> str:
    """
    Load the study card prompts from the prompts file.
    
    Returns:
        Complete prompt text including system header and instructions
    """
    try:
        prompts_path = Path(__file__).parent / "prompts" / "study_card_prompts.md"
        with open(prompts_path, 'r') as f:
            prompts_text = f.read()
        
        # Load the schema
        schema_path = Path(__file__).parent / "study_card.schema.json"
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        
        # Replace the schema placeholder with actual schema
        prompts_text = prompts_text.replace("(embed the minified JSON Schema)", 
                                         f"```json\n{json.dumps(schema, separators=(',', ':'))}\n```")
        
        return prompts_text
        
    except Exception as e:
        logger.error(f"Failed to load prompts: {e}")
        raise


def build_payload(doc_meta: Dict[str, Any], chunks: List[Dict[str, Any]], trial_hint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the payload for LangExtract.
    
    Args:
        doc_meta: Document metadata (doc_type, title, year, url, source_id)
        chunks: List of text chunks with page/paragraph/offset information
        trial_hint: Trial information hints (nct_id, phase, indication)
        
    Returns:
        Formatted payload for LangExtract
    """
    return {
        "doc": doc_meta,
        "trial_hint": trial_hint,
        "chunks": chunks
    }


def run_langextract(client, prompt_text: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run LangExtract with Gemini to extract study card information.
    
    Args:
        client: Gemini client (or mock client for testing)
        prompt_text: Complete prompt including system header and schema
        payload: Input payload with document and trial information
        
    Returns:
        Validated Study Card dictionary
        
    Raises:
        ValueError: If the extracted card doesn't meet pivotal requirements
        json.JSONDecodeError: If Gemini returns invalid JSON
    """
    try:
        # Build the complete prompt
        full_prompt = prompt_text + "\n\nINPUT:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        
        # Call Gemini
        logger.info("Calling Gemini via LangExtract")
        response = client.generate_json(full_prompt)
        
        # Parse the response
        card = json.loads(response)
        logger.info("Successfully parsed Gemini response")
        
        # Validate the card
        is_pivotal = bool(card.get("trial", {}).get("is_pivotal", False))
        validate_card(card, is_pivotal=is_pivotal)
        
        logger.info(f"Study card validated successfully (pivotal: {is_pivotal})")
        return card
        
    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned invalid JSON: {e}")
        logger.error(f"Response: {response}")
        raise
    except ValueError as e:
        logger.error(f"Study card validation failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in LangExtract: {e}")
        raise


def extract_study_card_from_document(
    doc_meta: Dict[str, Any],
    text_chunks: List[Dict[str, Any]],
    trial_hint: Dict[str, Any],
    client=None
) -> Dict[str, Any]:
    """
    Extract a complete study card from document text.
    
    This is the main entry point for study card extraction.
    
    Args:
        doc_meta: Document metadata
        text_chunks: Text chunks with positioning information
        trial_hint: Trial hints for context
        client: Gemini client (uses mock if None)
        
    Returns:
        Complete, validated Study Card
    """
    if client is None:
        client = MockGeminiClient()
        logger.info("Using mock Gemini client for testing")
    
    try:
        # Load prompts
        prompt_text = load_prompts()
        logger.info("Loaded study card prompts")
        
        # Build payload
        payload = build_payload(doc_meta, text_chunks, trial_hint)
        logger.info(f"Built payload with {len(text_chunks)} chunks")
        
        # Extract study card
        card = run_langextract(client, prompt_text, payload)
        logger.info("Study card extraction completed successfully")
        
        return card
        
    except Exception as e:
        logger.error(f"Study card extraction failed: {e}")
        raise


def create_text_chunks_from_pages(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert document pages to text chunks for LangExtract.
    
    Args:
        pages: List of document pages with text content
        
    Returns:
        List of chunks with page/paragraph/offset information
    """
    chunks = []
    
    for page in pages:
        page_no = page.get("page_no", 1)
        text = page.get("text", "")
        
        # Simple paragraph splitting (in production, use more sophisticated NLP)
        paragraphs = text.split('\n\n')
        
        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():
                chunk = {
                    "page": page_no,
                    "paragraph": i + 1,
                    "start": 0,  # Simplified - in production, calculate actual offsets
                    "end": len(paragraph),
                    "text": paragraph.strip()
                }
                chunks.append(chunk)
    
    return chunks


def extract_study_card_from_document_pages(
    doc_meta: Dict[str, Any],
    pages: List[Dict[str, Any]],
    trial_hint: Dict[str, Any],
    client=None
) -> Dict[str, Any]:
    """
    Convenience function to extract study card directly from document pages.
    
    Args:
        doc_meta: Document metadata
        pages: Document pages with text content
        trial_hint: Trial hints for context
        client: Gemini client (uses mock if None)
        
    Returns:
        Complete, validated Study Card
    """
    # Convert pages to chunks
    chunks = create_text_chunks_from_pages(pages)
    
    # Extract study card
    return extract_study_card_from_document(doc_meta, chunks, trial_hint, client)
