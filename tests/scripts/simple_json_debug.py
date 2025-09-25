#!/usr/bin/env python3
"""
Simple JSON Debug Test

Test the actual LLM response from the logs to identify parsing issues.
"""

import json
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_actual_llm_response():
    """Test the actual LLM response from the logs."""
    
    # This is the actual LLM response from run2.txt line 757
    actual_response = '''{
  "factsheet_sections": {
    "KEY_FINDINGS": [
      "PTI-125 significantly reduced CSF and plasma biomarkers of Alzheimer's disease pathology, neurodegeneration and neuroinflammation after 28 days of treatment.",
      "All patients showed a biomarker response to PTI-125; biomarker reductions reached at least p ≤ 0.001 by paired t test.",
      "Target engagement demonstrated by reversal of aberrant filamin A conformation in lymphocytes (93% aberrant on Day 1 vs. 40% on Day 28).",
      "PTI-125 was safe and well-tolerated in this study population."
    ],
    "EFFICACY_DATA": {
      "primary_endpoint_results": {
        "description": "Changes in CSF and plasma biomarkers (pathology, neurodegeneration, neuroinflammation) from baseline to Day 28.",
        "results_summary": [
          "Total tau decreased 20%",
          "Neurogranin decreased 32%",
          "Neurofilament light chain decreased 22%",
          "Phospho-tau (pT181) decreased 34%",
          "Neuroinflammation markers (YKL-40 and inflammatory cytokines) decreased 5-14%",
          "Aβ42 increased slightly (interpreted as desirable)"
        ],
        "statistical_significance": "Biomarker reductions were at least p ≤ 0.001 by paired t test."
      },
      "secondary_endpoint_results": {
        "description": "Target engagement, pharmacokinetics, plasma tau species.",
        "results_summary": [
          "Filamin A aberrant conformation shifted from 93% (Day 1) to 40% (Day 28) in lymphocytes.",
          "Filamin A linkages with α7-nicotinic acetylcholine receptor and toll-like receptor 4, and Aβ42 complexes with α7-nicotinic acetylcholine receptor and CD14, were all significantly reduced.",
          "Plasma half-life = 4.5 hours; ~30% drug accumulation on Day 28 vs Day 1.",
          "Plasma phosphorylated and nitrated tau species were assessed (pT181, pS202, pT231, nY29) and showed effects similar to CSF (biomarker effects were similar in plasma)."
        ]
      }
    },
    "SAFETY_DATA": {
      "safety_results": [
        "PTI-125 was safe and well-tolerated in all patients.",
        "Safety assessments included electrocardiograms, clinical laboratory analyses and adverse event monitoring.",
        "No specific adverse events or safety concerns were reported in the provided text."
      ],
      "pharmacokinetics": {
        "plasma_half_life": "4.5 hours",
        "accumulation": "Approximately 30% accumulation on Day 28 vs Day 1"
      }
    },
    "MECHANISM_DATA": [
      "PTI-125 is an oral small molecule that binds and reverses an altered conformation of filamin A found in AD brain, preventing filamin A linkages to α7-nicotinic acetylcholine receptor and toll-like receptor 4, thereby blocking Aβ42's toxic signaling that leads to tau hyperphosphorylation and neuroinflammation.",
      "The drug reduces Aβ42's femtomolar binding affinity to α7-nicotinic acetylcholine receptor by ~1,000-fold (mechanistic interpretation of Aβ42 increase)."
    ],
    "DOSING_DATA": {
      "dose": "100 mg",
      "route": "oral tablets",
      "schedule": "twice daily",
      "duration": "28 consecutive days"
    },
    "POPULATION_DATA": {
      "total_enrolled": 13,
      "eligibility_summary": "Mild-to-moderate Alzheimer's disease patients, age 50-85, Mini Mental State Exam ≥16 and ≤24, with CSF total tau/Aβ42 ratio ≥0.30.",
      "study_sites": "Five clinical trial sites in the U.S.",
      "study_design": "First-in-patient, open-label Phase 2a safety, pharmacokinetics and biomarker study."
    },
    "BIOMARKER_DATA": {
      "assessed_biomarkers": [
        "Pathology: pT181 tau, total tau, Aβ42",
        "Neurodegeneration: neurofilament light chain, neurogranin",
        "Neuroinflammation: YKL-40, interleukin-6, interleukin-1β, tumor necrosis factor α",
        "Plasma tau species: pT181-tau, pS202-tau, pT231-tau, nY29-tau",
        "Lymphocyte measures: filamin A conformation (isoelectric focusing point), filamin A linkages to α7-nicotinic acetylcholine receptor and toll-like receptor 4, Aβ42 complexes with α7-nicotinic acetylcholine receptor or CD14"
      ],
      "numeric_results": {
        "total_tau": "-20%",
        "neurogranin": "-32%",
        "neurofilament_light_chain": "-22%",
        "phospho_tau_pT181": "-34%",
        "neuroinflammation_markers": "-5% to -14%",
        "filaminA_aberrant": "93% (Day 1) -> 40% (Day 28)"
      }
    },
    "LIMITATIONS": [
      "Small sample size (n=13) and open-label, uncontrolled Phase 2a design.",
      "Short treatment duration (28 days).",
      "The trial did not measure cognition (no clinical cognitive endpoints reported).",
      "Findings are biomarker-based and require confirmation in larger, randomized, placebo-controlled trials (a ~60-patient Phase 2b is stated as enrolling)."
    ]
  },
  "provenance": {
    "KEY_FINDINGS": {
      "value": [
        "PTI-125 significantly reduced CSF and plasma biomarkers of Alzheimer's disease pathology, neurodegeneration and neuroinflammation after 28 days of treatment.",
        "All patients showed a biomarker response to PTI-125; biomarker reductions reached at least p ≤ 0.001 by paired t test.",
        "Target engagement demonstrated by reversal of aberrant filamin A conformation in lymphocytes (93% aberrant on Day 1 vs. 40% on Day 28).",
        "PTI-125 was safe and well-tolerated in this study population."
      ],
      "quotes": [
        {
          "text": "Consistent with the drug's mechanism of action and preclinical data, PTI-125 reduced cerebrospinal fluid biomarkers of Alzheimer's disease pathology, neurodegeneration and neuroinflammation from baseline to Day 28.",
          "loc": "Abstract; approx chars 700-830"
        },
        {
          "text": "All patients showed a biomarker response to PTI-125.",
          "loc": "Abstract; approx chars 930-965"
        },
        {
          "text": "Target engagement was shown in lymphocytes by a shift in filamin A's conformation from aberrant to native: 93% was aberrant on Day 1 vs. 40% on Day 28.",
          "loc": "Abstract; approx chars 1260-1330"
        },
        {
          "text": "PTI-125 was safe and well-tolerated in all patients.",
          "loc": "Abstract; approx chars 1410-1440"
        }
      ]
    }
  }
}'''

    logger.info("=== Testing Actual LLM Response ===")
    
    # Test 1: Direct JSON parsing
    try:
        parsed = json.loads(actual_response)
        logger.info("✅ Direct JSON parsing succeeded!")
        logger.info(f"Top-level keys: {list(parsed.keys())}")
        logger.info(f"Factsheet sections: {list(parsed.get('factsheet_sections', {}).keys())}")
        logger.info(f"Provenance keys: {list(parsed.get('provenance', {}).keys())}")
        
        # Check specific issues
        key_findings = parsed.get('factsheet_sections', {}).get('KEY_FINDINGS')
        logger.info(f"KEY_FINDINGS type: {type(key_findings)}")
        logger.info(f"KEY_FINDINGS content: {key_findings}")
        
        provenance_key_findings = parsed.get('provenance', {}).get('KEY_FINDINGS')
        logger.info(f"Provenance KEY_FINDINGS type: {type(provenance_key_findings)}")
        
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Direct JSON parsing failed: {e}")
        logger.error(f"Error at line {e.lineno}, column {e.colno}")
        logger.error(f"Error message: {e.msg}")
        
        # Show the problematic area
        lines = actual_response.split('\n')
        if e.lineno <= len(lines):
            logger.error(f"Problematic line: {lines[e.lineno - 1]}")
        
        return False

if __name__ == "__main__":
    logger.info("🔍 Starting Simple JSON Debug Test")
    success = test_actual_llm_response()
    if success:
        logger.info("✅ JSON parsing works fine - the issue must be elsewhere!")
    else:
        logger.info("❌ Found JSON parsing issue!")
    logger.info("✅ Simple JSON Debug Test Complete")
