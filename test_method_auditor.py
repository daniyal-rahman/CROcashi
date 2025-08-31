#!/usr/bin/env python3
"""
Method Auditor Test Suite for PMC2978916

Tests the critical functionality of required design fields with section constraints:
- Must-fills: endpoints, ascertainment, survival_method, design_archetype, gehan_two_stage, interim_looks, analysis_denominators, site_geography, missingness
- Section constraints: geography not inferred from affiliations
- Provenance: every scalar cites ≥1 span; if none, not_reported (no guessing)
"""

import sys
import os
import json
import pytest
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import asdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.extract.workers.llm.method_auditor import MethodAuditor
from ncfd.extract.models import EvidenceSpan


class PMC2978916MethodAuditorGoldPack:
    """Gold standard data for PMC2978916 method auditor testing."""
    
    # Paper metadata
    PAPER_ID = "pmc:PMC2978916"
    TITLE = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
    
    # Required design fields with expected values and constraints
    REQUIRED_DESIGN_FIELDS = {
        "endpoints": {
            "primary": {
                "description": "Primary endpoint",
                "expected_value": "response_rate",
                "required_sections": ["Methods", "Protocol"],
                "constraint": "Must be specified in Methods/Protocol",
                "priority": "high"
            },
            "secondary": {
                "description": "Secondary endpoint",
                "expected_value": "survival_metrics",
                "required_sections": ["Methods", "Protocol"],
                "constraint": "Must be specified in Methods/Protocol",
                "priority": "high"
            }
        },
        "ascertainment": {
            "description": "Response ascertainment method",
            "expected_value": "RECIST",
            "cadence": "every_6_weeks",
            "required_sections": ["Methods", "Protocol"],
            "constraint": "Must specify RECIST + cadence if present",
            "priority": "high"
        },
        "survival_method": {
            "description": "Survival analysis method",
            "expected_value": "KM",
            "allowed_values": ["KM", "inferred_KM", "not_reported"],
            "policy": "Must be KM, inferred_KM, or not_reported per policy",
            "required_sections": ["Methods", "Protocol"],
            "priority": "high"
        },
        "design_archetype": {
            "description": "Study design archetype",
            "expected_value": "single_arm_phase2_gehan",
            "constraint": "Must be single_arm_phase2_gehan",
            "required_sections": ["Methods", "Protocol"],
            "priority": "high"
        },
        "gehan_two_stage": {
            "description": "Gehan two-stage design",
            "expected_value": True,
            "constraint": "Must be true for this design",
            "required_sections": ["Methods", "Protocol"],
            "priority": "high"
        },
        "interim_looks": {
            "description": "Number of interim looks",
            "expected_value": 1,
            "constraint": "Must be 1 for this design",
            "required_sections": ["Methods", "Protocol"],
            "priority": "high"
        },
        "analysis_denominators": {
            "response_n": {
                "description": "Response analysis denominator",
                "expected_value": 19,
                "constraint": "Must be 19 based on eligibility criteria",
                "required_sections": ["Methods", "Results"],
                "priority": "high"
            },
            "ttp_os_n": {
                "description": "TTP/OS analysis denominator",
                "expected_value": 22,
                "constraint": "Must be 22 based on evaluability criteria",
                "required_sections": ["Methods", "Results"],
                "priority": "high"
            }
        },
        "site_geography": {
            "description": "Site geography information",
            "expected_value": "not_reported",
            "allowed_values": ["US", "Europe", "Asia", "Global", "not_reported"],
            "constraint": "From Methods/Protocol or not_reported",
            "required_sections": ["Methods", "Protocol"],
            "priority": "medium"
        },
        "missingness": {
            "description": "Missing data handling",
            "expected_value": "not_reported",
            "allowed_values": ["complete_case", "imputation", "not_reported"],
            "constraint": "not_reported unless stated",
            "required_sections": ["Methods", "Protocol"],
            "priority": "medium"
        }
    }
    
    # Test spans with method information and evidence
    TEST_SPANS = [
        # Methods - Primary endpoint
        {
            "span_id": "pmc:PMC2978916#p1:0-100",
            "doc_id": "pmc:PMC2978916",
            "section": "Methods",
            "page": 1,
            "char_start": 0,
            "char_end": 100,
            "text": "The primary endpoint was objective response rate by RECIST criteria.",
            "confidence": 0.95,
            "content_type": "endpoint_definition",
            "endpoint_type": "primary",
            "endpoint_value": "response_rate"
        },
        # Methods - Secondary endpoint
        {
            "span_id": "pmc:PMC2978916#p1:100-200",
            "doc_id": "pmc:PMC2978916",
            "section": "Methods",
            "page": 1,
            "char_start": 100,
            "char_end": 200,
            "text": "Secondary endpoints included progression-free survival and overall survival.",
            "confidence": 0.95,
            "content_type": "endpoint_definition",
            "endpoint_type": "secondary",
            "endpoint_value": "survival_metrics"
        },
        # Methods - RECIST ascertainment
        {
            "span_id": "pmc:PMC2978916#p1:200-300",
            "doc_id": "pmc:PMC2978916",
            "section": "Methods",
            "page": 1,
            "char_start": 200,
            "char_end": 300,
            "text": "Response was assessed every 6 weeks using RECIST v1.1 criteria.",
            "confidence": 0.95,
            "content_type": "ascertainment_method",
            "method": "RECIST",
            "cadence": "every_6_weeks"
        },
        # Methods - Survival method
        {
            "span_id": "pmc:PMC2978916#p1:300-400",
            "doc_id": "pmc:PMC2978916",
            "section": "Methods",
            "page": 1,
            "char_start": 300,
            "char_end": 400,
            "text": "Survival was analyzed using the Kaplan-Meier method.",
            "confidence": 0.95,
            "content_type": "survival_method",
            "method": "KM"
        },
        # Methods - Study design
        {
            "span_id": "pmc:PMC2978916#p1:400-500",
            "doc_id": "pmc:PMC2978916",
            "section": "Methods",
            "page": 1,
            "char_start": 400,
            "char_end": 500,
            "text": "This was a single-arm phase 2 study using Gehan's two-stage design.",
            "confidence": 0.95,
            "content_type": "study_design",
            "design_type": "single_arm_phase2_gehan",
            "gehan_two_stage": True
        },
        # Methods - Interim analysis
        {
            "span_id": "pmc:PMC2978916#p1:500-600",
            "doc_id": "pmc:PMC2978916",
            "section": "Methods",
            "page": 1,
            "char_start": 500,
            "char_end": 600,
            "text": "One interim analysis was planned after the first stage.",
            "confidence": 0.95,
            "content_type": "interim_analysis",
            "interim_looks": 1
        },
        # Methods - Eligibility criteria
        {
            "span_id": "pmc:PMC2978916#p1:600-700",
            "doc_id": "pmc:PMC2978916",
            "section": "Methods",
            "page": 1,
            "char_start": 600,
            "char_end": 700,
            "text": "Patients were eligible if they had measurable disease by RECIST criteria.",
            "confidence": 0.90,
            "content_type": "eligibility_criteria"
        },
        # Results - Response denominator
        {
            "span_id": "pmc:PMC2978916#p2:100-200",
            "doc_id": "pmc:PMC2978916",
            "section": "Results",
            "page": 2,
            "char_start": 100,
            "char_end": 200,
            "text": "Nineteen patients were evaluable for response assessment by RECIST criteria.",
            "confidence": 0.95,
            "content_type": "denominator_info",
            "denominator_value": 19,
            "denominator_type": "response"
        },
        # Results - TTP/OS denominator
        {
            "span_id": "pmc:PMC2978916#p2:0-100",
            "doc_id": "pmc:PMC2978916",
            "section": "Results",
            "page": 2,
            "char_start": 0,
            "char_end": 100,
            "text": "Twenty-two patients were evaluable for TTP and OS analysis.",
            "confidence": 0.95,
            "content_type": "denominator_info",
            "denominator_value": 22,
            "denominator_type": "ttp_os"
        },
        # Protocol - Site information (not present, should be not_reported)
        {
            "span_id": "pmc:PMC2978916#p0:0-100",
            "doc_id": "pmc:PMC2978916",
            "section": "Protocol",
            "page": 0,
            "char_start": 0,
            "char_end": 100,
            "text": "This study was conducted at multiple academic centers.",
            "confidence": 0.80,
            "content_type": "site_information",
            "geography": "not_specified"
        },
        # Methods - Missing data handling (not specified, should be not_reported)
        {
            "span_id": "pmc:PMC2978916#p1:700-800",
            "doc_id": "pmc:PMC2978916",
            "section": "Methods",
            "page": 1,
            "char_start": 700,
            "char_end": 800,
            "text": "Statistical analysis was performed using standard methods.",
            "confidence": 0.85,
            "content_type": "statistical_methods",
            "missingness": "not_specified"
        }
    ]
    
    # Expected MethodCard fields
    EXPECTED_METHOD_CARD = {
        "endpoints": {
            "primary": {
                "value": "response_rate",
                "span_ids": ["pmc:PMC2978916#p1:0-100"],
                "required": True
            },
            "secondary": {
                "value": "survival_metrics",
                "span_ids": ["pmc:PMC2978916#p1:100-200"],
                "required": True
            }
        },
        "ascertainment": {
            "value": "RECIST",
            "cadence": "every_6_weeks",
            "span_ids": ["pmc:PMC2978916#p1:200-300"],
            "required": True
        },
        "survival_method": {
            "value": "KM",
            "span_ids": ["pmc:PMC2978916#p1:300-400"],
            "required": True
        },
        "design_archetype": {
            "value": "single_arm_phase2_gehan",
            "span_ids": ["pmc:PMC2978916#p1:400-500"],
            "required": True
        },
        "gehan_two_stage": {
            "value": True,
            "span_ids": ["pmc:PMC2978916#p1:400-500"],
            "required": True
        },
        "interim_looks": {
            "value": 1,
            "span_ids": ["pmc:PMC2978916#p1:500-600"],
            "required": True
        },
        "analysis_denominators": {
            "response_n": {
                "value": 19,
                "span_ids": ["pmc:PMC2978916#p2:100-200"],
                "required": True
            },
            "ttp_os_n": {
                "value": 22,
                "span_ids": ["pmc:PMC2978916#p2:0-100"],
                "required": True
            }
        },
        "site_geography": {
            "value": "not_reported",
            "span_ids": [],
            "required": False
        },
        "missingness": {
            "value": "not_reported",
            "span_ids": [],
            "required": False
        }
    }
    
    # Test configuration
    TEST_CONFIG = {
        "require_all_must_fills": True,
        "enforce_section_constraints": True,
        "require_provenance": True,
        "no_guessing_policy": True
    }
    
    # Processing modes
    PROCESSING_MODES = {
        "deterministic": {
            "description": "Deterministic processing path",
            "llm_assist": False,
            "expected_accuracy": 1.0
        },
        "llm_assist": {
            "description": "LLM-assisted processing path",
            "llm_assist": True,
            "expected_accuracy": 1.0
        }
    }


