"""
DocumentCard JSON Schema

Schema for validating DocumentCard objects.
"""

from .base import BASE_SCHEMA, ID_PATTERNS, COMMON_ENUMS

DOCUMENT_CARD_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "DocumentCard",
    "description": "Source document representation with metadata and references",
    "type": "object",
    "allOf": [
        {"$ref": "#/definitions/base"},
        {
            "properties": {
                "doc_id": {
                    "type": "string",
                    "pattern": ID_PATTERNS["doc_id"],
                    "description": "Unique document identifier (e.g., pmid:, doi:, ctgov:NCT...)"
                },
                "doc_type": {
                    "type": "string",
                    "enum": COMMON_ENUMS["document_types"],
                    "description": "Type of document"
                },
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Document title"
                },
                "year": {
                    "type": "integer",
                    "minimum": 1900,
                    "maximum": 2030,
                    "description": "Publication year"
                },
                "venue": {
                    "type": "string",
                    "description": "Publication venue (journal, conference, etc.)"
                },
                "study_type": {
                    "type": "string",
                    "description": "Type of study (RCT, observational, etc.)"
                },
                "disease": {
                    "type": "string",
                    "description": "Primary disease or condition"
                },
                "intervention": {
                    "type": "string",
                    "description": "Primary intervention"
                },
                "route": {
                    "type": "string",
                    "description": "Route of administration"
                },
                "dose_units": {
                    "type": "string",
                    "description": "Units for dose information"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region of study"
                },
                "url": {
                    "type": "string",
                    "format": "uri",
                    "description": "URL to the document"
                },
                "source_id": {
                    "type": "string",
                    "description": "Original source identifier (NCT ID, PMID, etc.)"
                },
                "fulltext_refs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "page": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "Page number (1-based)"
                            },
                            "start_char": {
                                "type": "integer",
                                "minimum": 0,
                                "description": "Starting character position (0-based)"
                            },
                            "end_char": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "Ending character position (exclusive)"
                            },
                            "ref_type": {
                                "type": "string",
                                "enum": ["text", "table", "figure", "protocol"],
                                "description": "Type of reference"
                            },
                            "figure_id": {
                                "type": "string",
                                "description": "Figure identifier if applicable"
                            },
                            "table_id": {
                                "type": "string",
                                "description": "Table identifier if applicable"
                            }
                        },
                        "required": ["page", "start_char", "end_char", "ref_type"],
                        "additionalProperties": False
                    },
                    "description": "Fulltext references with page/character anchors"
                },
                "concepts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "MeSH/UMLS/CT.gov vocabulary concepts"
                },
                "abstract": {
                    "type": "string",
                    "description": "Document abstract"
                },
                "authors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of authors"
                },
                "journal": {
                    "type": "string",
                    "description": "Journal name"
                },
                "doi": {
                    "type": "string",
                    "pattern": r"^10\.\d{4,}/.+$",
                    "description": "Digital Object Identifier"
                },
                "pmid": {
                    "type": "string",
                    "pattern": r"^\d+$",
                    "description": "PubMed identifier"
                }
            },
            "required": ["doc_id", "doc_type", "title", "year"],
            "additionalProperties": False
        }
    ],
    "definitions": {
        "base": BASE_SCHEMA
    }
}

# Example DocumentCard for validation testing
EXAMPLE_DOCUMENT_CARD = {
    "id": "doc_001",
    "status": "validated",
    "doc_id": "pmid:12345678",
    "doc_type": "Paper",
    "title": "Efficacy and Safety of Gene Therapy in Heart Failure",
    "year": 2023,
    "venue": "New England Journal of Medicine",
    "study_type": "RCT",
    "disease": "Heart Failure",
    "intervention": "AAV Gene Therapy",
    "route": "intracoronary",
    "dose_units": "vg",
    "region": "North America",
    "url": "https://doi.org/10.1056/NEJMoa1234567",
    "source_id": "12345678",
    "fulltext_refs": [
        {
            "page": 1,
            "start_char": 0,
            "end_char": 200,
            "ref_type": "text"
        }
    ],
    "concepts": ["heart failure", "gene therapy", "AAV"],
    "abstract": "This study evaluated the efficacy and safety...",
    "authors": ["Smith J", "Johnson A", "Brown B"],
    "journal": "New England Journal of Medicine",
    "doi": "10.1056/NEJMoa1234567",
    "pmid": "12345678",
    "created_at": "2024-01-15T10:00:00Z",
    "created_by": "retriever_worker",
    "version": 1,
    "span_ids": [],
    "notes": []
}
