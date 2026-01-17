# Cascade Map: What Unlocks What

## Overview

Drug development bottlenecks are interconnected. Solving one problem can unlock multiple downstream benefits, while some problems are gated by others. This document maps the dependencies and cascade effects.

## Primary Cascade Chains

### Chain 1: Delivery → Modality Expansion

```
Endosomal Escape Solved (>30% efficiency)
↓
├── RNA therapeutics dose reduced 10-30x
│   ↓
│   └── Chronic RNA therapy viable
│       ↓
│       └── Genetic diseases addressable at scale
│
├── Intracellular protein delivery enabled
│   ↓
│   └── Transcription factors deliverable
│       ↓
│       └── "Undruggable" targets become druggable via protein delivery
│
└── Gene editing efficiency increased
    ↓
    └── In vivo editing practical for more indications
```

### Chain 2: Targeting → Toxicity Reduction

```
Tissue-Specific Delivery Solved (non-liver LNPs)
↓
├── Systemic toxicity reduced
│   ↓
│   └── Higher therapeutic doses possible
│       ↓
│       └── Modest efficacy drugs become viable
│
├── Gene therapy to non-liver organs
│   ↓
│   └── Neurodegenerative diseases addressable
│       ↓
│       └── CNS drug development transformed
│
└── Immunotherapy localized
    ↓
    └── Autoimmune diseases targetable without systemic immunosuppression
```

### Chain 3: Validation → Portfolio Efficiency

```
Reliable Target Validation (>70% Phase 2 prediction)
↓
├── Portfolio prioritization improved
│   ↓
│   └── Resources focused on validated targets
│       ↓
│       └── "Undruggable" validated targets get more chemistry investment
│
├── Fewer Phase 3 failures
│   ↓
│   └── R&D cost per approved drug drops
│       ↓
│       └── More diseases economically viable to pursue
│
└── Genetic targets prioritized
    ↓
    └── Drug development pipeline shifts to human-genetics-first
        ↓
        └── Mouse models used appropriately (mechanism, not efficacy)
```

### Chain 4: Heterogeneity → Precision Medicine

```
Patient Heterogeneity Understood
↓
├── Responder prediction
│   ↓
│   └── Smaller, faster trials in selected population
│       ↓
│       └── Rare disease drug development viable
│
├── Failed drugs rescued
│   ↓
│   └── Subset responders identified retroactively
│       ↓
│       └── Sunk R&D costs recovered
│
└── Rational combinations
    ↓
    └── Non-responders get different treatment
        ↓
        └── Population-level efficacy increased
```

## Cross-Domain Cascades

### Delivery Enables Validation
```
Intracellular Delivery Solved
↓
└── Can test any intracellular target
    ↓
    └── Genetic validation → immediate therapeutic testing
        ↓
        └── Target validation cycle accelerated
```

### Validation Enables Delivery Investment
```
Target Highly Validated
↓
└── Justifies hard chemistry/delivery investment
    ↓
    └── "Undruggable" targets receive resources
        ↓
        └── New modalities developed for specific targets
```

### Model Translation Failure → Human Genetics Primacy
```
Model Organism Failure Accepted
↓
└── Human genetics prioritized for validation
    ↓
    └── Mendelian randomization becomes standard
        ↓
        └── Target validation reliability increases
```

## Bottleneck Dependencies

### What's Gated (Can't Solve Without Solving Prerequisite)

| Bottleneck | Gated By | Implication |
|------------|----------|-------------|
| Non-liver RNA therapeutics | Tissue targeting | Can't deliver RNA outside liver without solving targeting |
| Intracellular protein therapeutics | Endosomal escape | Low escape = proteins destroyed |
| CNS drug development | BBB crossing | Must solve delivery first |
| "Undruggable" targets via degradation | PROTAC PK/delivery | Large molecules face delivery hurdles |
| Surrogate endpoint validation | Patient heterogeneity understanding | Surrogates may only work in subsets |
| Adaptive trials | Predictive biomarkers | Can't enrich without knowing who responds |

### What's Independent (Can Be Solved In Parallel)

| Bottleneck A | Bottleneck B | Why Independent |
|--------------|--------------|-----------------|
| Oral biologics | Tissue targeting | Different delivery routes, different biology |
| Target validation (genetics) | Endosomal escape | Different domains |
| Phase 2/3 gap (design) | Model organism translation | Design vs. preclinical |
| PROTAC chemistry | LNP formulation | Different modalities |

## Highest-Value Cascade Origins

These problems, if solved, would unlock the most downstream value:

