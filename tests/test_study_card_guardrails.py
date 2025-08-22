#!/usr/bin/env python3
"""
Comprehensive tests for Study Card guardrails and validation.

This test suite includes the golden examples from phase5.md and tests
the complete validation pipeline.
"""

import sys
import json
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.extract.validator import (
    validate_card, 
    validate_card_completeness,
    get_coverage_level
)
from ncfd.extract.lanextract_adapter import (
    MockGeminiClient,
    extract_study_card_from_document
)


class TestStudyCardValidation(unittest.TestCase):
    """Test Study Card validation and pivotal requirements."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Golden example 1: PR input (med coverage)
        self.pr_payload = {
            "doc": {
                "doc_type": "PR",
                "title": "Acme reports Phase 3 TOPAZ results of AX-101 in COPD",
                "year": 2024,
                "url": "https://acme.com/pr/topaz",
                "source_id": "pr_topaz_2024"
            },
            "trial_hint": {
                "nct_id": "NCT12345678",
                "phase": "3",
                "indication": "COPD"
            },
            "chunks": [
                {
                    "page": 1,
                    "paragraph": 2,
                    "start": 0,
                    "end": 180,
                    "text": "The Phase 3 TOPAZ study met its primary endpoint, showing a statistically significant reduction in annualized exacerbation rate with AX-101 vs placebo."
                },
                {
                    "page": 1,
                    "paragraph": 3,
                    "start": 181,
                    "end": 360,
                    "text": "TOPAZ enrolled 842 patients randomized 1:1 (AX-101 n=421; placebo n=421) across 120 sites."
                }
            ]
        }
        
        # Golden example 2: Abstract input (high coverage)
        self.abstract_payload = {
            "doc": {
                "doc_type": "Abstract",
                "title": "BRIGHT-1: Phase 3 trial of BX-12 in psoriasis",
                "year": 2025,
                "url": "https://conf.org/abs/BRIGHT1",
                "source_id": "abs_bright1_2025"
            },
            "trial_hint": {
                "nct_id": "NCT87654321",
                "phase": "3",
                "indication": "Plaque psoriasis"
            },
            "chunks": [
                {
                    "page": 1,
                    "paragraph": 1,
                    "start": 0,
                    "end": 240,
                    "text": "Methods: Adults... randomized 2:1 to BX-12 or placebo; primary endpoint PASI-75 at Week 16 (ITT)."
                },
                {
                    "page": 1,
                    "paragraph": 2,
                    "start": 241,
                    "end": 520,
                    "text": "Results: n=660 (BX-12 n=440; placebo n=220). PASI-75 achieved by 68% vs 35% (Δ=33%; p<0.001)."
                }
            ]
        }
        
        # Golden example 3: Paper input (high coverage)
        self.paper_payload = {
            "doc": {
                "doc_type": "Paper",
                "title": "EMERALD: Phase 3 randomized trial of EMR-201 in metastatic CRC",
                "year": 2023,
                "url": "https://doi.org/10.1000/emerald",
                "source_id": "paper_emerald"
            },
            "trial_hint": {
                "nct_id": "NCT00000001",
                "phase": "3",
                "indication": "mCRC"
            },
            "chunks": [
                {
                    "page": 2,
                    "paragraph": 3,
                    "start": 0,
                    "end": 300,
                    "text": "Primary endpoint was progression-free survival (PFS) per blinded independent review at Week 24; ITT was primary analysis population."
                },
                {
                    "page": 5,
                    "paragraph": 2,
                    "start": 0,
                    "end": 300,
                    "text": "A total of 720 patients were randomized 1:1 (EMR-201 n=360; control n=360)."
                },
                {
                    "page": 8,
                    "paragraph": 1,
                    "start": 0,
                    "end": 300,
                    "text": "PFS: HR 0.82 (95% CI 0.70–0.96), p=0.012 (stratified log-rank, alpha=0.025)."
                },
                {
                    "page": 10,
                    "paragraph": 4,
                    "start": 0,
                    "end": 300,
                    "text": "Overall survival at interim: HR 0.95 (95% CI 0.80–1.12), p=0.54; no alpha spent."
                }
            ]
        }
    
    def test_coverage_level_detection(self):
        """Test coverage level detection for different document types."""
        # Test PR coverage (should be med due to missing numeric effect/p-value)
        pr_card = self._create_pr_card()
        coverage = get_coverage_level(pr_card)
        self.assertEqual(coverage, "med", "PR should have medium coverage")
        
        # Test Abstract coverage (should be high due to complete information)
        abstract_card = self._create_abstract_card()
        coverage = get_coverage_level(abstract_card)
        self.assertEqual(coverage, "high", "Abstract should have high coverage")
        
        # Test Paper coverage (should be high due to complete information)
        paper_card = self._create_paper_card()
        coverage = get_coverage_level(paper_card)
        self.assertEqual(coverage, "high", "Paper should have high coverage")
    
    def test_pivotal_requirements_validation(self):
        """Test pivotal trial requirements validation."""
        # Test valid pivotal card
        valid_card = self._create_abstract_card()
        try:
            validate_card(valid_card, is_pivotal=True)
            # Should not raise exception
        except ValueError as e:
            self.fail(f"Valid pivotal card should not raise exception: {e}")
        
        # Test invalid pivotal card (missing p-value/effect)
        invalid_card = self._create_pr_card()
        with self.assertRaises(ValueError) as context:
            validate_card(invalid_card, is_pivotal=True)
        
        self.assertIn("PivotalStudyMissingFields", str(context.exception))
    
    def test_non_pivotal_validation(self):
        """Test that non-pivotal trials don't trigger strict validation."""
        # Non-pivotal trials should pass even with incomplete data
        incomplete_card = self._create_pr_card()
        try:
            validate_card(incomplete_card, is_pivotal=False)
            # Should not raise exception
        except ValueError as e:
            self.fail(f"Non-pivotal card should not raise exception: {e}")
    
    def test_evidence_span_validation(self):
        """Test evidence span validation."""
        from ncfd.extract.validator import validate_evidence_spans
        
        # Test card with evidence spans
        card_with_evidence = self._create_abstract_card()
        evidence_issues = validate_evidence_spans(card_with_evidence)
        self.assertEqual(len(evidence_issues), 0, "Card with evidence should have no issues")
        
        # Test card missing evidence spans
        card_without_evidence = self._create_card_without_evidence()
        evidence_issues = validate_evidence_spans(card_without_evidence)
        self.assertGreater(len(evidence_issues), 0, "Card without evidence should have issues")
    
    def test_comprehensive_validation(self):
        """Test comprehensive validation function."""
        # Test high coverage card
        high_card = self._create_abstract_card()
        results = validate_card_completeness(high_card)
        
        self.assertTrue(results["is_valid"], "High coverage card should be valid")
        self.assertEqual(results["coverage_level"], "high", "Should detect high coverage")
        self.assertEqual(len(results["schema_errors"]), 0, "Should have no schema errors")
        self.assertEqual(len(results["pivotal_errors"]), 0, "Should have no pivotal errors")
    
    def test_mock_gemini_integration(self):
        """Test integration with mock Gemini client."""
        client = MockGeminiClient()
        
        # Test that mock client generates valid JSON
        response = client.generate_json("Generate a study card")
        card = json.loads(response)
        
        # Validate the mock response
        self.assertIn("doc", card, "Mock response should contain doc")
        self.assertIn("trial", card, "Mock response should contain trial")
        self.assertIn("coverage_level", card, "Mock response should contain coverage_level")
        
        # Test that mock response passes validation
        try:
            validate_card(card, is_pivotal=False)
        except Exception as e:
            self.fail(f"Mock response should pass validation: {e}")
    
    def test_end_to_end_extraction(self):
        """Test complete study card extraction workflow."""
        # Test extraction with mock client
        doc_meta = {
            "doc_type": "Abstract",
            "title": "Test Study",
            "year": 2024,
            "url": "https://test.com",
            "source_id": "test_001"
        }
        
        chunks = [
            {
                "page": 1,
                "paragraph": 1,
                "start": 0,
                "end": 100,
                "text": "Sample text"
            }
        ]
        
        trial_hint = {
            "nct_id": "NCT12345678",
            "phase": "3",
            "indication": "Test Indication"
        }
        
        # Extract study card
        card = extract_study_card_from_document(doc_meta, chunks, trial_hint)
        
        # Verify structure
        self.assertIn("doc", card, "Extracted card should contain doc")
        self.assertIn("trial", card, "Extracted card should contain trial")
        self.assertIn("coverage_level", card, "Extracted card should contain coverage_level")
        
        # Verify coverage level is valid
        self.assertIn(card["coverage_level"], ["high", "med", "low"], "Coverage level should be valid")
    
    def _create_pr_card(self):
        """Create a PR study card (medium coverage)."""
        return {
            "doc": {
                "doc_type": "PR",
                "title": "Acme reports Phase 3 TOPAZ results of AX-101 in COPD",
                "year": 2024,
                "url": "https://acme.com/pr/topaz",
                "source_id": "pr_topaz_2024"
            },
            "trial": {
                "nct_id": "NCT12345678",
                "phase": "3",
                "indication": "COPD",
                "is_pivotal": True
            },
            "primary_endpoints": [
                {
                    "name": "Annualized COPD exacerbation rate vs placebo",
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 1,
                                "paragraph": 2
                            },
                            "text_preview": "met its primary endpoint"
                        }
                    ]
                }
            ],
            "populations": {
                "itt": {
                    "defined": True,
                    "text": "Randomized 1:1, assumed ITT",
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
                "pp": {
                    "defined": False,
                    "text": None,
                    "evidence": []
                },
                "analysis_primary_on": "ITT"
            },
            "arms": [
                {
                    "label": "AX-101",
                    "n": 421,
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
                    "label": "Placebo",
                    "n": 421,
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
                "total_n": 842,
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
                        "endpoint": "Annualized exacerbation rate",
                        "population": "ITT",
                        "success_declared": True,
                        "p_value": None,
                        "effect_size": {
                            "metric": "Other",
                            "value": None,
                            "evidence": []
                        },
                        "evidence": [
                            {
                                "loc": {
                                    "scheme": "page_paragraph",
                                    "page": 1,
                                    "paragraph": 2
                                }
                            }
                        ]
                    }
                ]
            },
            "coverage_level": "med",
            "coverage_rationale": "Primary endpoint and N present; no numeric effect or p-value.",
            "extraction_audit": {
                "missing_fields": [
                    "results.primary[0].effect_size.value",
                    "results.primary[0].p_value",
                    "multiplicity"
                ],
                "assumptions": [
                    "Assumed ITT due to randomized 1:1 language."
                ]
            }
        }
    
    def _create_card_without_evidence(self):
        """Create a study card without evidence spans for testing validation."""
        return {
            "doc": {
                "doc_type": "PR",
                "title": "Test PR without evidence",
                "year": 2024,
                "url": "https://test.com",
                "source_id": "test_no_evidence"
            },
            "trial": {
                "nct_id": "NCT99999999",
                "phase": "3",
                "indication": "Test Disease",
                "is_pivotal": False
            },
            "primary_endpoints": [
                {
                    "name": "Test Endpoint"
                    # No evidence spans
                }
            ],
            "populations": {
                "itt": {
                    "defined": True,
                    "text": "ITT"
                    # No evidence spans
                },
                "pp": {
                    "defined": False,
                    "text": None,
                    "evidence": []
                },
                "analysis_primary_on": "ITT"
            },
            "arms": [
                {
                    "label": "Treatment",
                    "n": 100
                    # No evidence spans
                },
                {
                    "label": "Control",
                    "n": 100
                    # No evidence spans
                }
            ],
            "sample_size": {
                "total_n": 200
                # No evidence spans
            },
            "results": {
                "primary": [
                    {
                        "endpoint": "Test Endpoint",
                        "p_value": 0.05
                        # No evidence spans
                    }
                ]
            },
            "coverage_level": "low",
            "coverage_rationale": "Missing evidence spans for numeric claims."
        }
    
    def _create_abstract_card(self):
        """Create an Abstract study card (high coverage)."""
        return {
            "doc": {
                "doc_type": "Abstract",
                "title": "BRIGHT-1: Phase 3 trial of BX-12 in psoriasis",
                "year": 2025,
                "url": "https://conf.org/abs/BRIGHT1",
                "source_id": "abs_bright1_2025"
            },
            "trial": {
                "nct_id": "NCT87654321",
                "phase": "3",
                "indication": "Plaque psoriasis",
                "is_pivotal": True
            },
            "primary_endpoints": [
                {
                    "name": "PASI-75 at Week 16",
                    "timepoint": "Week 16",
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
                    "text": "ITT",
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 1,
                                "paragraph": 1
                            }
                        }
                    ]
                },
                "pp": {
                    "defined": False,
                    "text": None,
                    "evidence": []
                },
                "analysis_primary_on": "ITT"
            },
            "arms": [
                {
                    "label": "BX-12",
                    "n": 440,
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
                {
                    "label": "Placebo",
                    "n": 220,
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 1,
                                "paragraph": 2
                            }
                        }
                    ]
                }
            ],
            "sample_size": {
                "total_n": 660,
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
            "results": {
                "primary": [
                    {
                        "endpoint": "PASI-75 at Week 16",
                        "population": "ITT",
                        "success_declared": True,
                        "effect_size": {
                            "metric": "Δ%",
                            "value": 33.0,
                            "direction_favors": "treatment",
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
                        "p_value": 0.001,
                        "evidence": [
                            {
                                "loc": {
                                    "scheme": "page_paragraph",
                                    "page": 1,
                                    "paragraph": 2
                                }
                            }
                        ]
                    }
                ]
            },
            "coverage_level": "high",
            "coverage_rationale": "Primary endpoint, N, ITT, and effect size with p-value present.",
            "extraction_audit": {
                "missing_fields": [
                    "CI bounds",
                    "multiplicity adjustment"
                ],
                "assumptions": []
            }
        }
    
    def _create_paper_card(self):
        """Create a Paper study card (high coverage)."""
        return {
            "doc": {
                "doc_type": "Paper",
                "title": "EMERALD: Phase 3 randomized trial of EMR-201 in metastatic CRC",
                "year": 2023,
                "url": "https://doi.org/10.1000/emerald",
                "source_id": "paper_emerald"
            },
            "trial": {
                "nct_id": "NCT00000001",
                "phase": "3",
                "indication": "mCRC",
                "is_pivotal": True
            },
            "primary_endpoints": [
                {
                    "name": "PFS per blinded independent review",
                    "timepoint": "Week 24",
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 2,
                                "paragraph": 3
                            }
                        }
                    ]
                }
            ],
            "populations": {
                "itt": {
                    "defined": True,
                    "text": "ITT was primary analysis population",
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 2,
                                "paragraph": 3
                            }
                        }
                    ]
                },
                "pp": {
                    "defined": False,
                    "text": None,
                    "evidence": []
                },
                "analysis_primary_on": "ITT"
            },
            "arms": [
                {
                    "label": "EMR-201",
                    "n": 360,
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 5,
                                "paragraph": 2
                            }
                        }
                    ]
                },
                {
                    "label": "Control",
                    "n": 360,
                    "evidence": [
                        {
                            "loc": {
                                "scheme": "page_paragraph",
                                "page": 5,
                                "paragraph": 2
                            }
                        }
                    ]
                }
            ],
            "sample_size": {
                "total_n": 720,
                "evidence": [
                    {
                        "loc": {
                            "scheme": "page_paragraph",
                            "page": 5,
                            "paragraph": 2
                        }
                    }
                ]
            },
            "results": {
                "primary": [
                    {
                        "endpoint": "PFS",
                        "population": "ITT",
                        "success_declared": True,
                        "effect_size": {
                            "metric": "HR",
                            "value": 0.82,
                            "ci_low": 0.70,
                            "ci_high": 0.96,
                            "ci_level": 95,
                            "direction_favors": "treatment",
                            "evidence": [
                                {
                                    "loc": {
                                        "scheme": "page_paragraph",
                                        "page": 8,
                                        "paragraph": 1
                                    }
                                }
                            ]
                        },
                        "p_value": 0.012,
                        "multiplicity_adjusted": True,
                        "evidence": [
                            {
                                "loc": {
                                    "scheme": "page_paragraph",
                                    "page": 8,
                                    "paragraph": 1
                                }
                            }
                        ]
                    }
                ],
                "secondary": [
                    {
                        "endpoint": "OS (interim)",
                        "population": "ITT",
                        "success_declared": False,
                        "effect_size": {
                            "metric": "HR",
                            "value": 0.95,
                            "ci_low": 0.80,
                            "ci_high": 1.12,
                            "ci_level": 95,
                            "evidence": [
                                {
                                    "loc": {
                                        "scheme": "page_paragraph",
                                        "page": 10,
                                        "paragraph": 4
                                    }
                                }
                            ]
                        },
                        "p_value": 0.54,
                        "evidence": [
                            {
                                "loc": {
                                    "scheme": "page_paragraph",
                                    "page": 10,
                                    "paragraph": 4
                                }
                            }
                        ]
                    }
                ],
                "interim_looks": [
                    {
                        "number": 1,
                        "alpha_spent": 0.0,
                        "evidence": [
                            {
                                "loc": {
                                    "scheme": "page_paragraph",
                                    "page": 10,
                                    "paragraph": 4
                                }
                            }
                        ]
                    }
                ]
            },
            "coverage_level": "high",
            "coverage_rationale": "All pivotal requirements present with explicit numerics and evidence."
        }


def run_comprehensive_tests():
    """Run all comprehensive tests for study card guardrails."""
    print("🧪 Running Comprehensive Study Card Guardrails Tests")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test class
    suite.addTests(loader.loadTestsFromTestCase(TestStudyCardValidation))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print("COMPREHENSIVE TEST RESULTS SUMMARY")
    print("=" * 60)
    
    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED!")
        print(f"   Tests run: {result.testsRun}")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
        
        print("\n🎉 Study Card Guardrails System Verified:")
        print("   • JSON Schema validation")
        print("   • Pivotal trial requirements enforcement")
        print("   • Coverage level detection")
        print("   • Evidence span validation")
        print("   • Mock Gemini integration")
        print("   • End-to-end extraction workflow")
        print("   • Golden example validation")
        
        return True
    else:
        print("❌ SOME TESTS FAILED!")
        print(f"   Tests run: {result.testsRun}")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
        
        if result.failures:
            print("\nFAILURES:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback}")
        
        if result.errors:
            print("\nERRORS:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback}")
        
        return False


if __name__ == "__main__":
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)
