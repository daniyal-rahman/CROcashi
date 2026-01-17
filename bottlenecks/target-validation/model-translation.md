# Model Translation Failure

## What We're Trying To Do

Use model systems (mice, cell lines, organoids) to predict which drugs will work in humans. The promise: test in models, advance winners, kill losers. The reality: models are poor predictors of human outcomes.

## Why It's Hard (First Principles)

### The Fundamental Problem

**From an evolutionary biologist's perspective:**

Mice and humans diverged ~75 million years ago. We share ~85% of protein-coding genes, but:
- Gene expression patterns differ
- Regulatory elements have diverged
- Immune systems differ substantially
- Metabolism differs (mice are 1000x smaller, 10x faster metabolism)
- Disease doesn't exist in mice the way it exists in humans

**The model organism assumption:** Conserved biology means conserved drug response.
**The reality:** Non-conserved details often determine drug response.

### Why Specific Model Types Fail

**1. Mouse genetic models (knockouts, transgenics)**
- Problem: Binary manipulation in different background
- Mouse knockout of X ≠ partial inhibition of human X
- Development, compensation differ between species
- *Clean genetics, wrong species*

**2. Mouse disease models (induced disease)**
- Problem: We induce a CARICATURE of disease
- EAE for MS: acute inflammation, not chronic demyelination
- DSS colitis for IBD: chemical damage, not immune-mediated
- Xenograft tumors: human cancer in immunodeficient mouse
- *We model what we CAN induce, not what patients HAVE*

**3. Cell lines (in vitro)**
- Problem: Clonal, immortalized, 2D, no stroma
- Lost heterogeneity of original tumor
- Adapted to plastic and media
- No immune context, no vasculature
- *They're cell lines, not cancer*

**4. Patient-derived xenografts (PDX)**
- Better: human tumor in mouse
- Still bad: mouse stroma replaces human; no human immune system
- Slow: takes months per model
- *Best we have for cancer, still limited*

**5. Organoids**
- Better: 3D, patient-derived, maintain some heterogeneity
- Still bad: no immune cells, no vasculature, no systemic factors
- Variable: reproducibility is challenging
- *Good for some questions, not for efficacy prediction*

### Barrier Decomposition

| Barrier | Why It Exists | Classification | Fixable? | What Would Fix It |
|---------|--------------|----------------|----------|-------------------|
| Species differences (fundamental) | 75M years evolution | Biology constraint | No | Use human systems or accept limitation |
| Disease model ≠ disease | We induce what we can | Design choice | Partially | Better models; spontaneous disease models |
| Immune system differs | Evolved differently | Biology constraint | Partially | Humanized mice; human immune components |
| Scale/metabolism differs | Mouse is 1000x smaller | Biology constraint | Accept | PK/PD translation; allometric scaling |
| Compensation/redundancy differs | Gene networks differ | Biology | Accept | Systems-level validation |
| Cell lines are artificial | Selection, adaptation | Design choice | Yes | Primary cells; organoids; patient-derived |
| No disease progression | Models are acute | Design choice | Partially | Longitudinal models; aged models |
| Endpoint ≠ clinical endpoint | We measure what we can | Design choice | Partially | Clinically relevant endpoints |

### Quantifying Translation Failure

**Oncology (tumor models → clinical efficacy):**
- Predictive value: ~5-10% (most preclinical hits fail in clinic)
- Response in xenograft: ~40-60% translate to any human response
- Complete response in xenograft: <5% translate to complete response in humans

**CNS (mouse behavior → human clinical):**
- Alzheimer's: >200 drugs worked in mice, 0 cured human AD
- Depression: Forced swim test → antidepressant? Questionable validity
- Stroke: >1000 neuroprotectants in mice, 0 in humans

**Immunology (mouse → human):**
- Generally better translation
- Still: anti-CD28 (TGN1412) cytokine storm not predicted
- Species differences in immune cell markers, responses

**Metabolic disease:**
- Best translation area
- Physiology more conserved
- Still: not 1:1

## What Works (Positive Deviants)

### 1. PK/PD Translation - The Success Story

**What works:**
- Drug metabolism and disposition reasonably predictable
- Allometric scaling (adjust for body size)
- In vitro human liver microsomes predict metabolism
- Plasma exposure-response often translates

**Why it works:**
- Pharmacokinetics is chemistry + biology
- Chemistry is conserved (drug is same molecule)
- Liver enzymes have human in vitro systems

**Key insight:** DRUG behavior translates better than DISEASE behavior.

### 2. Safety/Toxicity - Better Than Efficacy

**What works:**
- Toxicity often translates across species
- Carcinogenicity testing in rodents: ~70% concordance
- Liver toxicity: reasonable translation
- Cardiac (hERG): good prediction

**Why it works:**
- Toxicity targets conserved biology (liver, heart, kidneys)
- We're looking for BAD things at high doses
- False negatives more acceptable than for efficacy

**Key insight:** Predicting harm is easier than predicting benefit. Conserved physiology handles toxicity; disease-specific biology handles efficacy.

### 3. Antibiotics - High Translation

**What works:**
- In vitro MIC → in vivo efficacy reasonably predictive
- Bacterial targets well conserved
- Not testing human biology response, testing pathogen killing