### Tier 1: Maximum Cascade Impact

1. **Endosomal Escape**
   - Unlocks: RNA therapeutics, protein therapeutics, gene editing efficiency
   - Current state: 1-2% efficiency
   - Cascade multiplier: >10x

2. **Tissue-Specific Delivery (Non-Liver)**
   - Unlocks: CNS, tumors, autoimmune target organs
   - Current state: 80% goes to liver
   - Cascade multiplier: >5x

3. **Predictive Target Validation**
   - Unlocks: Portfolio prioritization, "undruggable" investment, rare disease viability
   - Current state: ~30% Phase 2 success
   - Cascade multiplier: ~3x

### Tier 2: High Cascade Impact

4. **Patient Responder Identification**
   - Unlocks: Precision medicine, failed drug rescue, smaller trials
   - Current state: Most trials don't stratify
   - Cascade multiplier: ~3x

5. **Oral Biologics**
   - Unlocks: Patient compliance, new therapeutic windows, cost reduction
   - Current state: Oral semaglutide is exception
   - Cascade multiplier: ~2x

### Tier 3: Moderate Cascade Impact

6. **Phase 2/3 Translation (Design)**
   - Unlocks: More efficient development, fewer patient exposures to futility
   - Current state: ~30% translation
   - Cascade multiplier: ~2x

7. **"Undruggable" Targets**
   - Unlocks: KRAS-like targets, transcription factors
   - Current state: ~20% of proteome druggable
   - Cascade multiplier: ~2x

## Cascade Interference

Some solutions may negatively impact other areas:

| Solution | Potential Interference |
|----------|----------------------|
| PROTAC/degraders | Large molecules face delivery challenges |
| Permeation enhancers (oral) | May cause local GI inflammation |
| Adaptive trial designs | Increase operational complexity |
| Human genetics-first | Requires new infrastructure/skills |
| External triggering (FUS, light) | Limited by tissue access |

## Strategic Implications

### Where To Invest for Maximum Impact

1. **Endosomal escape mechanisms** - Unlocks most modalities
2. **SORT/non-liver LNP targeting** - Unlocks tissue targeting
3. **Human genetics infrastructure** - Unlocks validation confidence

### Where NOT To Invest (Low Cascade)

1. **Better mouse models** - Fundamental limitation; won't cascade
2. **Incremental PK optimization** - Mature field; diminishing returns
3. **Single target chemistry programs** - Limited generalizability

### Sequencing Matters

```
Recommended sequence for maximum leverage:

Year 0-3: Endosomal escape research (foundational)
         Target validation infrastructure (genetics)

Year 3-7: Non-liver LNP targeting (builds on escape)
         Patient stratification tools (builds on validation)

Year 7+:  Intracellular protein delivery (requires escape + targeting)
         Organ-specific gene editing (requires all above)
```

## Summary Cascade Diagram

```
                    ┌─────────────────────────────────────────────────────────┐
                    │              DRUG DEVELOPMENT BOTTLENECK CASCADE          │
                    └─────────────────────────────────────────────────────────┘
                                              │
           ┌──────────────────────────────────┼──────────────────────────────────┐
           │                                  │                                  │
     ┌─────▼─────┐                   ┌────────▼────────┐               ┌────────▼────────┐
     │ DELIVERY  │                   │   VALIDATION    │               │  TRANSLATION    │
     └─────┬─────┘                   └────────┬────────┘               └────────┬────────┘
           │                                  │                                  │
    ┌──────┼──────┐              ┌────────────┼────────────┐          ┌─────────┼─────────┐
    │      │      │              │            │            │          │         │         │
    ▼      ▼      ▼              ▼            ▼            ▼          ▼         ▼         ▼
 Endosomal Tissue  Oral      Genetic    Undruggable   Model      Phase2/3  Surrogate  Patient
 Escape  Targeting Biologics  vs.Pheno   Targets     Organisms   Gap      Endpoints  Hetero
    │      │      │              │            │            │          │         │         │
    └──────┴──────┴──────────────┴────────────┴────────────┴──────────┴─────────┴─────────┘
                                              │
                                              ▼
                              ┌────────────────────────────────┐
                              │        CASCADE EFFECTS          │
                              │  • RNA therapeutics scaled      │
                              │  • Gene editing practical       │
                              │  • CNS diseases addressable     │
                              │  • Portfolio efficiency >2x     │
                              │  • Rare diseases viable         │
                              │  • Failed drugs rescued         │
                              └────────────────────────────────┘
```
