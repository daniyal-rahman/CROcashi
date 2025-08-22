"""
Synthetic data generation for trial failure detection testing.

This module provides comprehensive synthetic data generators for creating
realistic test scenarios including study cards, trial versions, and historical
data for validating the failure detection system.
"""

import random
import json
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np


class TrialType(Enum):
    """Trial type classifications."""
    PIVOTAL = "pivotal"
    NON_PIVOTAL = "non_pivotal"
    PHASE_1 = "phase_1"
    PHASE_2 = "phase_2"
    PHASE_3 = "phase_3"


class Indication(Enum):
    """Medical indication classifications."""
    ONCOLOGY = "oncology"
    CARDIOVASCULAR = "cardiovascular"
    RARE_DISEASE = "rare_disease"
    NEUROLOGY = "neurology"
    IMMUNOLOGY = "immunology"
    DERMATOLOGY = "dermatology"


class FailureMode(Enum):
    """Trial failure mode scenarios."""
    ENDPOINT_CHANGE = "endpoint_change"
    UNDERPOWERED = "underpowered"
    SUBGROUP_ONLY = "subgroup_only"
    ITT_PP_CONTRADICTION = "itt_pp_contradiction"
    IMPLAUSIBLE_EFFECT = "implausible_effect"
    MULTIPLE_INTERIMS = "multiple_interims"
    SINGLE_ARM_ISSUE = "single_arm_issue"
    P_VALUE_CUSP = "p_value_cusp"
    OS_PFS_CONTRADICTION = "os_pfs_contradiction"


@dataclass
class TestScenario:
    """Test scenario configuration."""
    name: str
    description: str
    trial_type: TrialType
    indication: Indication
    failure_modes: List[FailureMode]
    expected_signals: List[str]
    expected_gates: List[str]
    expected_risk_level: str  # "H", "M", "L"
    metadata: Optional[Dict[str, Any]] = None


