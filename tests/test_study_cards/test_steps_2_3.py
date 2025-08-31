"""
Tests for Steps 2-3: Results Distiller and Method Auditor

Tests the implementation of:
- Step 2: Results Distiller v0 (facts-only rows)
- Step 3: Method Auditor v0 (the non-obvious bits)
"""

import pytest
import json
from unittest.mock import Mock, patch

from src.ncfd.extract.workers.llm.results_distiller import ResultsDistiller
from src.ncfd.extract.workers.llm.method_auditor import MethodAuditor
from src.ncfd.extract.models import (
    EvidenceSpan, ResultsFactsheet, MethodCard, PocketContextCard
)
from src.ncfd.extract.workers.base_worker import WorkerResult


class TestStep2ResultsDistiller:
    """Test the Results Distiller worker implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.distiller = ResultsDistiller()
        
        # Create sample evidence spans
        self.results_spans = [
            EvidenceSpan(
                doc_id="pmid:12345",
                page=2,
                char_start=0,
                char_end=150,
                quote="The primary endpoint showed a hazard ratio of 0.75 (95% CI: 0.60-0.94, p=0.012) in the intent-to-treat population at 12 months follow-up.",
                section="Results",
                confidence=0.9
            ),
            EvidenceSpan(
                doc_id="pmid:12345",
                page=2,
                char_start=151,
                char_end=300,
                quote="Secondary analysis revealed an odds ratio of 1.25 (95% CI: 0.95-1.65, p=0.108) in the per-protocol population.",
                section="Results",
                confidence=0.8
            ),
            EvidenceSpan(
                doc_id="pmid:12345",
                page=3,
                char_start=0,
                char_end=100,
                quote="Post-hoc subgroup analysis showed a response rate of 45% in patients aged >65 years.",
                section="Results",
                confidence=0.7
            ),
            EvidenceSpan(
                doc_id="pmid:12345",
                page=4,
                char_start=0,
                char_end=80,
                quote="The study demonstrated a mean difference of -2.5 points (95% CI: -3.8 to -1.2) in the primary outcome.",
                section="Table",
                confidence=0.9
            )
        ]
        
        self.trial_context = {
            "disease": "heart_failure",
            "intervention": "gene_therapy",
            "primary_endpoint": "time_to_first_hf_hospitalization"
        }

    def test_validate_inputs_success(self):
        """Test input validation with valid inputs."""
        inputs = {
            'evidence_spans': self.results_spans,
            'trial_context': self.trial_context
        }
        
        assert self.distiller.validate_inputs(inputs) is True

    def test_validate_inputs_missing_spans(self):
        """Test input validation with missing evidence spans."""
        inputs = {
            'trial_context': self.trial_context
        }
        
        assert self.distiller.validate_inputs(inputs) is False

    def test_validate_inputs_empty_spans(self):
        """Test input validation with empty evidence spans list."""
        inputs = {
            'evidence_spans': [],
            'trial_context': self.trial_context
        }
        
        assert self.distiller.validate_inputs(inputs) is False

    def test_validate_inputs_wrong_span_type(self):
        """Test input validation with wrong span type."""
        inputs = {
            'evidence_spans': [{"not": "a_span"}],
            'trial_context': self.trial_context
        }
        
        assert self.distiller.validate_inputs(inputs) is False

    def test_filter_results_spans(self):
        """Test filtering of results spans."""
        # Add a low-confidence span
        low_confidence_span = EvidenceSpan(
            doc_id="pmid:12345",
            page=5,
            char_start=0,
            char_end=50,
            quote="Some low quality text",
            section="Results",
            confidence=0.3
        )
        
        all_spans = self.results_spans + [low_confidence_span]
        filtered_spans = self.distiller._filter_results_spans(all_spans)
        
        # Should exclude the low-confidence span
        assert len(filtered_spans) == len(self.results_spans)
        assert low_confidence_span not in filtered_spans

    def test_filter_results_spans_wrong_section(self):
        """Test filtering spans from wrong sections."""
        wrong_section_span = EvidenceSpan(
            doc_id="pmid:12345",
            page=6,
            char_start=0,
            char_end=50,
            quote="Methods section text",
            section="Methods",
            confidence=0.9
        )
        
        all_spans = self.results_spans + [wrong_section_span]
        filtered_spans = self.distiller._filter_results_spans(all_spans)
        
        # Should exclude the Methods section span
        assert len(filtered_spans) == len(self.results_spans)
        assert wrong_section_span not in filtered_spans

    def test_is_spin_content(self):
        """Test detection of spin content."""
        spin_text = "The results showed a promising trend toward significance"
        non_spin_text = "The primary endpoint was met with p=0.045"
        
        assert self.distiller._is_spin_content(spin_text) is True
        assert self.distiller._is_spin_content(non_spin_text) is False

    def test_extract_span_results(self):
        """Test extraction of results from a single span."""
        span = self.results_spans[0]  # HR span
        
        results = self.distiller._extract_span_results(span, self.trial_context)
        
        assert len(results) >= 1
        result = results[0]
        assert result['span_id'] == span.span_id

    def test_extract_result_context(self):
        """Test extraction of result context."""
        text = "The hazard ratio was 0.75 (95% CI: 0.60-0.94, p=0.012) in the ITT population at 12 months"
        start = text.find("0.75")
        end = start + 4
        
        context = self.distiller._extract_result_context(text, start, end)
        
        assert context['ci_lower'] == 0.60
        assert context['ci_upper'] == 0.94
        assert context['p_value'] == 0.012
        assert context['analysis_set'] == 'intent_to_treat'
        assert context['timepoint'] == '12_months'
        assert context['is_posthoc'] is False

    def test_extract_analysis_set(self):
        """Test extraction of analysis set information."""
        text = "Results were analyzed in the intent-to-treat population"
        
        analysis_set = self.distiller._extract_analysis_set(text)
        assert analysis_set == 'intent_to_treat'
        
        text2 = "Per-protocol analysis showed similar results"
        analysis_set2 = self.distiller._extract_analysis_set(text2)
        assert analysis_set2 == 'per_protocol'

    def test_extract_timepoint(self):
        """Test extraction of timepoint information."""
        text = "Results at 6 months follow-up"
        timepoint = self.distiller._extract_timepoint(text)
        assert timepoint == '6_months'
        
        text2 = "Baseline measurements were taken"
        timepoint2 = self.distiller._extract_timepoint(text2)
        assert timepoint2 == 'baseline'

    def test_is_posthoc_content(self):
        """Test detection of post-hoc content."""
        posthoc_text = "Post-hoc subgroup analysis revealed"
        non_posthoc_text = "Primary endpoint analysis showed"
        
        assert self.distiller._is_posthoc_content(posthoc_text) is True
        assert self.distiller._is_posthoc_content(non_posthoc_text) is False

    def test_extract_population_slice(self):
        """Test extraction of population slice information."""
        text = "Results in patients aged >65 years"
        population_slice = self.distiller._extract_population_slice(text)
        assert population_slice == 'age >65'
        
        text2 = "Male patients showed better response"
        population_slice2 = self.distiller._extract_population_slice(text2)
        assert population_slice2 == 'male'

    def test_extract_flags(self):
        """Test extraction of flags and qualifiers."""
        text = "Nominal p-values were reported"
        flags = self.distiller._extract_flags(text)
        assert 'nominal_p' in flags
        
        text2 = "Sensitivity analysis confirmed results"
        flags2 = self.distiller._extract_flags(text2)
        assert 'sensitivity' in flags2

    def test_deduplicate_results(self):
        """Test deduplication of results."""
        results = [
            {'metric': 'HR', 'analysis_set': 'ITT', 'timepoint': '12_months', 'population_slice': None},
            {'metric': 'HR', 'analysis_set': 'ITT', 'timepoint': '12_months', 'population_slice': None},  # Duplicate
            {'metric': 'HR', 'analysis_set': 'PP', 'timepoint': '12_months', 'population_slice': None},  # Different set
        ]
        
        deduplicated = self.distiller._deduplicate_results(results)
        assert len(deduplicated) == 2  # Should remove duplicate

    def test_create_factsheet_entry(self):
        """Test creation of ResultsFactsheet entry."""
        result = {
            'metric': 'median_os',
            'value': 13.1,
            'units': 'months',
            'summary_statistic': 'median',
            'n': 22,
            'method': 'Kaplan-Meier',
            'ci_lower': 0.60,
            'ci_upper': 0.94,
            'p_value': 0.012,
            'analysis_set': 'not_specified',
            'timepoint': None,
            'is_posthoc': False,
            'flags': [],
            'span_id': 'pmid:12345#p2:0-150'
        }
        
        factsheet_entry = self.distiller._create_factsheet_entry(result)
        
        assert factsheet_entry is not None
        assert len(factsheet_entry.results) == 1
        
        # Check the first result in the results list
        first_result = factsheet_entry.results[0]
        assert first_result['metric'] == 'median_os'
        assert first_result['value'] == 13.1
        assert first_result['units'] == 'months'
        assert first_result['summary_statistic'] == 'median'
        assert first_result['n'] == 22
        assert first_result['method'] == 'Kaplan-Meier'
        assert first_result['span_ids'] == ['pmid:12345#p2:0-150']

    def test_determine_direction(self):
        """Test determination of effect direction."""
        # For survival metrics, higher values are generally favorable
        assert self.distiller._determine_direction(13.1, 'median_os') == 'favorable'
        # For response rates, higher values are favorable
        assert self.distiller._determine_direction(16.0, 'orr_recist') == 'favorable'

    def test_process_success(self):
        """Test successful processing of results."""
        inputs = {
            'evidence_spans': self.results_spans,
            'trial_context': self.trial_context
        }
        
        result = self.distiller.process(inputs)
        
        assert result.success is True
        assert 'results_factsheet' in result.output
        assert len(result.output['results_factsheet']) > 0
        assert result.output['processed_spans'] == len(self.results_spans)

    def test_process_validation_failure(self):
        """Test processing with validation failure."""
        inputs = {
            'evidence_spans': [],  # Empty spans
            'trial_context': self.trial_context
        }
        
        result = self.distiller.process(inputs)
        
        assert result.success is False
        assert 'Invalid inputs' in result.error_message


class TestStep2ResultsDistillerPMC2978916:
    """Comprehensive test for Results Distiller using PMC2978916 ovarian cancer paper."""
    
    def setup_method(self):
        """Set up test fixtures for PMC2978916 paper."""
        self.distiller = ResultsDistiller()
        
        # Create evidence spans from PMC2978916 paper
        self.pmc2978916_spans = [
            # Table 3 span with TTP and OS data
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                page=3,
                char_start=0,
                char_end=200,
                quote="Median time to progression was 14 weeks (range 0.7-45 weeks) and median overall survival was 13.1 months (range 3-63+ months) in the Phase 2 population (n=22).",
                section="Table",
                confidence=0.95,
                table_id="3"
            ),
            # Results paragraph with ORR and CA-125 data
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                page=2,
                char_start=500,
                char_end=700,
                quote="The overall response rate was 16% (3 of 19 patients) with 1 complete response, 2 partial responses, 6 stable disease, and 10 progressive disease. CA-125 response was observed in 21% (4 of 19 patients).",
                section="Results",
                confidence=0.9
            ),
            # Abstract span (should be deduplicated)
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                page=1,
                char_start=100,
                char_end=300,
                quote="Median time to progression was 14 weeks and overall survival was 13.1 months. Response rate was 16%.",
                section="Abstract",
                confidence=0.8
            )
        ]
        
        self.trial_context = {
            "disease": "ovarian_cancer",
            "intervention": "atrasentan_plus_doxorubicin",
            "doc_id": "pmc:PMC2978916",
            "phase": "phase_1_2"
        }

    def test_extract_median_ttp_from_pmc2978916(self):
        """Test extraction of median TTP from PMC2978916."""
        span = self.pmc2978916_spans[0]  # Table 3 span
        
        results = self.distiller._extract_span_results(span, self.trial_context)
        
        # Find median TTP result
        ttp_results = [r for r in results if r['metric'] == 'median_ttp']
        assert len(ttp_results) == 1
        
        ttp_result = ttp_results[0]
        assert ttp_result['value'] == 14.0
        assert ttp_result['units'] == 'weeks'
        assert ttp_result['summary_statistic'] == 'median'
        assert ttp_result['n'] == 22
        assert ttp_result['method'] == 'Kaplan-Meier'
        assert ttp_result['range_min'] == 0.7
        assert ttp_result['range_max'] == '45'
        assert ttp_result['span_id'] == span.span_id

    def test_extract_median_os_from_pmc2978916(self):
        """Test extraction of median OS from PMC2978916."""
        span = self.pmc2978916_spans[0]  # Table 3 span
        
        results = self.distiller._extract_span_results(span, self.trial_context)
        
        # Find median OS result
        os_results = [r for r in results if r['metric'] == 'median_os']
        assert len(os_results) == 1
        
        os_result = os_results[0]
        assert os_result['value'] == 13.1
        assert os_result['units'] == 'months'
        assert os_result['summary_statistic'] == 'median'
        assert os_result['n'] == 22
        assert os_result['method'] == 'Kaplan-Meier'
        assert os_result['range_min'] == 3.0
        assert os_result['range_max'] == '63+'
        assert os_result['span_id'] == span.span_id

    def test_extract_orr_recist_from_pmc2978916(self):
        """Test extraction of ORR from PMC2978916."""
        span = self.pmc2978916_spans[1]  # Results span
        
        results = self.distiller._extract_span_results(span, self.trial_context)
        
        # Find ORR result
        orr_results = [r for r in results if r['metric'] == 'orr_recist']
        assert len(orr_results) == 1
        
        orr_result = orr_results[0]
        assert orr_result['value'] == 16.0
        assert orr_result['units'] == 'percent'
        assert orr_result['summary_statistic'] == 'proportion'
        assert orr_result['n'] == 19
        assert orr_result['breakdown'] == {'CR': 1, 'PR': 2, 'SD': 6, 'PD': 10}
        assert orr_result['span_id'] == span.span_id

    def test_extract_ca125_response_from_pmc2978916(self):
        """Test extraction of CA-125 response from PMC2978916."""
        span = self.pmc2978916_spans[1]  # Results span
        
        results = self.distiller._extract_span_results(span, self.trial_context)
        
        # Find CA-125 response result
        ca125_results = [r for r in results if r['metric'] == 'ca125_response']
        assert len(ca125_results) == 1
        
        ca125_result = ca125_results[0]
        assert ca125_result['value'] == 21.0
        assert ca125_result['units'] == 'percent'
        assert ca125_result['summary_statistic'] == 'proportion'
        assert ca125_result['n'] == 19
        assert ca125_result['span_id'] == span.span_id

    def test_comprehensive_pmc2978916_validation(self):
        """Comprehensive validation of all PMC2978916 results."""
        results = self.distiller.process({
            'evidence_spans': self.pmc2978916_spans,
            'trial_context': self.trial_context
        })
        
        assert results.success is True
        factsheets = results.output['results_factsheet']
        
        # Collect all results
        all_results = []
        for factsheet in factsheets:
            all_results.extend(factsheet.results)
        
        # Should have exactly 4 results
        assert len(all_results) == 4
        
        # Check each expected result
        expected_results = {
            'median_ttp': {'value': 14.0, 'units': 'weeks', 'n': 22, 'method': 'Kaplan-Meier'},
            'median_os': {'value': 13.1, 'units': 'months', 'n': 22, 'method': 'Kaplan-Meier'},
            'orr_recist': {'value': 16.0, 'units': 'percent', 'n': 19, 'breakdown': {'CR': 1, 'PR': 2, 'SD': 6, 'PD': 10}},
            'ca125_response': {'value': 21.0, 'units': 'percent', 'n': 19}
        }
        
        for metric, expected in expected_results.items():
            result = next((r for r in all_results if r['metric'] == metric), None)
            assert result is not None, f"Missing result for {metric}"
            
            for field, expected_value in expected.items():
                assert result[field] == expected_value, f"Field {field} mismatch for {metric}"

    def test_no_serialization_junk(self):
        """Test that no serialization junk appears in results."""
        results = self.distiller.process({
            'evidence_spans': self.pmc2978916_spans,
            'trial_context': self.trial_context
        })
        
        assert results.success is True
        factsheets = results.output['results_factsheet']
        
        # Check that no Field(...) strings appear
        for factsheet in factsheets:
            factsheet_dict = factsheet.to_dict()
            factsheet_str = json.dumps(factsheet_dict)
            assert 'Field(' not in factsheet_str, "Found serialization junk in factsheet"

    def test_analysis_set_not_itt_for_single_arm(self):
        """Test that analysis_set is not ITT for single-arm phase 1/2 study."""
        results = self.distiller.process({
            'evidence_spans': self.pmc2978916_spans,
            'trial_context': self.trial_context
        })
        
        assert results.success is True
        factsheets = results.output['results_factsheet']
        
        for factsheet in factsheets:
            for result in factsheet.results:
                # Should not default to ITT for single-arm study
                analysis_set = result.get('analysis_set')
                assert analysis_set != 'intent_to_treat'
                # Should be 'not_specified' or None
                assert analysis_set in ['not_specified', None]

    def test_provenance_anchors_from_table_and_results(self):
        """Test that results have proper provenance anchors from Table 3 or Results."""
        results = self.distiller.process({
            'evidence_spans': self.pmc2978916_spans,
            'trial_context': self.trial_context
        })
        
        assert results.success is True
        factsheets = results.output['results_factsheet']
        
        for factsheet in factsheets:
            for result in factsheet.results:
                span_ids = result['span_ids']
                assert len(span_ids) > 0
                
                # Each span_id should reference the correct document
                for span_id in span_ids:
                    assert span_id.startswith('pmc:PMC2978916')
                
                # Should reference Table 3 or Results section, not Abstract
                valid_sections = ['table:3', 'sec:Results']
                assert any(section in span_id for span_id in span_ids for section in valid_sections)

    def test_metric_enum_validation(self):
        """Test that only valid metric enums are accepted."""
        # Test with invalid metric
        invalid_result = {
            'metric': 'survival_rate',  # Invalid - should be median_os
            'value': 13.1,
            'units': 'months',
            'n': 22,
            'span_id': 'pmc:PMC2978916#table:3:rTTP_OS'
        }
        
        factsheet_entry = self.distiller._create_factsheet_entry(invalid_result)
        assert factsheet_entry is None  # Should reject invalid metric

    def test_units_validation(self):
        """Test that units are properly validated."""
        # Test with swapped units
        invalid_result = {
            'metric': 'median_os',
            'value': 13.1,
            'units': 'weeks',  # Invalid - OS should be months
            'n': 22,
            'span_id': 'pmc:PMC2978916#table:3:rTTP_OS'
        }
        
        factsheet_entry = self.distiller._create_factsheet_entry(invalid_result)
        # This should still be created but with corrected units
        assert factsheet_entry is not None

    def test_required_fields_validation(self):
        """Test that required fields are present."""
        # Test missing n
        invalid_result = {
            'metric': 'median_os',
            'value': 13.1,
            'units': 'months',
            # Missing 'n'
            'span_id': 'pmc:PMC2978916#table:3:rTTP_OS'
        }
        
        factsheet_entry = self.distiller._create_factsheet_entry(invalid_result)
        assert factsheet_entry is None  # Should reject missing n


class TestStep3MethodAuditor:
    """Test the Method Auditor worker implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.auditor = MethodAuditor()
        
        # Create sample evidence spans
        self.methods_spans = [
            EvidenceSpan(
                doc_id="pmid:12345",
                page=1,
                char_start=0,
                char_end=200,
                quote="The study enrolled patients with heart failure and reduced ejection fraction. Primary endpoint was time to first HF hospitalization. Statistical analysis used two-sided testing with α=0.05 and Bonferroni correction for multiple comparisons.",
                section="Methods",
                confidence=0.9
            ),
            EvidenceSpan(
                doc_id="pmid:12345",
                page=1,
                char_start=201,
                char_end=400,
                quote="Interim analysis was planned at 50% and 75% of events. Sample size re-estimation was allowed. Analysis was performed in the intent-to-treat population with missing data handled by multiple imputation.",
                section="Methods",
                confidence=0.8
            ),
            EvidenceSpan(
                doc_id="pmid:12345",
                page=2,
                char_start=0,
                char_end=150,
                quote="The study was conducted at 45 sites across North America and Europe. Endpoints were adjudicated by a central endpoint committee. Blinding was maintained throughout the study.",
                section="Protocol",
                confidence=0.9
            )
        ]
        
        self.design_json = {
            "arms": ["placebo", "treatment"],
            "total_n": 500,
            "primary_endpoint": {
                "name": "time_to_first_hf_hospitalization",
                "summary_measure": "hazard_ratio"
            }
        }
        
        self.pocket_context = PocketContextCard(
            disease="heart_failure",
            intervention_class="gene_therapy"
        )

    def test_validate_inputs_success(self):
        """Test input validation with valid inputs."""
        inputs = {
            'evidence_spans': self.methods_spans,
            'design_json': self.design_json,
            'pocket_context': self.pocket_context
        }
        
        assert self.auditor.validate_inputs(inputs) is True

    def test_validate_inputs_missing_spans(self):
        """Test input validation with missing evidence spans."""
        inputs = {
            'design_json': self.design_json,
            'pocket_context': self.pocket_context
        }
        
        assert self.auditor.validate_inputs(inputs) is False

    def test_validate_inputs_wrong_design_type(self):
        """Test input validation with wrong design_json type."""
        inputs = {
            'evidence_spans': self.methods_spans,
            'design_json': "not_a_dict",
            'pocket_context': self.pocket_context
        }
        
        assert self.auditor.validate_inputs(inputs) is False

    def test_filter_methods_spans(self):
        """Test filtering of methods spans."""
        # Add a span from wrong section
        wrong_section_span = EvidenceSpan(
            doc_id="pmid:12345",
            page=3,
            char_start=0,
            char_end=100,
            quote="Results showed significant improvement",
            section="Results",
            confidence=0.9
        )
        
        all_spans = self.methods_spans + [wrong_section_span]
        filtered_spans = self.auditor._filter_methods_spans(all_spans)
        
        # Should exclude the Results section span
        assert len(filtered_spans) == len(self.methods_spans)
        assert wrong_section_span not in filtered_spans

    def test_extract_estimand(self):
        """Test extraction of estimand information."""
        text = "The study enrolled patients with heart failure. Primary endpoint was time to first HF hospitalization."
        
        estimand = self.auditor._extract_estimand(text, self.design_json)
        
        assert 'heart failure' in estimand['population']
        assert 'time to first HF hospitalization' in estimand['endpoint']
        assert estimand['summary_measure'] == 'hazard_ratio'  # From design_json

    def test_extract_alpha_structure(self):
        """Test extraction of alpha structure information."""
        text = "Statistical analysis used two-sided testing with α=0.05 and Bonferroni correction for multiple comparisons."
        
        alpha_structure = self.auditor._extract_alpha_structure(text)
        
        assert alpha_structure['sidedness'] == 'two_sided'
        assert alpha_structure['multiplicity_plan'] == 'adjusted'
        assert alpha_structure['gatekeeping'] is False

    def test_extract_interim_plan(self):
        """Test extraction of interim analysis plan."""
        text = "Interim analysis was planned at 50% and 75% of events. Sample size re-estimation was allowed."
        
        interim = self.auditor._extract_interim_plan(text)
        
        assert interim['looks'] == 2  # 50% and 75%
        assert interim['ssr'] is True

    def test_extract_analysis_sets(self):
        """Test extraction of analysis set information."""
        text = "Analysis was performed in the intent-to-treat population with stratification by age and sex."
        
        analysis_sets = self.auditor._extract_analysis_sets(text, self.design_json)
        
        assert analysis_sets['ITT'] is True
        assert 'age' in analysis_sets['stratification_factors']
        assert 'sex' in analysis_sets['stratification_factors']

    def test_extract_missingness_policies(self):
        """Test extraction of missingness policies."""
        text = "Missing data was handled by multiple imputation assuming missing at random."
        
        missingness = self.auditor._extract_missingness_policies(text)
        
        assert missingness['assumption'] == 'MAR'
        assert missingness['imputation_method'] == 'imputation'

    def test_extract_endpoint_ascertainment(self):
        """Test extraction of endpoint ascertainment information."""
        text = "Endpoints were adjudicated by a central endpoint committee. Blinding was maintained throughout the study."
        
        ascertainment = self.auditor._extract_endpoint_ascertainment(text)
        
        assert ascertainment['method'] == 'CEC'
        assert ascertainment['blinded'] is True
        assert ascertainment['adjudication'] == 'central'

    def test_extract_protocol_features(self):
        """Test extraction of protocol features."""
        text = "The study included a 2-week run-in period and allowed rescue therapy."
        
        features = self.auditor._extract_protocol_features(text)
        
        assert features['run_in'] is True
        assert features['rescue'] is True

    def test_extract_assay_thresholds(self):
        """Test extraction of assay thresholds."""
        text = "Vector genome cutoff was set at 1e6 vg/mL and neutralizing antibody threshold at 1:40 titer."
        
        thresholds = self.auditor._extract_assay_thresholds(text)
        
        assert len(thresholds) >= 1
        # Check that we can extract at least one threshold
        assert any('cutoff' in t['threshold_type'] for t in thresholds)

    def test_extract_dose_rationale(self):
        """Test extraction of dose-exposure rationale."""
        text = "Dose selection was based on target engagement studies in preclinical models."
        
        rationale = self.auditor._extract_dose_rationale(text, self.pocket_context)
        
        assert 'target engagement' in rationale

    def test_extract_site_geography(self):
        """Test extraction of site geography information."""
        text = "The study was conducted at 45 sites across North America and Europe."
        
        geography = self.auditor._extract_site_geography(text)
        
        assert geography['num_sites'] == 45
        assert 'north america' in geography['regions']
        assert 'europe' in geography['regions']
        assert geography['dispersion'] == 'medium'

    def test_extract_design_risks(self):
        """Test extraction of design risks."""
        text = "The study had limited power due to small sample size and high missingness in follow-up data."
        
        risks = self.auditor._extract_design_risks(text, self.pocket_context)
        
        assert 'small_sample_size' in risks
        assert 'missing_data' in risks

    def test_create_method_card(self):
        """Test creation of MethodCard from extracted information."""
        method_info = {
            'estimand': {'population': 'heart failure patients', 'endpoint': 'HF hospitalization'},
            'alpha_structure': {'sidedness': 'two_sided', 'multiplicity_plan': 'adjusted'},
            'interim': {'looks': 2, 'ssr': True},
            'analysis_set': {'ITT': True, 'stratification_factors': ['age', 'sex']},
            'missingness': {'assumption': 'MAR', 'imputation_method': 'imputation'},
            'endpoint_ascertainment': {'method': 'CEC', 'blinded': True},
            'protocol_features': {'run_in': True, 'rescue': True},
            'assay_thresholds': [{'assay_type': 'vector_genome', 'value': 1e6, 'units': 'vg/mL'}],
            'dose_exposure_rationale': 'target engagement studies',
            'site_geography': {'num_sites': 45, 'regions': ['north america', 'europe']},
            'design_risks': ['small_sample_size', 'missing_data']
        }
        
        method_card = self.auditor._create_method_card(method_info, self.methods_spans)
        
        assert method_card is not None
        assert method_card.estimand['population'] == 'heart failure patients'
        assert method_card.alpha_structure['sidedness'] == 'two_sided'
        assert method_card.site_geography['num_sites'] == 45
        assert len(method_card.provenance_anchors) == len(self.methods_spans)

    def test_process_success(self):
        """Test successful processing of methodology."""
        inputs = {
            'evidence_spans': self.methods_spans,
            'design_json': self.design_json,
            'pocket_context': self.pocket_context
        }
        
        result = self.auditor.process(inputs)
        
        assert result.success is True
        assert 'method_card' in result.output
        assert result.output['method_card'] is not None
        assert result.output['processed_spans'] == len(self.methods_spans)

    def test_process_validation_failure(self):
        """Test processing with validation failure."""
        inputs = {
            'evidence_spans': [],  # Empty spans
            'design_json': self.design_json,
            'pocket_context': self.pocket_context
        }
        
        result = self.auditor.process(inputs)
        
        assert result.success is False
        assert 'Invalid inputs' in result.error_message


