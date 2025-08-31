"""
Base Schema for Study Card Models

Common schema definitions used across all models.
"""

from typing import Dict, Any

# Common field definitions
PROVENANCE_FIELDS = {
    "created_at": {
        "type": "string",
        "format": "date-time",
        "description": "Timestamp when the artifact was created"
    },
    "created_by": {
        "type": "string",
        "description": "Identifier of the worker that created this artifact"
    },
    "version": {
        "type": "integer",
        "minimum": 1,
        "description": "Version number of this artifact"
    },
    "input_hash": {
        "type": "string",
        "pattern": "^[a-f0-9]{64}$",
        "description": "SHA-256 hash of the inputs used to create this artifact"
    },
    "parent_ids": {
        "type": "array",
        "items": {"type": "string"},
        "description": "IDs of parent artifacts that this artifact was derived from"
    },
    "span_ids": {
        "type": "array",
        "items": {"type": "string"},
        "description": "IDs of evidence spans that support this artifact"
    },
    "notes": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Additional notes and comments"
    }
}

BASE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "Unique identifier for this artifact"
        },
        "status": {
            "type": "string",
            "enum": ["draft", "validated", "frozen"],
            "description": "Current status of this artifact"
        },
        "metadata": {
            "type": "object",
            "additionalProperties": True,
            "description": "Additional metadata for this artifact"
        },
        **PROVENANCE_FIELDS
    },
    "required": ["id", "status"],
    "additionalProperties": False
}

# Common validation patterns
ID_PATTERNS = {
    "doc_id": r"^[a-z]+:.+$",
    "span_id": r"^.+?#p\d+:\d+-\d+$",
    "claim_id": r"^claim_\d{8}_\d{6}_[a-f0-9]{8}$",
    "gate_id": r"^gate_g[123]_\d{8}_\d{6}_[a-f0-9]{8}$"
}

# Common field constraints
FIELD_CONSTRAINTS = {
    "confidence": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "Confidence score between 0.0 and 1.0"
    },
    "quality_score": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "Quality score between 0.0 and 1.0"
    },
    "applicability_score": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "Applicability score between 0.0 and 1.0"
    }
}

# Common enums
COMMON_ENUMS = {
    "status_values": ["draft", "validated", "frozen"],
    "stance_values": ["supports", "contradicts", "neutral"],
    "claim_types": [
        "design_fact", "effect_size", "prevalence", "assay_cutoff",
        "pkpd", "operational", "limitation"
    ],
    "gate_families": ["g1", "g2", "g3"],
    "analysis_sets": ["ITT", "mITT", "PP"],
    "document_types": ["PR", "Abstract", "Paper", "Registry", "FDA"]
}
