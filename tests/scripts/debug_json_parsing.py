#!/usr/bin/env python3
"""
Debug JSON Parsing Issues

This script tests the JSON parsing logic with actual LLM responses from the logs
to identify why factsheet extraction is failing.
"""

import json
import sys
import os
import logging
from typing import Dict, Any

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from ncfd.extract.utils.json_repair import JSONRepairUtil
from ncfd.extract.generators.factsheet_extractor import LLMFactsheetExtractor

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_json_parsing():
    """Test JSON parsing with actual LLM responses from the logs."""
    
    # Sample LLM response from the logs (truncated but shows the structure)
    sample_response_1 = '''{
  "factsheet_sections": {
    "KEY_FINDINGS": [
      "PTI-125 significantly reduced CSF and plasma biomarkers of Alzheimer's disease pathology, neurodegeneration and neuroinflammation after 28 days of treatment.",
      "All patients showed a biomarker response to PTI-125; biomarker reductions reached at least p ≤ 0.05 for multiple biomarkers."
    ],
    "EFFICACY_DATA": "Primary efficacy endpoints were CSF and plasma biomarkers including pT181 tau, total tau, Aβ42, NfL, YKL-40, and others. All patients showed statistically significant reductions in these biomarkers.",
    "SAFETY_DATA": "PTI-125 was reported safe and well-tolerated with no serious adverse events reported.",
    "MECHANISM_DATA": "PTI-125 targets filamin A (FLNA) to disrupt aberrant interactions with α7nAChR and inflammatory receptors.",
    "DOSING_DATA": "Patients received PTI-125 100 mg PO BID for 28 days.",
    "POPULATION_DATA": "Phase 2a open-label study with n=13 patients with mild to moderate Alzheimer's disease.",
    "BIOMARKER_DATA": "CSF and plasma biomarkers measured included pT181 tau, total tau, Aβ42, NfL, YKL-40, and other AD-related biomarkers.",
    "LIMITATIONS": "Small sample size (n=13), open-label design, short duration (28 days), biomarker endpoints not validated for clinical benefit."
  },
  "provenance": {
    "KEY_FINDINGS": {
      "value": "PTI-125 significantly reduced CSF and plasma biomarkers of Alzheimer's disease pathology, neurodegeneration and neuroinflammation after 28 days of treatment.",
      "quotes": [
        {
          "text": "PTI-125 significantly reduced CSF and plasma biomarkers of Alzheimer's disease pathology, neurodegeneration and neuroinflammation after 28 days of treatment.",
          "loc": {
            "doc_id": "doc1",
            "section": "Results",
            "start": 1200,
            "end": 1350
          },
          "confidence": 0.95
        }
      ]
    },
    "EFFICACY_DATA": {
      "value": "Primary efficacy endpoints were CSF and plasma biomarkers including pT181 tau, total tau, Aβ42, NfL, YKL-40, and others.",
      "quotes": [
        {
          "text": "Primary efficacy endpoints were CSF and plasma biomarkers including pT181 tau, total tau, Aβ42, NfL, YKL-40, and others.",
          "loc": {
            "doc_id": "doc1",
            "section": "Methods",
            "start": 800,
            "end": 950
          },
          "confidence": 0.90
        }
      ]
    }
  }
}'''

    # Test 1: Direct JSON parsing
    logger.info("=== Test 1: Direct JSON Parsing ===")
    try:
        parsed = json.loads(sample_response_1)
        logger.info("✅ Direct JSON parsing succeeded")
        logger.info(f"Keys: {list(parsed.keys())}")
        logger.info(f"Factsheet sections: {list(parsed.get('factsheet_sections', {}).keys())}")
        logger.info(f"Provenance keys: {list(parsed.get('provenance', {}).keys())}")
    except json.JSONDecodeError as e:
        logger.error(f"❌ Direct JSON parsing failed: {e}")
        logger.error(f"Error at line {e.lineno}, column {e.colno}")
    
    # Test 2: JSON Repair Utility
    logger.info("\n=== Test 2: JSON Repair Utility ===")
    repair_util = JSONRepairUtil()
    
    # Get the schema from the factsheet extractor
    extractor = LLMFactsheetExtractor()
    schema = extractor._get_flexible_json_schema()
    
    try:
        repaired = repair_util.repair_json(sample_response_1, schema)
        if repaired:
            logger.info("✅ JSON repair succeeded")
            logger.info(f"Repaired keys: {list(repaired.keys())}")
        else:
            logger.error("❌ JSON repair failed")
    except Exception as e:
        logger.error(f"❌ JSON repair error: {e}")
    
    # Test 3: Test with malformed JSON (simulate truncation)
    logger.info("\n=== Test 3: Truncated JSON (Simulating Real Issue) ===")
    
    # Simulate what might happen with large responses
    truncated_response = sample_response_1[:1000] + "..."
    logger.info(f"Truncated response length: {len(truncated_response)}")
    logger.info(f"Truncated response: {truncated_response}")
    
    try:
        parsed_truncated = json.loads(truncated_response)
        logger.info("✅ Truncated JSON parsing succeeded")
    except json.JSONDecodeError as e:
        logger.error(f"❌ Truncated JSON parsing failed: {e}")
        logger.error(f"Error at line {e.lineno}, column {e.colno}")
        
        # Try repair
        try:
            repaired_truncated = repair_util.repair_json(truncated_response, schema)
            if repaired_truncated:
                logger.info("✅ Truncated JSON repair succeeded")
            else:
                logger.error("❌ Truncated JSON repair failed")
        except Exception as repair_error:
            logger.error(f"❌ Truncated JSON repair error: {repair_error}")
    
    # Test 4: Test with array in KEY_FINDINGS (from the logs)
    logger.info("\n=== Test 4: Array in KEY_FINDINGS (From Logs) ===")
    
    array_response = '''{
  "factsheet_sections": {
    "KEY_FINDINGS": [
      "PTI-125 significantly reduced CSF and plasma biomarkers of Alzheimer's disease pathology, neurodegeneration and neuroinflammation after 28 days of treatment.",
      "All patients showed a biomarker response to PTI-125; biomarker reductions reached at least p ≤ 0.05 for multiple biomarkers."
    ],
    "EFFICACY_DATA": "Primary efficacy endpoints were CSF and plasma biomarkers including pT181 tau, total tau, Aβ42, NfL, YKL-40, and others."
  },
  "provenance": {
    "KEY_FINDINGS": {
      "value": "PTI-125 significantly reduced CSF and plasma biomarkers of Alzheimer's disease pathology, neurodegeneration and neuroinflammation after 28 days of treatment.",
      "quotes": [
        {
          "text": "PTI-125 significantly reduced CSF and plasma biomarkers of Alzheimer's disease pathology, neurodegeneration and neuroinflammation after 28 days of treatment.",
          "loc": {
            "doc_id": "doc1",
            "section": "Results",
            "start": 1200,
            "end": 1350
          },
          "confidence": 0.95
        }
      ]
    }
  }
}'''
    
    try:
        parsed_array = json.loads(array_response)
        logger.info("✅ Array JSON parsing succeeded")
        logger.info(f"KEY_FINDINGS type: {type(parsed_array['factsheet_sections']['KEY_FINDINGS'])}")
        logger.info(f"KEY_FINDINGS content: {parsed_array['factsheet_sections']['KEY_FINDINGS']}")
    except json.JSONDecodeError as e:
        logger.error(f"❌ Array JSON parsing failed: {e}")
    
    # Test 5: Check schema compatibility
    logger.info("\n=== Test 5: Schema Compatibility ===")
    logger.info(f"Schema expects KEY_FINDINGS as: {schema['properties']['factsheet_sections']['properties'].get('key_findings', 'NOT FOUND')}")
    
    # The schema expects lowercase field names, but LLM generates uppercase
    logger.info("🔍 ISSUE FOUND: Schema expects 'key_findings' but LLM generates 'KEY_FINDINGS'")
    
    return True

if __name__ == "__main__":
    logger.info("🔍 Starting JSON Parsing Debug Test")
    test_json_parsing()
    logger.info("✅ JSON Parsing Debug Test Complete")
