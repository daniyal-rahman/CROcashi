# V2 Test Results - Study Card System

This folder contains the complete raw outputs from the Study Card system test using PMC2978916 paper.

## Files Overview

### 1. `complete_test_output.txt`
Complete console output from running the test, including all worker outputs and test results.

### 2. `method_auditor_raw_output.json`
Complete raw output from the Method Auditor worker, including:
- Generated MethodCard with 19 extracted fields
- Input spans (3 Methods spans)
- Design JSON and pocket context
- Processing metadata

### 3. `results_distiller_raw_output.json`
Complete raw output from the Results Distiller worker, including:
- Results factsheet (empty as expected for test data)
- Input spans (3 Results spans)
- Trial context
- Processing metadata

### 4. `claimizer_raw_output.json`
Complete raw output from the Claimizer worker, including:
- 8 generated claims with full details
- Input spans (6 total spans)
- Trial context
- Processing metadata

## Test Summary

**Paper**: PMC2978916 - Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer

**Test Results**: ✅ ALL WORKERS PASSED
- Method Auditor: ✅ PASS
- Results Distiller: ✅ PASS  
- Claimizer: ✅ PASS

**Key Outputs**:
- **MethodCard**: Comprehensive study methodology extraction with RECIST endpoints, phase 2 design, Gehan two-stage
- **Claims**: 8 structured claims including design facts (study phase, interim design) and effect sizes (15.8% ORR, 14 weeks PFS, 13.1 months OS)
- **Provenance**: Full traceability with span references and input hashes

## Data Structure

Each worker output includes:
- Success status
- Raw output data
- Input data used
- Processing metadata
- Worker version information

This demonstrates the complete end-to-end functionality of the Study Card system for extracting structured clinical trial information from unstructured text.