class SyntheticDataGenerator:
    """Comprehensive synthetic data generator for testing."""
    
    def __init__(self, seed: Optional[int] = None):
        """
        Initialize the synthetic data generator.
        
        Args:
            seed: Random seed for reproducible generation
        """
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        
        self.drug_names = [
            "Pembrolizumab", "Nivolumab", "Atezolizumab", "Durvalumab", "Cemiplimab",
            "Bevacizumab", "Trastuzumab", "Rituximab", "Adalimumab", "Infliximab",
            "Paclitaxel", "Carboplatin", "Cisplatin", "Docetaxel", "Gemcitabine",
            "Sorafenib", "Sunitinib", "Pazopanib", "Regorafenib", "Lenvatinib"
        ]
        
        self.company_names = [
            "Merck", "Bristol-Myers Squibb", "Roche", "AstraZeneca", "Pfizer",
            "Novartis", "Johnson & Johnson", "AbbVie", "Gilead", "Amgen",
            "Eli Lilly", "GlaxoSmithKline", "Sanofi", "Biogen", "Regeneron"
        ]
        
        self.endpoint_types = [
            "Overall Survival", "Progression-Free Survival", "Objective Response Rate",
            "Disease-Free Survival", "Time to Progression", "Complete Response Rate",
            "Partial Response Rate", "Quality of Life", "Safety Run-in", "Pharmacokinetics"
        ]
    
    def generate_study_card(self, scenario: Optional[TestScenario] = None) -> Dict[str, Any]:
        """
        Generate a synthetic study card.
        
        Args:
            scenario: Test scenario to generate data for
            
        Returns:
            Synthetic study card dictionary
        """
        if scenario is None:
            scenario = self._random_scenario()
        
        study_card = {
            "study_id": f"SYNTH_{random.randint(1000, 9999)}",
            "is_pivotal": scenario.trial_type in [TrialType.PIVOTAL, TrialType.PHASE_3],
            "primary_type": random.choice(["proportion", "survival", "continuous"]),
            "single_arm": random.random() < 0.15,  # 15% single-arm trials
            "indication": scenario.indication.value,
            "phase": scenario.trial_type.value,
            "drug_name": random.choice(self.drug_names),
            "sponsor": random.choice(self.company_names),
        }
        
        # Generate arms data
        study_card["arms"] = self._generate_arms_data(scenario, study_card)
        
        # Generate analysis plan
        study_card["analysis_plan"] = self._generate_analysis_plan(scenario, study_card)
        
        # Generate primary result
        study_card["primary_result"] = self._generate_primary_result(scenario, study_card)
        
        # Generate subgroups if needed
        study_card["subgroups"] = self._generate_subgroups(scenario, study_card)
        
        # Add failure mode specific data
        self._add_failure_mode_data(study_card, scenario)
        
        return study_card
    
    def generate_trial_versions(self, study_card: Dict[str, Any], 
                               num_versions: int = 3) -> List[Dict[str, Any]]:
        """
        Generate trial version history.
        
        Args:
            study_card: Base study card
            num_versions: Number of versions to generate
            
        Returns:
            List of trial version dictionaries
        """
        versions = []
        base_date = datetime.now() - timedelta(days=365)
        
        for i in range(num_versions):
            version = {
                "version_id": f"v{i+1}",
                "trial_id": study_card["study_id"],
                "captured_at": base_date + timedelta(days=i*90),
                "raw_jsonb": study_card.copy(),
                "primary_endpoint_text": self._generate_endpoint_text(i),
                "sample_size": self._generate_sample_size_evolution(study_card, i),
                "analysis_plan_text": self._generate_analysis_plan_text(i),
                "changes_jsonb": self._generate_changes(i),
                "metadata": {
                    "version_number": i + 1,
                    "total_versions": num_versions,
                    "change_type": "major" if i == 0 else random.choice(["minor", "major", "administrative"])
                }
            }
            versions.append(version)
        
        return versions
    
    def generate_historical_data(self, num_trials: int = 100) -> List[Dict[str, Any]]:
        """
        Generate synthetic historical trial data for calibration.
        
        Args:
            num_trials: Number of historical trials to generate
            
        Returns:
            List of historical trial records
        """
        historical_data = []
        
        for i in range(num_trials):
            # Generate random scenario
            scenario = self._random_scenario()
            
            # Determine outcome based on failure modes
            actual_outcome = self._determine_outcome(scenario)
            
            # Generate fired gates based on scenario
            gates_fired, gate_severities = self._generate_gate_results(scenario)
            
            trial_record = {
                "trial_id": i + 1,
                "actual_outcome": actual_outcome,
                "gates_fired": gates_fired,
                "gate_severities": gate_severities,
                "is_pivotal": scenario.trial_type in [TrialType.PIVOTAL, TrialType.PHASE_3],
                "indication": scenario.indication.value,
                "phase": scenario.trial_type.value,
                "sponsor_experience": random.choice(["novice", "experienced", "experienced"]),  # Bias toward experienced
                "completion_date": datetime.now() - timedelta(days=random.randint(30, 1825)),
                "metadata": {
                    "scenario_name": scenario.name,
                    "failure_modes": [fm.value for fm in scenario.failure_modes],
                    "expected_risk": scenario.expected_risk_level
                }
            }
            
            historical_data.append(trial_record)
        
        return historical_data
    
    def _random_scenario(self) -> TestScenario:
        """Generate a random test scenario."""
        failure_modes = random.sample(list(FailureMode), k=random.randint(0, 3))
        
        # Determine expected signals and gates based on failure modes
        expected_signals = []
        expected_gates = []
        
        signal_mapping = {
            FailureMode.ENDPOINT_CHANGE: ["S1"],
            FailureMode.UNDERPOWERED: ["S2"],
            FailureMode.SUBGROUP_ONLY: ["S3"],
            FailureMode.ITT_PP_CONTRADICTION: ["S4"],
            FailureMode.IMPLAUSIBLE_EFFECT: ["S5"],
            FailureMode.MULTIPLE_INTERIMS: ["S6"],
            FailureMode.SINGLE_ARM_ISSUE: ["S7"],
            FailureMode.P_VALUE_CUSP: ["S8"],
            FailureMode.OS_PFS_CONTRADICTION: ["S9"],
        }
        
        for fm in failure_modes:
            expected_signals.extend(signal_mapping.get(fm, []))
        
        # Determine gates based on signals
        if "S1" in expected_signals and "S2" in expected_signals:
            expected_gates.append("G1")
        if "S3" in expected_signals and "S4" in expected_signals:
            expected_gates.append("G2")
        if "S5" in expected_signals and ("S6" in expected_signals or "S7" in expected_signals):
            expected_gates.append("G3")
        if "S8" in expected_signals and ("S1" in expected_signals or "S3" in expected_signals):
            expected_gates.append("G4")
        
        # Determine risk level
        if len(expected_gates) >= 2:
            risk_level = "H"
        elif len(expected_gates) == 1 or len(expected_signals) >= 3:
            risk_level = "M"
        else:
            risk_level = "L"
        
        return TestScenario(
            name=f"Scenario_{random.randint(1000, 9999)}",
            description=f"Random scenario with {len(failure_modes)} failure modes",
            trial_type=random.choice(list(TrialType)),
            indication=random.choice(list(Indication)),
            failure_modes=failure_modes,
            expected_signals=expected_signals,
            expected_gates=expected_gates,
            expected_risk_level=risk_level
        )
    
    def _generate_arms_data(self, scenario: TestScenario, study_card: Dict[str, Any]) -> Dict[str, Any]:
        """Generate arms data for the study card."""
        if study_card["single_arm"]:
            return {
                "t": {
                    "n": random.randint(50, 300),
                    "dropout": random.uniform(0.05, 0.25)
                }
            }
        else:
            # Add bias for dropout asymmetry if ITT_PP_CONTRADICTION in failure modes
            base_dropout_t = random.uniform(0.05, 0.20)
            base_dropout_c = random.uniform(0.05, 0.20)
            
            if FailureMode.ITT_PP_CONTRADICTION in scenario.failure_modes:
                # Create asymmetric dropout
                base_dropout_t += random.uniform(0.10, 0.25)
            
            # Adjust sample sizes based on failure modes
            n_t = random.randint(100, 500)
            n_c = random.randint(100, 500)
            
            # Make trials underpowered if UNDERPOWERED failure mode is present
            if FailureMode.UNDERPOWERED in scenario.failure_modes:
                # Reduce sample sizes to create underpowered trials
                n_t = int(n_t * 0.4)  # Reduce by 60%
                n_c = int(n_c * 0.4)  # Reduce by 60%
            
            return {
                "t": {
                    "n": n_t,
                    "dropout": round(base_dropout_t, 3)
                },
                "c": {
                    "n": n_c,
                    "dropout": round(base_dropout_c, 3)
                }
            }
    
    def _generate_analysis_plan(self, scenario: TestScenario, study_card: Dict[str, Any]) -> Dict[str, Any]:
        """Generate analysis plan data."""
        plan = {
            "alpha": random.choice([0.01, 0.025, 0.05]),
            "one_sided": random.random() < 0.3,  # 30% one-sided
            "assumed_p_c": round(random.uniform(0.15, 0.60), 3),
            "assumed_delta_abs": round(random.uniform(0.10, 0.30), 3),
        }
        
        # Add interim analysis data
        if FailureMode.MULTIPLE_INTERIMS in scenario.failure_modes:
            plan["planned_interims"] = random.randint(2, 5)
            plan["alpha_spending"] = None  # No alpha spending plan (problematic)
        else:
            plan["planned_interims"] = random.randint(0, 2)
            if plan["planned_interims"] > 0:
                plan["alpha_spending"] = random.choice([
                    "O'Brien-Fleming", "Pocock", "Lan-DeMets", "Custom"
                ])
        
        return plan
    
    def _generate_primary_result(self, scenario: TestScenario, study_card: Dict[str, Any]) -> Dict[str, Any]:
        """Generate primary result data."""
        # Base p-value
        if FailureMode.P_VALUE_CUSP in scenario.failure_modes:
            # Generate p-value in cusp range for S8
            p_value = round(random.uniform(0.045, 0.050), 4)
        else:
            # Generate normal p-value
            if random.random() < 0.7:  # 70% significant
                p_value = round(random.uniform(0.001, 0.04), 4)
            else:
                p_value = round(random.uniform(0.06, 0.30), 4)
        
        result = {
            "ITT": {
                "p": p_value,
                "estimate": round(random.uniform(0.05, 0.40), 3),
                "ci_lower": round(random.uniform(0.01, 0.15), 3),
                "ci_upper": round(random.uniform(0.20, 0.50), 3)
            }
        }
        
        # Add PP analysis if ITT_PP_CONTRADICTION in failure modes
        if FailureMode.ITT_PP_CONTRADICTION in scenario.failure_modes:
            # Make PP significantly different from ITT
            if result["ITT"]["p"] > 0.05:  # ITT non-significant
                pp_p = round(random.uniform(0.001, 0.04), 4)  # PP significant
            else:  # ITT significant
                pp_p = round(random.uniform(0.06, 0.30), 4)  # PP non-significant
            
            result["PP"] = {
                "p": pp_p,
                "estimate": round(random.uniform(0.05, 0.40), 3),
                "ci_lower": round(random.uniform(0.01, 0.15), 3),
                "ci_upper": round(random.uniform(0.20, 0.50), 3)
            }
        
        return result
    
    def _generate_subgroups(self, scenario: TestScenario, study_card: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate subgroup analysis data."""
        subgroups = []
        
        if FailureMode.SUBGROUP_ONLY in scenario.failure_modes:
            # Force overall result to be non-significant for subgroup-only scenario
            study_card["primary_result"]["ITT"]["p"] = round(random.uniform(0.06, 0.30), 4)
            
            # Generate subgroup-only win scenario
            subgroup = {
                "name": random.choice(["biomarker_positive", "high_expression", "mutation_positive"]),
                "n": random.randint(50, 200),
                "p": round(random.uniform(0.001, 0.04), 4),  # Significant subgroup
                "estimate": round(random.uniform(0.15, 0.50), 3),
                "multiplicity_adjusted": False,  # No multiplicity adjustment (problematic)
                "adjusted": False  # Also set adjusted to False for S3 signal
            }
            subgroups.append(subgroup)
        
        # Add random subgroups for realism
        for _ in range(random.randint(0, 3)):
            subgroup = {
                "name": f"subgroup_{random.randint(1, 10)}",
                "n": random.randint(30, 150),
                "p": round(random.uniform(0.01, 0.30), 4),
                "estimate": round(random.uniform(0.05, 0.40), 3),
                "multiplicity_adjusted": random.random() < 0.7  # 70% have adjustment
            }
            subgroups.append(subgroup)
        
        return subgroups
    
    def _add_failure_mode_data(self, study_card: Dict[str, Any], scenario: TestScenario) -> None:
        """Add failure mode specific data to study card."""
        # Endpoint change data
        study_card["endpoint_changed_after_lpr"] = FailureMode.ENDPOINT_CHANGE in scenario.failure_modes
        
        # PP-only success data
        study_card["pp_only_success"] = (
            FailureMode.ITT_PP_CONTRADICTION in scenario.failure_modes and
            "PP" in study_card["primary_result"] and
            study_card["primary_result"]["PP"]["p"] < 0.05 and
            study_card["primary_result"]["ITT"]["p"] >= 0.05
        )
        
        # Dropout asymmetry
        if "arms" in study_card and "c" in study_card["arms"]:
            dropout_t = study_card["arms"]["t"]["dropout"]
            dropout_c = study_card["arms"]["c"]["dropout"]
            study_card["dropout_asymmetry"] = abs(dropout_t - dropout_c)
        else:
            study_card["dropout_asymmetry"] = 0.0
        
        # Blinding data
        study_card["unblinded_subjective_primary"] = random.random() < 0.1  # 10% unblinded
        study_card["blinding_feasible"] = random.random() < 0.9  # 90% blinding feasible
    
    def _generate_endpoint_text(self, version_index: int) -> str:
        """Generate endpoint text for different versions."""
        base_endpoints = [
            "Overall survival defined as time from randomization to death",
            "Progression-free survival per RECIST 1.1 criteria",
            "Objective response rate by investigator assessment"
        ]
        
        if version_index == 0:
            return random.choice(base_endpoints)
        else:
            # Potentially changed endpoint
            if random.random() < 0.3:  # 30% chance of change
                return random.choice(base_endpoints)
            else:
                return random.choice(base_endpoints)
    
    def _generate_sample_size_evolution(self, study_card: Dict[str, Any], version_index: int) -> int:
        """Generate sample size evolution across versions."""
        base_size = study_card["arms"]["t"]["n"]
        if "c" in study_card["arms"]:
            base_size += study_card["arms"]["c"]["n"]
        
        # Sample size may change across versions
        change_factor = random.uniform(0.8, 1.2)
        return int(base_size * change_factor)
    
    def _generate_analysis_plan_text(self, version_index: int) -> str:
        """Generate analysis plan text for different versions."""
        plans = [
            "Primary analysis using log-rank test with alpha=0.05",
            "ITT analysis with sensitivity analysis on modified ITT population",
            "Hierarchical testing procedure for multiple endpoints"
        ]
        return random.choice(plans)
    
    def _generate_changes(self, version_index: int) -> Dict[str, Any]:
        """Generate changes between versions."""
        changes = {
            "version": version_index + 1,
            "change_summary": [],
            "major_changes": version_index == 0 or random.random() < 0.2
        }
        
        if version_index > 0:
            possible_changes = [
                "Sample size modification",
                "Endpoint clarification", 
                "Analysis plan update",
                "Inclusion criteria refinement",
                "Safety monitoring update"
            ]
            num_changes = random.randint(1, 3)
            changes["change_summary"] = random.sample(possible_changes, num_changes)
        
        return changes
    
    def _determine_outcome(self, scenario: TestScenario) -> bool:
        """Determine trial outcome based on scenario."""
        # Higher failure probability for more failure modes
        base_failure_prob = 0.15  # Base 15% failure rate
        
        # Increase probability based on failure modes
        failure_prob = base_failure_prob + len(scenario.failure_modes) * 0.15
        
        # Adjust for trial type
        if scenario.trial_type == TrialType.PHASE_3:
            failure_prob *= 1.3
        elif scenario.trial_type == TrialType.PIVOTAL:
            failure_prob *= 1.2
        
        # Adjust for indication
        if scenario.indication == Indication.ONCOLOGY:
            failure_prob *= 1.1
        elif scenario.indication == Indication.RARE_DISEASE:
            failure_prob *= 0.8
        
        # Cap at 90%
        failure_prob = min(failure_prob, 0.90)
        
        return random.random() < failure_prob
    
    def _generate_gate_results(self, scenario: TestScenario) -> Tuple[List[str], Dict[str, str]]:
        """Generate gate firing results based on scenario."""
        gates_fired = []
        gate_severities = {}
        
        # Gates fire based on expected gates from scenario
        for gate_id in scenario.expected_gates:
            if random.random() < 0.8:  # 80% chance of firing when expected
                gates_fired.append(gate_id)
                # Severity based on number of failure modes
                if len(scenario.failure_modes) >= 3:
                    gate_severities[gate_id] = "H"
                elif len(scenario.failure_modes) >= 2:
                    gate_severities[gate_id] = random.choice(["H", "M"])
                else:
                    gate_severities[gate_id] = "M"
        
        # Occasionally add unexpected gates (noise)
        all_gates = ["G1", "G2", "G3", "G4"]
        for gate_id in all_gates:
            if gate_id not in gates_fired and random.random() < 0.1:  # 10% false positive
                gates_fired.append(gate_id)
                gate_severities[gate_id] = random.choice(["M", "L"])
        
        return gates_fired, gate_severities


# Convenience functions
def generate_synthetic_study_card(scenario: Optional[TestScenario] = None, 
                                 seed: Optional[int] = None) -> Dict[str, Any]:
    """Generate a single synthetic study card."""
    generator = SyntheticDataGenerator(seed=seed)
    return generator.generate_study_card(scenario)


def generate_synthetic_trial_versions(study_card: Dict[str, Any], 
                                    num_versions: int = 3,
                                    seed: Optional[int] = None) -> List[Dict[str, Any]]:
    """Generate synthetic trial versions."""
    generator = SyntheticDataGenerator(seed=seed)
    return generator.generate_trial_versions(study_card, num_versions)


def generate_synthetic_historical_data(num_trials: int = 100,
                                      seed: Optional[int] = None) -> List[Dict[str, Any]]:
    """Generate synthetic historical data."""
    generator = SyntheticDataGenerator(seed=seed)
    return generator.generate_historical_data(num_trials)


def create_test_scenarios() -> List[TestScenario]:
    """Create predefined test scenarios for comprehensive testing."""
    scenarios = [
        # High-risk scenarios
        TestScenario(
            name="High_Risk_Oncology_Multiple_Issues",
            description="Phase 3 oncology trial with multiple failure modes",
            trial_type=TrialType.PHASE_3,
            indication=Indication.ONCOLOGY,
            failure_modes=[FailureMode.ENDPOINT_CHANGE, FailureMode.UNDERPOWERED, FailureMode.P_VALUE_CUSP],
            expected_signals=["S1", "S2", "S8"],
            expected_gates=["G1", "G4"],
            expected_risk_level="H"
        ),
        
        TestScenario(
            name="Analysis_Gaming_Pattern",
            description="Trial showing signs of analysis gaming",
            trial_type=TrialType.PIVOTAL,
            indication=Indication.CARDIOVASCULAR,
            failure_modes=[FailureMode.SUBGROUP_ONLY, FailureMode.ITT_PP_CONTRADICTION],
            expected_signals=["S3", "S4"],
            expected_gates=["G2"],
            expected_risk_level="H"
        ),
        
        # Medium-risk scenarios
        TestScenario(
            name="Underpowered_Trial",
            description="Trial with power issues",
            trial_type=TrialType.PHASE_3,
            indication=Indication.NEUROLOGY,
            failure_modes=[FailureMode.UNDERPOWERED],
            expected_signals=["S2"],
            expected_gates=[],
            expected_risk_level="M"
        ),
        
        TestScenario(
            name="Interim_Analysis_Issues",
            description="Trial with problematic interim analyses",
            trial_type=TrialType.PIVOTAL,
            indication=Indication.IMMUNOLOGY,
            failure_modes=[FailureMode.MULTIPLE_INTERIMS],
            expected_signals=["S6"],
            expected_gates=[],
            expected_risk_level="M"
        ),
        
        # Low-risk scenarios
        TestScenario(
            name="Clean_Phase_2",
            description="Well-designed phase 2 trial",
            trial_type=TrialType.PHASE_2,
            indication=Indication.RARE_DISEASE,
            failure_modes=[],
            expected_signals=[],
            expected_gates=[],
            expected_risk_level="L"
        ),
        
        TestScenario(
            name="Successful_Trial",
            description="Clean successful trial",
            trial_type=TrialType.PIVOTAL,
            indication=Indication.DERMATOLOGY,
            failure_modes=[],
            expected_signals=[],
            expected_gates=[],
            expected_risk_level="L"
        ),
        
        # Edge cases
        TestScenario(
            name="Single_Arm_Issues",
            description="Single-arm trial where RCT is standard",
            trial_type=TrialType.PIVOTAL,
            indication=Indication.ONCOLOGY,
            failure_modes=[FailureMode.SINGLE_ARM_ISSUE],
            expected_signals=["S7"],
            expected_gates=[],
            expected_risk_level="M"
        ),
        
        TestScenario(
            name="OS_PFS_Mismatch",
            description="Trial with OS/PFS contradiction",
            trial_type=TrialType.PHASE_3,
            indication=Indication.ONCOLOGY,
            failure_modes=[FailureMode.OS_PFS_CONTRADICTION],
            expected_signals=["S9"],
            expected_gates=[],
            expected_risk_level="M"
        )
    ]
    
    return scenarios
