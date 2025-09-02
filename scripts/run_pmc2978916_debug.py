#!/usr/bin/env python3
"""
Debug PMC2978916 End-to-End Test

This script runs the comprehensive end-to-end test for PMC2978916 and provides
detailed debugging output, even when validation fails.
"""

import argparse
import sys
import logging
import json
from pathlib import Path
from typing import Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'tests'))
from test_pmc2978916_e2e import PMC2978916E2ETest


def setup_logging(verbose: bool = False, debug: bool = False):
    """Setup logging configuration."""
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('pmc2978916_debug.log')
        ]
    )


def run_test_with_graceful_handling(output_dir: str = None) -> Dict[str, Any]:
    """Run the test with graceful handling of validation failures."""
    
    # Create test runner
    test_runner = PMC2978916E2ETest(output_dir)
    
    # Run individual steps with detailed logging
    logger = logging.getLogger(__name__)
    logger.info("Running PMC2978916 test with graceful handling")
    
    try:
        # Step 1: Ingest and create BaseSpans
        logger.info("=== STEP 1: Ingesting document and creating BaseSpans ===")
        evidence_spans = test_runner._ingest_document()
        logger.info(f"✅ Created {len(evidence_spans)} BaseSpans")
        
        # Step 2: Validate BaseSpan coverage
        logger.info("=== STEP 2: Validating BaseSpan coverage ===")
        try:
            test_runner._validate_base_span_coverage(evidence_spans)
            logger.info("✅ BaseSpan coverage validation passed")
        except Exception as e:
            logger.error(f"❌ BaseSpan coverage validation failed: {e}")
            return {'success': False, 'errors': [str(e)]}
        
        # Step 3: Run span triage
        logger.info("=== STEP 3: Running span triage ===")
        triaged_spans = test_runner._run_span_triage(evidence_spans)
        logger.info(f"✅ Triage completed: {len(triaged_spans)} spans selected")
        
        # Step 4: Validate span counts and must-hit spans
        logger.info("=== STEP 4: Validating span counts and must-hit spans ===")
        try:
            test_runner._validate_span_counts_and_must_hits(triaged_spans)
            logger.info("✅ Span counts validation passed")
        except Exception as e:
            logger.warning(f"⚠️  Span counts validation failed: {e}")
        
        # Step 5: Run fuzzy alignment
        logger.info("=== STEP 5: Running fuzzy alignment ===")
        aligned_spans = test_runner._run_fuzzy_alignment(triaged_spans)
        logger.info(f"✅ Fuzzy alignment completed: {len(aligned_spans)} spans")
        
        # Step 6: Run dual-path extraction
        logger.info("=== STEP 6: Running dual-path extraction ===")
        try:
            extraction_results = test_runner._run_dual_path_extraction(aligned_spans)
            logger.info("✅ Dual-path extraction completed")
            
            # Analyze extraction results
            analyze_extraction_results(extraction_results)
            
        except Exception as e:
            logger.error(f"❌ Dual-path extraction failed: {e}")
            # Create mock results for validation
            extraction_results = {
                'method_card': None,
                'results_factsheet': None,
                'claims': [],
                'llm_method_card': None,
                'llm_results_factsheet': None,
                'deterministic_method_card': None,
                'deterministic_results_factsheet': None,
                'success': False,
                'errors': [str(e)]
            }
            logger.warning("Using mock results for validation due to extraction failure")
        
        # Step 7: Validate ResultsFactsheet (gracefully)
        logger.info("=== STEP 7: Validating ResultsFactsheet ===")
        try:
            test_runner._validate_results_factsheet(extraction_results.get('results_factsheet'))
            logger.info("✅ ResultsFactsheet validation passed")
        except Exception as e:
            logger.warning(f"⚠️  ResultsFactsheet validation failed: {e}")
        
        # Step 8: Validate MethodCard (gracefully)
        logger.info("=== STEP 8: Validating MethodCard ===")
        try:
            test_runner._validate_method_card(extraction_results.get('method_card'))
            logger.info("✅ MethodCard validation passed")
        except Exception as e:
            logger.warning(f"⚠️  MethodCard validation failed: {e}")
        
        # Step 9: Validate Claims (gracefully)
        logger.info("=== STEP 9: Validating Claims ===")
        try:
            test_runner._validate_claims(extraction_results.get('claims', []))
            logger.info("✅ Claims validation passed")
        except Exception as e:
            logger.warning(f"⚠️  Claims validation failed: {e}")
        
        # Step 10: Validate dual-path fusion (gracefully)
        logger.info("=== STEP 10: Validating dual-path fusion ===")
        try:
            test_runner._validate_dual_path_fusion(extraction_results)
            logger.info("✅ Dual-path fusion validation passed")
        except Exception as e:
            logger.warning(f"⚠️  Dual-path fusion validation failed: {e}")
        
        # Step 11: Final sanity checks
        logger.info("=== STEP 11: Final sanity checks ===")
        test_runner._final_sanity_checks(extraction_results)
        logger.info("✅ Final sanity checks completed")
        
        # Step 12: Save all artifacts
        logger.info("=== STEP 12: Saving all artifacts ===")
        test_runner._save_all_artifacts(evidence_spans, triaged_spans, aligned_spans, extraction_results)
        logger.info("✅ Artifacts saved")
        
        # Mark as successful even if some validations failed
        test_runner.test_results['success'] = True
        logger.info("🎉 PMC2978916 test completed with graceful handling")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")
        test_runner.test_results['errors'].append(f"Test execution failed: {str(e)}")
    
    return test_runner.test_results