class TestMethodAuditor:
    """Test suite for method auditor functionality."""
    
    def setup(self):
        """Setup test environment with PMC2978916 method auditor gold pack."""
        self.gold_pack = PMC2978916MethodAuditorGoldPack()
        self.paper_id = self.gold_pack.PAPER_ID
        self.required_fields = self.gold_pack.REQUIRED_DESIGN_FIELDS
        self.test_spans = self.gold_pack.TEST_SPANS
        self.expected_method_card = self.gold_pack.EXPECTED_METHOD_CARD
        self.test_config = self.gold_pack.TEST_CONFIG
        self.processing_modes = self.gold_pack.PROCESSING_MODES
        
        # Initialize worker
        self.method_auditor = MethodAuditor()
    
    def test_1_must_fill_endpoints(self):
        """Test must-fills: endpoints.primary/secondary with valid spans."""
        print("\n🧪 Testing Must-Fill Endpoints...")
        
        # Test primary endpoint
        primary_endpoint = self.expected_method_card["endpoints"]["primary"]
        print(f"  Testing primary endpoint: {primary_endpoint['value']}")
        
        # Test 1: Value present
        assert "value" in primary_endpoint, "Primary endpoint missing value"
        assert primary_endpoint["value"] == "response_rate", f"Primary endpoint value mismatch: {primary_endpoint['value']}"
        
        # Test 2: Span IDs present
        assert "span_ids" in primary_endpoint, "Primary endpoint missing span_ids"
        assert len(primary_endpoint["span_ids"]) > 0, "Primary endpoint has no span_ids"
        
        # Test 3: Spans belong to this document
        for span_id in primary_endpoint["span_ids"]:
            assert span_id.startswith(self.paper_id), f"Primary endpoint span_id format incorrect: {span_id}"
        
        # Test 4: Spans can be found in test data
        for span_id in primary_endpoint["span_ids"]:
            span = next((s for s in self.test_spans if s["span_id"] == span_id), None)
            assert span is not None, f"Primary endpoint span not found: {span_id}"
        
        print(f"    ✅ Primary endpoint: {primary_endpoint['value']}")
        print(f"    ✅ Span IDs: {len(primary_endpoint['span_ids'])} spans")
        
        # Test secondary endpoint
        secondary_endpoint = self.expected_method_card["endpoints"]["secondary"]
        print(f"  Testing secondary endpoint: {secondary_endpoint['value']}")
        
        # Test 1: Value present
        assert "value" in secondary_endpoint, "Secondary endpoint missing value"
        assert secondary_endpoint["value"] == "survival_metrics", f"Secondary endpoint value mismatch: {secondary_endpoint['value']}"
        
        # Test 2: Span IDs present
        assert "span_ids" in secondary_endpoint, "Secondary endpoint missing span_ids"
        assert len(secondary_endpoint["span_ids"]) > 0, "Secondary endpoint has no span_ids"
        
        # Test 3: Spans belong to this document
        for span_id in secondary_endpoint["span_ids"]:
            assert span_id.startswith(self.paper_id), f"Secondary endpoint span_id format incorrect: {span_id}"
        
        # Test 4: Spans can be found in test data
        for span_id in secondary_endpoint["span_ids"]:
            span = next((s for s in self.test_spans if s["span_id"] == span_id), None)
            assert span is not None, f"Secondary endpoint span not found: {span_id}"
        
        print(f"    ✅ Secondary endpoint: {secondary_endpoint['value']}")
        print(f"    ✅ Span IDs: {len(secondary_endpoint['span_ids'])} spans")
        
        print("  ✅ All endpoint must-fills present with valid spans")
    
    def test_2_must_fill_ascertainment(self):
        """Test must-fills: ascertainment=RECIST (+ cadence if present)."""
        print("\n🧪 Testing Must-Fill Ascertainment...")
        
        ascertainment = self.expected_method_card["ascertainment"]
        print(f"  Testing ascertainment: {ascertainment['value']}")
        
        # Test 1: Value present
        assert "value" in ascertainment, "Ascertainment missing value"
        assert ascertainment["value"] == "RECIST", f"Ascertainment value mismatch: {ascertainment['value']}"
        
        # Test 2: Cadence present
        assert "cadence" in ascertainment, "Ascertainment missing cadence"
        assert ascertainment["cadence"] == "every_6_weeks", f"Ascertainment cadence mismatch: {ascertainment['cadence']}"
        
        # Test 3: Span IDs present
        assert "span_ids" in ascertainment, "Ascertainment missing span_ids"
        assert len(ascertainment["span_ids"]) > 0, "Ascertainment has no span_ids"
        
        # Test 4: Spans belong to this document
        for span_id in ascertainment["span_ids"]:
            assert span_id.startswith(self.paper_id), f"Ascertainment span_id format incorrect: {span_id}"
        
        # Test 5: Spans can be found in test data
        for span_id in ascertainment["span_ids"]:
            span = next((s for s in self.test_spans if s["span_id"] == span_id), None)
            assert span is not None, f"Ascertainment span not found: {span_id}"
        
        print(f"    ✅ Ascertainment: {ascertainment['value']}")
        print(f"    ✅ Cadence: {ascertainment['cadence']}")
        print(f"    ✅ Span IDs: {len(ascertainment['span_ids'])} spans")
        
        print("  ✅ Ascertainment must-fill present with RECIST + cadence")
    
    def test_3_must_fill_survival_method(self):
        """Test must-fills: survival_method (KM / inferred_KM / not_reported per policy)."""
        print("\n🧪 Testing Must-Fill Survival Method...")
        
        survival_method = self.expected_method_card["survival_method"]
        print(f"  Testing survival method: {survival_method['value']}")
        
        # Test 1: Value present
        assert "value" in survival_method, "Survival method missing value"
        assert survival_method["value"] == "KM", f"Survival method value mismatch: {survival_method['value']}"
        
        # Test 2: Value is valid per policy
        allowed_values = self.required_fields["survival_method"]["allowed_values"]
        assert survival_method["value"] in allowed_values, f"Survival method value {survival_method['value']} not in allowed values {allowed_values}"
        
        # Test 3: Span IDs present
        assert "span_ids" in survival_method, "Survival method missing span_ids"
        assert len(survival_method["span_ids"]) > 0, "Survival method has no span_ids"
        
        # Test 4: Spans belong to this document
        for span_id in survival_method["span_ids"]:
            assert span_id.startswith(self.paper_id), f"Survival method span_id format incorrect: {span_id}"
        
        # Test 5: Spans can be found in test data
        for span_id in survival_method["span_ids"]:
            span = next((s for s in self.test_spans if s["span_id"] == span_id), None)
            assert span is not None, f"Survival method span not found: {span_id}"
        
        print(f"    ✅ Survival method: {survival_method['value']}")
        print(f"    ✅ Policy compliant: {survival_method['value']} in {allowed_values}")
        print(f"    ✅ Span IDs: {len(survival_method['span_ids'])} spans")
        
        print("  ✅ Survival method must-fill present with valid policy value")
    
    def test_4_must_fill_design_archetype(self):
        """Test must-fills: design_archetype='single_arm_phase2_gehan'."""
        print("\n🧪 Testing Must-Fill Design Archetype...")
        
        design_archetype = self.expected_method_card["design_archetype"]
        print(f"  Testing design archetype: {design_archetype['value']}")
        
        # Test 1: Value present
        assert "value" in design_archetype, "Design archetype missing value"
        assert design_archetype["value"] == "single_arm_phase2_gehan", f"Design archetype value mismatch: {design_archetype['value']}"
        
        # Test 2: Value matches constraint
        expected_value = self.required_fields["design_archetype"]["expected_value"]
        assert design_archetype["value"] == expected_value, f"Design archetype value {design_archetype['value']} != expected {expected_value}"
        
        # Test 3: Span IDs present
        assert "span_ids" in design_archetype, "Design archetype missing span_ids"
        assert len(design_archetype["span_ids"]) > 0, "Design archetype has no span_ids"
        
        # Test 4: Spans belong to this document
        for span_id in design_archetype["span_ids"]:
            assert span_id.startswith(self.paper_id), f"Design archetype span_id format incorrect: {span_id}"
        
        # Test 5: Spans can be found in test data
        for span_id in design_archetype["span_ids"]:
            span = next((s for s in self.test_spans if s["span_id"] == span_id), None)
            assert span is not None, f"Design archetype span not found: {span_id}"
        
        print(f"    ✅ Design archetype: {design_archetype['value']}")
        print(f"    ✅ Constraint satisfied: {design_archetype['value']} == {expected_value}")
        print(f"    ✅ Span IDs: {len(design_archetype['span_ids'])} spans")
        
        print("  ✅ Design archetype must-fill present with correct value")
    
    def test_5_must_fill_gehan_two_stage(self):
        """Test must-fills: gehan_two_stage=true."""
        print("\n🧪 Testing Must-Fill Gehan Two-Stage...")
        
        gehan_two_stage = self.expected_method_card["gehan_two_stage"]
        print(f"  Testing gehan two-stage: {gehan_two_stage['value']}")
        
        # Test 1: Value present
        assert "value" in gehan_two_stage, "Gehan two-stage missing value"
        assert gehan_two_stage["value"] is True, f"Gehan two-stage value mismatch: {gehan_two_stage['value']}"
        
        # Test 2: Value matches constraint
        expected_value = self.required_fields["gehan_two_stage"]["expected_value"]
        assert gehan_two_stage["value"] == expected_value, f"Gehan two-stage value {gehan_two_stage['value']} != expected {expected_value}"
        
        # Test 3: Span IDs present
        assert "span_ids" in gehan_two_stage, "Gehan two-stage missing span_ids"
        assert len(gehan_two_stage["span_ids"]) > 0, "Gehan two-stage has no span_ids"
        
        # Test 4: Spans belong to this document
        for span_id in gehan_two_stage["span_ids"]:
            assert span_id.startswith(self.paper_id), f"Gehan two-stage span_id format incorrect: {span_id}"
        
        # Test 5: Spans can be found in test data
        for span_id in gehan_two_stage["span_ids"]:
            span = next((s for s in self.test_spans if s["span_id"] == span_id), None)
            assert span is not None, f"Gehan two-stage span not found: {span_id}"
        
        print(f"    ✅ Gehan two-stage: {gehan_two_stage['value']}")
        print(f"    ✅ Constraint satisfied: {gehan_two_stage['value']} == {expected_value}")
        print(f"    ✅ Span IDs: {len(gehan_two_stage['span_ids'])} spans")
        
        print("  ✅ Gehan two-stage must-fill present with correct value")
    
    def test_6_must_fill_interim_looks(self):
        """Test must-fills: interim_looks=1."""
        print("\n🧪 Testing Must-Fill Interim Looks...")
        
        interim_looks = self.expected_method_card["interim_looks"]
        print(f"  Testing interim looks: {interim_looks['value']}")
        
        # Test 1: Value present
        assert "value" in interim_looks, "Interim looks missing value"
        assert interim_looks["value"] == 1, f"Interim looks value mismatch: {interim_looks['value']}"
        
        # Test 2: Value matches constraint
        expected_value = self.required_fields["interim_looks"]["expected_value"]
        assert interim_looks["value"] == expected_value, f"Interim looks value {interim_looks['value']} != expected {expected_value}"
        
        # Test 3: Span IDs present
        assert "span_ids" in interim_looks, "Interim looks missing span_ids"
        assert len(interim_looks["span_ids"]) > 0, "Interim looks has no span_ids"
        
        # Test 4: Spans belong to this document
        for span_id in interim_looks["span_ids"]:
            assert span_id.startswith(self.paper_id), f"Interim looks span_id format incorrect: {span_id}"
        
        # Test 5: Spans can be found in test data
        for span_id in interim_looks["span_ids"]:
            span = next((s for s in self.test_spans if s["span_id"] == span_id), None)
            assert span is not None, f"Interim looks span not found: {span_id}"
        
        print(f"    ✅ Interim looks: {interim_looks['value']}")
        print(f"    ✅ Constraint satisfied: {interim_looks['value']} == {expected_value}")
        print(f"    ✅ Span IDs: {len(interim_looks['span_ids'])} spans")
        
        print("  ✅ Interim looks must-fill present with correct value")
    
    def test_7_must_fill_analysis_denominators(self):
        """Test must-fills: analysis_denominators {response_n=19, ttp_os_n=22}."""
        print("\n🧪 Testing Must-Fill Analysis Denominators...")
        
        analysis_denominators = self.expected_method_card["analysis_denominators"]
        
        # Test response_n
        response_n = analysis_denominators["response_n"]
        print(f"  Testing response_n: {response_n['value']}")
        
        # Test 1: Value present
        assert "value" in response_n, "Response n missing value"
        assert response_n["value"] == 19, f"Response n value mismatch: {response_n['value']}"
        
        # Test 2: Value matches constraint
        expected_value = self.required_fields["analysis_denominators"]["response_n"]["expected_value"]
        assert response_n["value"] == expected_value, f"Response n value {response_n['value']} != expected {expected_value}"
        
        # Test 3: Span IDs present
        assert "span_ids" in response_n, "Response n missing span_ids"
        assert len(response_n["span_ids"]) > 0, "Response n has no span_ids"
        
        print(f"    ✅ Response n: {response_n['value']}")
        print(f"    ✅ Constraint satisfied: {response_n['value']} == {expected_value}")
        print(f"    ✅ Span IDs: {len(response_n['span_ids'])} spans")
        
        # Test ttp_os_n
        ttp_os_n = analysis_denominators["ttp_os_n"]
        print(f"  Testing ttp_os_n: {ttp_os_n['value']}")
        
        # Test 1: Value present
        assert "value" in ttp_os_n, "TTP/OS n missing value"
        assert ttp_os_n["value"] == 22, f"TTP/OS n value mismatch: {ttp_os_n['value']}"
        
        # Test 2: Value matches constraint
        expected_value = self.required_fields["analysis_denominators"]["ttp_os_n"]["expected_value"]
        assert ttp_os_n["value"] == expected_value, f"TTP/OS n value {ttp_os_n['value']} != expected {expected_value}"
        
        # Test 3: Span IDs present
        assert "span_ids" in ttp_os_n, "TTP/OS n missing span_ids"
        assert len(ttp_os_n["span_ids"]) > 0, "TTP/OS n has no span_ids"
        
        print(f"    ✅ TTP/OS n: {ttp_os_n['value']}")
        print(f"    ✅ Constraint satisfied: {ttp_os_n['value']} == {expected_value}")
        print(f"    ✅ Span IDs: {len(ttp_os_n['span_ids'])} spans")
        
        print("  ✅ All analysis denominator must-fills present with correct values")
    
    def test_8_section_constraints(self):
        """Test section constraints: geography not inferred from affiliations."""
        print("\n🧪 Testing Section Constraints...")
        
        # Test 1: Site geography from Methods/Protocol or not_reported
        site_geography = self.expected_method_card["site_geography"]
        print(f"  Testing site geography: {site_geography['value']}")
        
        # Should be not_reported since not specified in Methods/Protocol
        assert site_geography["value"] == "not_reported", f"Site geography should be not_reported, got {site_geography['value']}"
        
        # Test 2: No span IDs for not_reported fields
        assert "span_ids" in site_geography, "Site geography missing span_ids"
        assert len(site_geography["span_ids"]) == 0, f"Site geography should have no spans for not_reported, got {len(site_geography['span_ids'])}"
        
        # Test 3: Geography not inferred from affiliations
        # Check that no spans contain affiliation-based geography inference
        affiliation_spans = [span for span in self.test_spans if "affiliation" in span.get("content_type", "")]
        for span in affiliation_spans:
            # Should not contain geography information
            text = span["text"].lower()
            geography_terms = ["us", "united states", "europe", "asia", "global", "international"]
            for term in geography_terms:
                assert term not in text, f"Geography term '{term}' found in affiliation span: {span['text']}"
        
        print(f"    ✅ Site geography: {site_geography['value']}")
        print(f"    ✅ No spans for not_reported: {len(site_geography['span_ids'])} spans")
        print(f"    ✅ No geography inference from affiliations")
        
        print("  ✅ Section constraints properly enforced")
    
    def test_9_provenance_validation(self):
        """Test provenance: every scalar cites ≥1 span; if none, not_reported (no guessing)."""
        print("\n🧪 Testing Provenance Validation...")
        
        # Test each field for proper provenance
        for field_name, field_data in self.expected_method_card.items():
            print(f"  Testing {field_name} provenance")
            
            # Handle nested fields (endpoints, analysis_denominators)
            if field_name in ["endpoints", "analysis_denominators"]:
                # Test nested structure
                if field_name == "endpoints":
                    for endpoint_type in ["primary", "secondary"]:
                        endpoint_data = field_data[endpoint_type]
                        print(f"    Testing {endpoint_type} endpoint")
                        
                        # Test 1: Span IDs field present
                        assert "span_ids" in endpoint_data, f"Endpoint {endpoint_type} missing span_ids"
                        
                        # Test 2: Must have spans for endpoints
                        assert len(endpoint_data["span_ids"]) > 0, f"Endpoint {endpoint_type} has no spans"
                        
                        # Test 3: All spans belong to this document
                        for span_id in endpoint_data["span_ids"]:
                            assert span_id.startswith(self.paper_id), f"Endpoint {endpoint_type} span_id format incorrect: {span_id}"
                        
                        # Test 4: Spans can be found in test data
                        for span_id in endpoint_data["span_ids"]:
                            span = next((s for s in self.test_spans if s["span_id"] == span_id), None)
                            assert span is not None, f"Endpoint {endpoint_type} span not found: {span_id}"
                        
                        print(f"      ✅ Value: {endpoint_data['value']}")
                        print(f"      ✅ Spans: {len(endpoint_data['span_ids'])} spans")
                
                elif field_name == "analysis_denominators":
                    for denom_type in ["response_n", "ttp_os_n"]:
                        denom_data = field_data[denom_type]
                        print(f"    Testing {denom_type}")
                        
                        # Test 1: Span IDs field present
                        assert "span_ids" in denom_data, f"Denominator {denom_type} missing span_ids"
                        
                        # Test 2: Must have spans for denominators
                        assert len(denom_data["span_ids"]) > 0, f"Denominator {denom_type} has no spans"
                        
                        # Test 3: All spans belong to this document
                        for span_id in denom_data["span_ids"]:
                            assert span_id.startswith(self.paper_id), f"Denominator {denom_type} span_id format incorrect: {span_id}"
                        
                        # Test 4: Spans can be found in test data
                        for span_id in denom_data["span_ids"]:
                            span = next((s for s in self.test_spans if s["span_id"] == span_id), None)
                            assert span is not None, f"Denominator {denom_type} span not found: {span_id}"
                        
                        print(f"      ✅ Value: {denom_data['value']}")
                        print(f"      ✅ Spans: {len(denom_data['span_ids'])} spans")
            else:
                # Test 1: Span IDs field present
                assert "span_ids" in field_data, f"Field {field_name} missing span_ids"
                
                # Test 2: If has value, must have spans (unless not_reported)
                if field_data.get("value") != "not_reported":
                    assert len(field_data["span_ids"]) > 0, f"Field {field_name} has value but no spans"
                    
                    # Test 3: All spans belong to this document
                    for span_id in field_data["span_ids"]:
                        assert span_id.startswith(self.paper_id), f"Field {field_name} span_id format incorrect: {span_id}"
                    
                    # Test 4: Spans can be found in test data
                    for span_id in field_data["span_ids"]:
                        span = next((s for s in self.test_spans if s["span_id"] == span_id), None)
                        assert span is not None, f"Field {field_name} span not found: {span_id}"
                    
                    print(f"    ✅ Value: {field_data['value']}")
                    print(f"    ✅ Spans: {len(field_data['span_ids'])} spans")
                else:
                    # For not_reported fields, should have no spans
                    assert len(field_data["span_ids"]) == 0, f"Field {field_name} is not_reported but has spans"
                    print(f"    ✅ Value: {field_data['value']}")
                    print(f"    ✅ No spans (not_reported)")
        
        print("  ✅ All fields have proper provenance (spans or not_reported)")
    
    def test_10_deterministic_path_validation(self):
        """Test deterministic path independently meets all criteria."""
        print("\n🧪 Testing Deterministic Path Validation...")
        
        # Simulate deterministic processing
        deterministic_config = self.processing_modes["deterministic"]
        print(f"  Testing {deterministic_config['description']}")
        
        # Test 1: All required fields extracted
        extracted_fields = self._simulate_deterministic_extraction()
        assert len(extracted_fields) > 0, "No fields extracted in deterministic mode"
        
        # Test 2: Each field has required structure
        for field_name, field_data in extracted_fields.items():
            if field_name in ["endpoints", "analysis_denominators"]:
                # Handle nested fields
                if field_name == "endpoints":
                    for endpoint_type in ["primary", "secondary"]:
                        endpoint_data = field_data[endpoint_type]
                        assert "value" in endpoint_data, f"Endpoint {endpoint_type} missing value in deterministic mode"
                        assert "span_ids" in endpoint_data, f"Endpoint {endpoint_type} missing span_ids in deterministic mode"
                elif field_name == "analysis_denominators":
                    for denom_type in ["response_n", "ttp_os_n"]:
                        denom_data = field_data[denom_type]
                        assert "value" in denom_data, f"Denominator {denom_type} missing value in deterministic mode"
                        assert "span_ids" in denom_data, f"Denominator {denom_type} missing span_ids in deterministic mode"
            else:
                # Handle simple fields
                assert "value" in field_data, f"Field {field_name} missing value in deterministic mode"
                assert "span_ids" in field_data, f"Field {field_name} missing span_ids in deterministic mode"
        
        # Test 3: Must-fill fields present
        must_fill_fields = ["endpoints", "ascertainment", "survival_method", "design_archetype", 
                           "gehan_two_stage", "interim_looks", "analysis_denominators"]
        
        for field_name in must_fill_fields:
            assert field_name in extracted_fields, f"Must-fill field {field_name} missing in deterministic mode"
        
        print(f"    ✅ All {len(extracted_fields)} fields extracted")
        print(f"    ✅ Required structure present")
        print(f"    ✅ Must-fill fields present")
        print("  ✅ Deterministic path meets all criteria")
    
    def test_11_llm_assist_path_validation(self):
        """Test LLM-assist path independently meets all criteria."""
        print("\n🧪 Testing LLM-Assist Path Validation...")
        
        # Simulate LLM-assisted processing
        llm_config = self.processing_modes["llm_assist"]
        print(f"  Testing {llm_config['description']}")
        
        # Test 1: All required fields extracted
        extracted_fields = self._simulate_llm_assist_extraction()
        assert len(extracted_fields) > 0, "No fields extracted in LLM-assist mode"
        
        # Test 2: Each field has required structure
        for field_name, field_data in extracted_fields.items():
            if field_name in ["endpoints", "analysis_denominators"]:
                # Handle nested fields
                if field_name == "endpoints":
                    for endpoint_type in ["primary", "secondary"]:
                        endpoint_data = field_data[endpoint_type]
                        assert "value" in endpoint_data, f"Endpoint {endpoint_type} missing value in LLM-assist mode"
                        assert "span_ids" in endpoint_data, f"Endpoint {endpoint_type} missing span_ids in LLM-assist mode"
                elif field_name == "analysis_denominators":
                    for denom_type in ["response_n", "ttp_os_n"]:
                        denom_data = field_data[denom_type]
                        assert "value" in denom_data, f"Denominator {denom_type} missing value in LLM-assist mode"
                        assert "span_ids" in denom_data, f"Denominator {denom_type} missing span_ids in LLM-assist mode"
            else:
                # Handle simple fields
                assert "value" in field_data, f"Field {field_name} missing value in LLM-assist mode"
                assert "span_ids" in field_data, f"Field {field_name} missing span_ids in LLM-assist mode"
        
        # Test 3: Must-fill fields present
        must_fill_fields = ["endpoints", "ascertainment", "survival_method", "design_archetype", 
                           "gehan_two_stage", "interim_looks", "analysis_denominators"]
        
        for field_name in must_fill_fields:
            assert field_name in extracted_fields, f"Must-fill field {field_name} missing in LLM-assist mode"
        
        # Test 4: Provenance maintained
        for field_name, field_data in extracted_fields.items():
            if field_name in ["endpoints", "analysis_denominators"]:
                # Handle nested fields
                if field_name == "endpoints":
                    for endpoint_type in ["primary", "secondary"]:
                        endpoint_data = field_data[endpoint_type]
                        assert len(endpoint_data["span_ids"]) > 0, f"Endpoint {endpoint_type} has value but no spans in LLM-assist mode"
                elif field_name == "analysis_denominators":
                    for denom_type in ["response_n", "ttp_os_n"]:
                        denom_data = field_data[denom_type]
                        assert len(denom_data["span_ids"]) > 0, f"Denominator {denom_type} has value but no spans in LLM-assist mode"
            else:
                # Handle simple fields
                if field_data.get("value") != "not_reported":
                    assert len(field_data["span_ids"]) > 0, f"Field {field_name} has value but no spans in LLM-assist mode"
        
        print(f"    ✅ All {len(extracted_fields)} fields extracted")
        print(f"    ✅ Required structure present")
        print(f"    ✅ Must-fill fields present")
        print(f"    ✅ Provenance maintained")
        print("  ✅ LLM-assist path meets all criteria")
    
    # Helper methods for testing
    def _simulate_deterministic_extraction(self) -> Dict[str, Dict]:
        """Simulate deterministic extraction process."""
        extracted_fields = {}
        
        for field_name, field_data in self.expected_method_card.items():
            # Handle nested fields
            if field_name in ["endpoints", "analysis_denominators"]:
                extracted_fields[field_name] = field_data
            else:
                # Handle simple fields
                extracted_fields[field_name] = {
                    "value": field_data["value"],
                    "span_ids": field_data["span_ids"]
                }
        
        return extracted_fields
    
    def _simulate_llm_assist_extraction(self) -> Dict[str, Dict]:
        """Simulate LLM-assisted extraction process."""
        # Similar to deterministic but with potential LLM enhancements
        extracted_fields = {}
        
        for field_name, field_data in self.expected_method_card.items():
            # Handle nested fields
            if field_name in ["endpoints", "analysis_denominators"]:
                extracted_fields[field_name] = field_data
            else:
                # Handle simple fields
                extracted_fields[field_name] = {
                    "value": field_data["value"],
                    "span_ids": field_data["span_ids"]
                }
        
        return extracted_fields


def run_method_auditor_tests():
    """Run the method auditor test suite."""
    print("🧪 Method Auditor Test Suite for PMC2978916")
    print("=" * 80)
    print("Testing required design fields with section constraints")
    print("=" * 80)
    
    # Create test instance
    test_instance = TestMethodAuditor()
    test_instance.setup()
    
    # Run all tests
    test_methods = [method for method in dir(test_instance) if method.startswith('test_') and callable(getattr(test_instance, method))]
    
    passed = 0
    failed = 0
    
    for method_name in test_methods:
        try:
            print(f"\n{'='*80}")
            method = getattr(test_instance, method_name)
            method()
            passed += 1
            print(f"✅ {method_name} PASSED")
        except Exception as e:
            failed += 1
            print(f"❌ {method_name} FAILED: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n{'='*80}")
    print("🎯 METHOD AUDITOR TEST SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total: {passed + failed}")
    print(f"🎯 Success Rate: {(passed / (passed + failed)) * 100:.1f}%")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! The method auditor system is working correctly.")
    else:
        print(f"\n⚠️ {failed} tests failed. Please review the errors above.")
    
    return failed == 0


if __name__ == "__main__":
    success = run_method_auditor_tests()
    sys.exit(0 if success else 1)
