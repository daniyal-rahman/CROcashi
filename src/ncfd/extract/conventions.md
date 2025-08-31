# Study Card Conventions

This document defines standardized conventions for units, endpoints, assay cutoffs, and other values used throughout the study card system.

## Units Mapping

### Volume Units

| Unit | Full Name | Conversion to Base (ml) |
|------|-----------|-------------------------|
| `ml` | milliliter | 1.0 |
| `l` | liter | 1000.0 |
| `ul` | microliter | 0.001 |
| `nl` | nanoliter | 0.000001 |
| `pl` | picoliter | 0.000000001 |

### Weight Units

| Unit | Full Name | Conversion to Base (mg) |
|------|-----------|-------------------------|
| `mg` | milligram | 1.0 |
| `g` | gram | 1000.0 |
| `ug` | microgram | 0.001 |
| `ng` | nanogram | 0.000001 |
| `pg` | picogram | 0.000000001 |

### Concentration Units

| Unit | Full Name | Conversion to Base (mg/ml) |
|------|-----------|----------------------------|
| `mg/ml` | milligrams per milliliter | 1.0 |
| `g/l` | grams per liter | 1.0 |
| `ug/ul` | micrograms per microliter | 1.0 |
| `ng/ul` | nanograms per microliter | 0.001 |
| `mM` | millimolar | varies by compound |
| `uM` | micromolar | varies by compound |
| `nM` | nanomolar | varies by compound |

### Time Units

| Unit | Full Name | Conversion to Base (seconds) |
|------|-----------|------------------------------|
| `sec` | seconds | 1.0 |
| `min` | minutes | 60.0 |
| `hr` | hours | 3600.0 |
| `day` | days | 86400.0 |
| `week` | weeks | 604800.0 |
| `month` | months | 2592000.0 |
| `year` | years | 31536000.0 |

### Frequency Units

| Unit | Full Name | Conversion to Base (Hz) |
|------|-----------|-------------------------|
| `Hz` | hertz | 1.0 |
| `kHz` | kilohertz | 1000.0 |
| `MHz` | megahertz | 1000000.0 |

## Endpoint Mapping

### Primary Endpoints

| Canonical Name | Synonyms | Description |
|----------------|----------|-------------|
| `overall_survival` | OS, overall survival, survival | Time from randomization to death from any cause |
| `progression_free_survival` | PFS, progression-free survival | Time from randomization to disease progression or death |
| `disease_free_survival` | DFS, disease-free survival | Time from randomization to disease recurrence or death |
| `event_free_survival` | EFS, event-free survival | Time from randomization to any event of interest |
| `objective_response_rate` | ORR, objective response rate | Proportion of patients with complete or partial response |
| `complete_response_rate` | CRR, complete response rate | Proportion of patients with complete response |
| `partial_response_rate` | PRR, partial response rate | Proportion of patients with partial response |

### Secondary Endpoints

| Canonical Name | Synonyms | Description |
|----------------|----------|-------------|
| `duration_of_response` | DOR, duration of response | Time from response to progression |
| `time_to_response` | TTR, time to response | Time from randomization to first response |
| `quality_of_life` | QoL, quality of life, PRO | Patient-reported quality of life measures |
| `safety_events` | AE, adverse events, safety | Incidence and severity of adverse events |

### Biomarker Endpoints

| Canonical Name | Synonyms | Description |
|----------------|----------|-------------|
| `biomarker_level` | biomarker, marker level | Concentration or activity of biomarker |
| `target_engagement` | target engagement, engagement | Degree of target binding or modulation |
| `pharmacokinetics` | PK, pharmacokinetics | Drug concentration over time |
| `pharmacodynamics` | PD, pharmacodynamics | Drug effect over time |

## Assay Cutoffs

### Vector Genome Assays

| Assay Type | Units | Typical Cutoffs | Notes |
|------------|-------|-----------------|-------|
| `vg_per_cell` | vg/cell | ≥ 0.1, ≥ 1.0, ≥ 10.0 | Vector genomes per cell |
| `vg_per_ml` | vg/ml | ≥ 1e10, ≥ 1e11, ≥ 1e12 | Vector genomes per milliliter |
| `vg_per_mg` | vg/mg | ≥ 1e8, ≥ 1e9, ≥ 1e10 | Vector genomes per milligram tissue |

### Immunogenicity Assays

| Assay Type | Units | Typical Cutoffs | Notes |
|------------|-------|-----------------|-------|
| `neutralizing_antibodies` | titer | ≥ 1:10, ≥ 1:20, ≥ 1:100 | Neutralizing antibody titer |
| `binding_antibodies` | titer | ≥ 1:10, ≥ 1:20, ≥ 1:100 | Binding antibody titer |
| `t_cell_response` | spots/well | ≥ 50, ≥ 100, ≥ 200 | ELISpot or similar assay |