class TestIntegrationSteps2And3:
    """Integration tests for Steps 2 and 3 working together."""
    
    def setup_method(self):
        """Set up test fixtures for integration testing."""
        self.distiller = ResultsDistiller()
        self.auditor = MethodAuditor()
        
        # Create comprehensive test data
        self.evidence_spans = [
            # Results spans
            EvidenceSpan(
                doc_id="pmid:12345",
                page=2,
                char_start=0,
                char_end=150,
                quote="Primary endpoint: HR 0.75 (95% CI: 0.60-0.94, p=0.012) in ITT population at 12 months.",
                section="Results",
                confidence=0.9
            ),
            # Methods spans
            EvidenceSpan(
                doc_id="pmid:12345",
                page=1,
                char_start=0,
                char_end=200,
                quote="Study enrolled HF patients. Two-sided testing with α=0.05. ITT analysis with multiple imputation.",
                section="Methods",
                confidence=0.9
            )
        ]
        
        self.design_json = {
            "arms": ["placebo", "treatment"],
            "total_n": 500,
            "primary_endpoint": {
                "name": "time_to_first_hf_hospitalization",
                "summary_measure": "hazard_ratio"
            }
        }
        
        self.pocket_context = PocketContextCard(
            disease="heart_failure",
            intervention_class="gene_therapy"
        )

    def test_end_to_end_workflow(self):
        """Test the complete workflow from spans to both outputs."""
        # Step 2: Results Distiller
        results_inputs = {
            'evidence_spans': self.evidence_spans,
            'trial_context': {'disease': 'heart_failure'}
        }
        
        results_result = self.distiller.process(results_inputs)
        assert results_result.success is True
        assert 'results_factsheet' in results_result.output
        
        # Step 3: Method Auditor
        methods_inputs = {
            'evidence_spans': self.evidence_spans,
            'design_json': self.design_json,
            'pocket_context': self.pocket_context
        }
        
        methods_result = self.auditor.process(methods_inputs)
        assert methods_result.success is True
        assert 'method_card' in methods_result.output
        
        # Verify that both outputs have proper provenance
        results_factsheet = results_result.output['results_factsheet']
        method_card = methods_result.output['method_card']
        
        # Check that results reference the correct spans
        for entry in results_factsheet:
            # ResultsFactsheet stores results in the results list
            assert len(entry.results) > 0
            for result in entry.results:
                assert len(result['span_ids']) > 0
                assert all(span_id in [span.span_id for span in self.evidence_spans] 
                          for span_id in result['span_ids'])
        
        # Check that method card references the correct spans
        assert len(method_card.provenance_anchors) > 0
        assert all(span_id in [span.span_id for span in self.evidence_spans] 
                  for span_id in method_card.provenance_anchors)

    def test_data_consistency(self):
        """Test that extracted data is consistent between workers."""
        # Process with both workers
        results_result = self.distiller.process({
            'evidence_spans': self.evidence_spans,
            'trial_context': {'disease': 'heart_failure'}
        })
        
        methods_result = self.auditor.process({
            'evidence_spans': self.evidence_spans,
            'design_json': self.design_json,
            'pocket_context': self.pocket_context
        })
        
        # Extract key information
        results_factsheet = results_result.output['results_factsheet']
        method_card = methods_result.output['method_card']
        
        # Check that both reference the same document
        for entry in results_factsheet:
            # ResultsFactsheet stores results in the results list
            assert len(entry.results) > 0
            for result in entry.results:
                assert result['doc_id'] == "pmid:12345"
        
        # Check that method card has the expected structure
        assert method_card.estimand is not None
        assert method_card.alpha_structure is not None
        assert method_card.analysis_set is not None
        
        # Verify that the extracted methodology aligns with the results
        # (e.g., if we extracted ITT analysis, we should see ITT results)
        analysis_set_data = json.loads(method_card.analysis_set)
        if analysis_set_data.get('ITT'):
            # Should find ITT results in the factsheet
            itt_results = []
            for entry in results_factsheet:
                for result in entry.results:
                    if result.get('analysis_set') == 'ITT':
                        itt_results.append(result)
            assert len(itt_results) > 0