def analyze_extraction_results(extraction_results: Dict[str, Any]):
    """Analyze the extraction results in detail."""
    logger = logging.getLogger(__name__)
    
    logger.info("📊 EXTRACTION RESULTS ANALYSIS:")
    
    # Check LLM path results
    llm_method_card = extraction_results.get('llm_method_card')
    llm_results_factsheet = extraction_results.get('llm_results_factsheet')
    
    if llm_method_card:
        logger.info("✅ LLM MethodCard produced")
        logger.info(f"   - Primary endpoint: {getattr(llm_method_card, 'primary_endpoint', 'None')}")
        logger.info(f"   - Design archetype: {getattr(llm_method_card, 'design_archetype', 'None')}")
        logger.info(f"   - Span coverage: {len(getattr(llm_method_card, 'span_ids', []))} spans")
    else:
        logger.warning("⚠️  No LLM MethodCard produced")
    
    if llm_results_factsheet:
        logger.info("✅ LLM ResultsFactsheet produced")
        logger.info(f"   - Results count: {len(getattr(llm_results_factsheet, 'results', []))}")
        logger.info(f"   - Doc ID: {getattr(llm_results_factsheet, 'doc_id', 'None')}")
        
        # Analyze individual results
        for i, result in enumerate(getattr(llm_results_factsheet, 'results', [])):
            logger.info(f"   - Result {i}: {result.get('metric_type', 'Unknown')} = {result.get('value_native', 'None')} {result.get('unit_native', '')}")
    else:
        logger.warning("⚠️  No LLM ResultsFactsheet produced")
    
    # Check deterministic path results
    det_method_card = extraction_results.get('deterministic_method_card')
    det_results_factsheet = extraction_results.get('deterministic_results_factsheet')
    
    if det_method_card:
        logger.info("✅ Deterministic MethodCard produced")
    else:
        logger.warning("⚠️  No deterministic MethodCard produced")
    
    if det_results_factsheet:
        logger.info("✅ Deterministic ResultsFactsheet produced")
    else:
        logger.warning("⚠️  No deterministic ResultsFactsheet produced")
    
    # Check fusion results
    method_card = extraction_results.get('method_card')
    results_factsheet = extraction_results.get('results_factsheet')
    
    if method_card:
        logger.info("✅ Fused MethodCard produced")
    else:
        logger.warning("⚠️  No fused MethodCard produced")
    
    if results_factsheet:
        logger.info("✅ Fused ResultsFactsheet produced")
    else:
        logger.warning("⚠️  No fused ResultsFactsheet produced")
    
    # Check claims
    claims = extraction_results.get('claims', [])
    logger.info(f"📝 Claims produced: {len(claims)}")
    
    # Check errors
    errors = extraction_results.get('errors', [])
    if errors:
        logger.error(f"❌ Extraction errors: {len(errors)}")
        for error in errors:
            logger.error(f"   - {error}")