### Safety Assays

| Assay Type | Units | Typical Cutoffs | Notes |
|------------|-------|-----------------|-------|
| `liver_enzymes` | U/L | ≤ 3x ULN, ≤ 5x ULN | ALT, AST levels |
| `kidney_function` | mg/dL | ≤ 1.5x ULN | Creatinine levels |
| `platelet_count` | cells/ul | ≥ 50,000, ≥ 100,000 | Platelet count |

## Statistical Models

| Canonical Name | Aliases | Description |
|----------------|---------|-------------|
| `cox_proportional_hazards` | Cox PH, proportional hazards | Cox proportional hazards regression |
| `logistic_regression` | logistic, logit | Logistic regression analysis |
| `linear_regression` | linear, OLS | Ordinary least squares regression |
| `mixed_effects` | mixed model, LMM | Linear mixed effects model |
| `survival_analysis` | survival, KM | Kaplan-Meier survival analysis |
| `chi_square` | chi-squared, χ² | Chi-square test |
| `t_test` | t-test, Student's t | Student's t-test |
| `wilcoxon` | Wilcoxon, rank-sum | Wilcoxon rank-sum test |

## Analysis Sets

| Canonical Name | Aliases | Description |
|----------------|---------|-------------|
| `intention_to_treat` | ITT, intention to treat | All randomized patients |
| `per_protocol` | PP, per protocol | Patients who completed per protocol |
| `modified_itt` | mITT, modified ITT | Modified intention to treat |
| `safety_population` | safety, safety set | All treated patients |
| `evaluable_population` | evaluable, evaluable set | Patients with evaluable data |

## Population Characteristics

| Characteristic | Values | Description |
|----------------|--------|-------------|
| `age_group` | pediatric, adult, elderly | Age-based population grouping |
| `disease_stage` | early, intermediate, advanced | Disease progression stage |
| `prior_treatment` | naive, pretreated, refractory | Previous treatment history |
| `performance_status` | 0, 1, 2, 3, 4 | ECOG or Karnofsky performance status |
| `organ_function` | normal, mild, moderate, severe | Organ function impairment |

## Intervention Types

| Canonical Name | Aliases | Description |
|----------------|---------|-------------|
| `gene_therapy` | gene therapy, GT | Gene therapy intervention |
| `cell_therapy` | cell therapy, CT | Cell therapy intervention |
| `small_molecule` | small molecule, SM | Small molecule drug |
| `monoclonal_antibody` | mAb, monoclonal antibody | Monoclonal antibody |
| `vaccine` | vaccine, immunization | Vaccine or immunization |
| `device` | device, implant | Medical device or implant |

## Route of Administration

| Canonical Name | Aliases | Description |
|----------------|---------|-------------|
| `intravenous` | IV, intravenous | Intravenous administration |
| `intramuscular` | IM, intramuscular | Intramuscular administration |
| `subcutaneous` | SC, subcutaneous | Subcutaneous administration |
| `oral` | PO, oral | Oral administration |
| `intratumoral` | IT, intratumoral | Direct tumor injection |
| `intracranial` | IC, intracranial | Intracranial administration |

## Normalization Functions

The system provides functions for normalizing these values:

```python
from src.ncfd.extract.normalization import (
    normalize_units,
    normalize_endpoint_name,
    normalize_assay_type
)

# Normalize units
normalized_value = normalize_units(100, "ug", "mg")
# Result: 0.1 mg

# Normalize endpoint name
canonical_endpoint = normalize_endpoint_name("OS")
# Result: "overall_survival"

# Normalize assay type
canonical_assay = normalize_assay_type("vg/cell")
# Result: "vg_per_cell"
```

## Validation Rules

All values should be validated against these conventions:

```python
def validate_unit(unit: str) -> bool:
    """Validate unit against conventions."""
    valid_units = [
        # Volume units
        "ml", "l", "ul", "nl", "pl",
        # Weight units  
        "mg", "g", "ug", "ng", "pg",
        # Time units
        "sec", "min", "hr", "day", "week", "month", "year"
    ]
    return unit in valid_units

def validate_endpoint(endpoint: str) -> bool:
    """Validate endpoint against conventions."""
    valid_endpoints = [
        "overall_survival", "progression_free_survival",
        "disease_free_survival", "event_free_survival",
        "objective_response_rate", "complete_response_rate"
    ]
    return endpoint in valid_endpoints
```

## Extending Conventions

To add new conventions:

1. **Update this document** with the new convention
2. **Add normalization functions** in the normalization module
3. **Update validation rules** to include new values
4. **Add tests** for the new conventions
5. **Document migration** if existing values need to change

## Version History

- **v1.0.0** - Initial conventions established
- **v1.1.0** - Added biomarker endpoints and safety assays
- **v1.2.0** - Added population characteristics and intervention types