**Why it works:**
- Target (bacteria) is conserved regardless of host
- Simple endpoint (kill bacteria)
- Not relying on host disease model validity

**Key insight:** When you're targeting the pathogen, not the host, translation is better.

### 4. Humanized Mouse Models - Partial Success

**What works:**
- Human immune system mice for immunotherapy
- Human liver chimeric mice for hepatitis
- Better than standard mice for specific questions

**Why it works:**
- Adding human components addresses species difference
- Limited to specific biological questions

**Key insight:** Humanization helps but doesn't solve fundamental disease model problems.

### 5. Natural History Comparison - Spontaneous Models

**What works:**
- Dogs get spontaneous osteosarcoma - better than induced
- Cats get hypertrophic cardiomyopathy - better than induced
- Old mice get cancer - more natural than xenografts

**Why it works:**
- Disease developed "naturally" through similar processes
- Better models of disease biology

**Key insight:** Spontaneous disease models translate better than induced models, but are slower and harder to work with.

## What Solving This Would Unlock

```
Predictive preclinical models (>50% translation)
↓
├── Kill bad drugs earlier
│   ├── 90% of failures identified preclinically instead of Phase 2/3
│   ├── Save $100M+ per failed program
│   └── Don't expose patients to drugs that won't work
│
├── Find more drugs
│   ├── Drugs that would work in humans but fail mice: discovered
│   ├── Expand target space (currently limited by model validity)
│   └── Mechanism-based combinations testable
│
├── Rare disease feasibility
│   ├── Can't run large trials; need predictive models
│   ├── Small patient populations require high-confidence candidates
│   └── Orphan drug development de-risked
│
└── Speed to patients
    ├── Less iteration on model-optimized compounds
    ├── Right drug advances faster
    └── Patients benefit years earlier
```

## What Specifically Blocks The Unlock

| Blocking Factor | Type | Who's Working On It | Status |
|-----------------|------|---------------------|--------|
| No fundamentally better model available | Tech gap | Organ-on-chip; organoids; humanized mice | Incremental |
| Regulatory requires animal models | Systemic | FDA modernization; NAMs acceptance | Slow change |
| "Model worked before" (survivor bias) | Framing | Some recognition | Cultural |
| Model development not rewarded | Systemic | Academic incentives | Misaligned |
| Induced disease models entrenched | Systemic | Model reform efforts | Slow |
| Species differences fundamental | Biology constraint | Can't fix | Accept |
| Field measures model endpoints not human endpoints | Framing | Endpoint reform | Beginning |

## Key Uncertainties

| Question | Why It Matters | How We'd Answer It |
|----------|---------------|-------------------|
| Which model properties predict translation? | Guide model selection | Meta-analysis of model features → clinical outcome |
| Can organoids replace animals? | Feasibility of shift | Head-to-head comparison studies |
| Is there a model-clinical translation law? | Predictability | Quantitative modeling |
| What fraction of drugs fail due to model choice? | Problem magnitude | Systematic failure attribution |
| Can AI learn the mouse→human translation function? | Computational solution | ML on paired preclinical-clinical data |

## Confidence Summary

**Biology constraints identified:** 3
- Species differences in disease biology (evolutionary divergence)
- Immune system differences (evolved differently)
- Scale/metabolism differences (cannot be fully compensated)

**Knowledge gaps:** 2
- Which model features predict translation
- How to build better models for specific diseases

**Tech gaps:** 3
- Human-relevant disease models for most diseases
- Scalable organoid/organ-on-chip systems
- In vivo imaging that's clinically translatable

**Framing problems:** 3 (major)
- "Worked in the model" as evidence (model has unknown validity)
- Measuring model endpoints not clinical endpoints
- Survivor bias: we remember when models predicted, forget when they didn't

**Systemic problems:** 2
- Regulatory requirements for animal data
- Academic incentives don't reward model improvement

## Bottom Line

Model translation failure is **significantly a biology constraint** - mice aren't humans, and this fundamentally limits predictability. But we make it WORSE through:

1. **Wrong disease models:** Induced models don't recapitulate disease
2. **Wrong endpoints:** Model endpoints ≠ clinical endpoints
3. **Survivor bias:** We ignore the vast majority of mouse successes that fail in humans

**What would help (but not solve):**
1. **Prioritize human genetic validation** - don't rely on mouse biology
2. **Use models for specific questions** - PK/PD, toxicity, mechanism - not efficacy prediction
3. **Humanized models** for specific applications (immune system, liver)
4. **Organoids and organ-on-chip** for human tissue responses
5. **Spontaneous disease models** where available
6. **Accept the limitation** - model data reduces uncertainty, doesn't eliminate it

**What we should NOT expect:**
- A model system that reliably predicts human efficacy
- This is fundamentally limited by species differences

**Prediction:** The field will shift toward:
- Human genetics as primary validation
- Models for mechanism, PK/PD, safety - not efficacy
- Earlier human experiments (Phase 0, microdosing)
- Regulatory acceptance of non-animal alternatives (slow)

**The hard truth:** Most preclinical efficacy data is not predictive of human outcomes. We use models because we have to start somewhere, not because they're predictive. The field has confused "necessary" with "sufficient."