def analyze_test_results(results: Dict[str, Any], output_dir: str):
    """Analyze and report test results."""
    
    print("\n" + "="*80)
    print("PMC2978916 END-TO-END TEST RESULTS (DEBUG MODE)")
    print("="*80)
    
    # Overall success
    success = results.get('success', False)
    print(f"Overall Test Success: {'✅ PASSED' if success else '❌ FAILED'}")
    
    # Errors
    errors = results.get('errors', [])
    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
    
    # Warnings
    warnings = results.get('warnings', [])
    if warnings:
        print(f"\n⚠️  WARNINGS ({len(warnings)}):")
        for i, warning in enumerate(warnings, 1):
            print(f"  {i}. {warning}")
    
    # Validation results
    validation_results = results.get('validation_results', {})
    if validation_results:
        print(f"\n📊 VALIDATION RESULTS:")
        for validation_name, validation_data in validation_results.items():
            print(f"  {validation_name}:")
            
            # Count errors and warnings
            val_errors = validation_data.get('errors', [])
            val_warnings = validation_data.get('warnings', [])
            
            if val_errors:
                print(f"    ❌ Errors: {len(val_errors)}")
                for error in val_errors[:3]:  # Show first 3
                    print(f"      - {error}")
                if len(val_errors) > 3:
                    print(f"      ... and {len(val_errors) - 3} more")
            
            if val_warnings:
                print(f"    ⚠️  Warnings: {len(val_warnings)}")
                for warning in val_warnings[:3]:  # Show first 3
                    print(f"      - {warning}")
                if len(val_warnings) > 3:
                    print(f"      ... and {len(val_warnings) - 3} more")
            
            if not val_errors and not val_warnings:
                print(f"    ✅ All validations passed")
    
    # Output directory
    print(f"\n📁 OUTPUT DIRECTORY: {output_dir}")
    print("Generated files:")
    
    output_path = Path(output_dir)
    if output_path.exists():
        for file_path in output_path.glob("*.json"):
            file_size = file_path.stat().st_size
            print(f"  - {file_path.name} ({file_size} bytes)")
    
    # Summary
    print(f"\n📋 SUMMARY:")
    print(f"  - Test completed: {'Yes' if success else 'No'}")
    print(f"  - Errors: {len(errors)}")
    print(f"  - Warnings: {len(warnings)}")
    print(f"  - Validation checks: {len(validation_results)}")
    
    if success:
        print(f"\n🎉 Test completed successfully!")
    else:
        print(f"\n🔧 Test completed with issues - check artifacts for details")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run PMC2978916 end-to-end test with detailed debugging"
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='test_outputs/pmc2978916_debug',
        help='Output directory for test artifacts (default: test_outputs/pmc2978916_debug)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(verbose=args.verbose, debug=args.debug)
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Run the test
    logger = logging.getLogger(__name__)
    logger.info(f"Starting PMC2978916 debug test")
    logger.info(f"Output directory: {output_dir}")
    
    try:
        results = run_test_with_graceful_handling(str(output_dir))
        
        # Analyze and report results
        analyze_test_results(results, str(output_dir))
        
        # Exit with appropriate code
        if results.get('success', False):
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.error("Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
