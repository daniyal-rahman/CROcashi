# Model Organisms - Why Mice Don't Predict Humans

## What We're Trying To Do

Use mice (and other model organisms) to predict drug efficacy and safety in humans. The question is fundamental: can studying disease in one species predict treatment in another?

## Why It's Hard (First Principles)

### The Evolutionary Math

**From an evolutionary biologist's perspective:**

Mouse and human diverged ~75-80 million years ago. To understand why translation fails, consider what's conserved and what's not:

**What's conserved (~85% of genes):**
- Core cellular machinery (DNA replication, protein synthesis)
- Fundamental metabolic pathways
- Basic organ structures
- Many signaling pathways (at the component level)

**What's NOT conserved:**
- Regulatory sequences (when/where genes are expressed)
- Immune system details (different receptors, cell types, responses)
- Drug metabolism specifics (CYP450 isoforms differ)
- Disease susceptibility (mice don't naturally get most human diseases)
- Lifespan biology (mouse lives 2 years, human lives 80)
- Scale (mouse is 1000x smaller)

### The Specific Translation Gaps

**1. Immune System Differences**
```
Human immune feature          Mouse equivalent
TLR repertoire               ~70% similar, some differ
MHC Class I molecules        Similar structure, different specifics
NK cell receptors            Different families entirely
T cell subsets              Different balance
Neutrophil lifespan         Different (mouse shorter)
Antibody classes            Different (no IgD equivalent function)
```
- Implication: Immunotherapy, vaccines, inflammation responses vary

**2. Metabolic Differences**
- Mouse metabolic rate: ~10x human (per gram)
- Drug metabolism: Different CYP profiles
- Glucose handling: Mice more resistant to diabetes than humans
- Lifespan: Age-related diseases compressed/different

**3. Neurological Differences**
- Brain size: 500x smaller
- Cortical complexity: Much simpler
- Behavioral repertoire: Different, many human behaviors absent
- Neurotransmitter systems: Similar but not identical
- Implication: CNS drugs fail in translation at very high rates

**4. Disease Model Validity**

| Human Disease | Mouse "Model" | Translation Problem |
|--------------|---------------|---------------------|
| Alzheimer's | APP/PSEN transgenics | Mice don't get plaques naturally; no tangles in most models |
| Parkinson's | MPTP, 6-OHDA | Chemical damage ≠ progressive degeneration |
| ALS | SOD1 transgenic | Only models ~2% of human ALS (SOD1 mutations) |
| Depression | Forced swim test | Mice aren't depressed; test measures immobility |
| Stroke | MCAO | Acute, young mice; humans have chronic risk factors |
| Cancer | Xenografts | Immunodeficient mice; human tumor in foreign stroma |
| Sepsis | CLP, LPS | Mouse immune response fundamentally different |

### Barrier Decomposition

| Barrier | Why It Exists | Classification | Fixable? | What Would Fix It |
|---------|--------------|----------------|----------|-------------------|
| Species divergence (75M years) | Evolution | Biology constraint | No | Accept; use multiple species; prioritize human data |
| Immune system differences | Different selective pressures | Biology constraint | Partially | Humanized mice; human immune system components |
| Disease model artificiality | Can't induce human disease | Design choice | Partially | Better models; spontaneous disease; aged animals |
| Scale/metabolism | Body size, lifespan | Biology constraint | Model | Allometric scaling; PK/PD translation |
| Behavior/cognition | Brain complexity | Biology constraint | Partially | Primate models for CNS; human behavior studies |
| Genetic background variation | Inbred mice ≠ diverse humans | Design choice | Yes | Diversity panels; outbred mice |
| Environment (SPF housing) | Experimental control | Design choice | Partially | "Dirty" mice; realistic conditions |
| Single time point disease | Want clean experiment | Design choice | Yes | Longitudinal studies; aged models |

### Quantifying Translation Failure

**Therapeutic area translation rates (mouse → human):**

| Area | Success Rate | Why |
|------|-------------|-----|
| Infectious disease | ~40-50% | Pathogen is target, not host |
| Oncology | ~5-10% | Different tumor biology; immune context |
| CNS | ~5-10% | Maximum species differences |
| Immunology | ~20-30% | Important differences in immune system |
| Cardiovascular | ~30-40% | More conserved physiology |
| Metabolic | ~40-50% | More conserved physiology |

## What Works (Positive Deviants)

### 1. Toxicity Prediction - Better Than Efficacy

**What works:**
- Acute toxicity: ~70% concordance
- Carcinogenicity: ~60-70% concordance
- Organ toxicity (liver, kidney): reasonable prediction

**Why it works:**
- Conserved physiology handles toxic insults similarly
- High doses create obvious damage
- We're looking for BAD effects, not subtle efficacy

**Key insight:** Predicting harm is easier than predicting benefit.

### 2. Pharmacokinetics - The Translation Success

**What works:**
- ADME (absorption, distribution, metabolism, excretion) reasonably predictable
- Allometric scaling adjusts for body size
- In vitro human systems (hepatocytes, microsomes) improve prediction

**Why it works:**
- PK is chemistry + biology
- The drug molecule is identical across species
- Scaling laws are understood

**Key insight:** Drug behavior translates better than disease behavior.

### 3. Spontaneous Cancer Models (Dogs) - Better Fit

**What works:**
- Dogs get spontaneous osteosarcoma, melanoma, lymphoma
- Similar tumor biology to humans
- Pet dogs are outbred, diverse, aged
- Tumor microenvironment includes real immune system

**Why it works:**
- Disease arose naturally through similar processes
- Not artificial induction
- Real immune context

**Key insight:** Spontaneous disease models translate better than induced models.

### 4. Large Animal Models for Devices/Surgery

**What works:**
- Pigs for cardiovascular devices (similar heart size)
- Sheep for orthopedic implants (similar bone structure)
- Primates for neurological procedures

**Why it works:**
- Physical scale matches humans
- Not testing drug mechanism, testing physical interaction

**Key insight:** When the question is physical/mechanical (not molecular mechanism), large animals can work.

### 5. Humanized Mouse Models - Partial Success

**What works:**
- Human immune system mice for immunotherapy (partial)
- Human liver chimeric mice for hepatitis
- Human tumor xenografts with human stroma

**Why it works:**
- Adding human components addresses specific translation gaps
- Useful for specific questions

**Limitations:**
- Complex to make and maintain
- Incomplete humanization
- Doesn't solve disease model problem

## What Solving This Would Unlock

```
Predictive model organisms
↓
├── Earlier go/no-go decisions
│   ├── Kill drugs that would fail in humans
│   ├── Advance drugs that would work in humans
│   └── Save billions in failed Phase 2/3
│
├── Fewer false negatives
│   ├── Drugs that work in humans but failed mice: discovered
│   ├── Expanded therapeutic options
│   └── Rescue "failed" compounds
│
├── Mechanism understanding
│   ├── Use models for mechanism, accept efficacy limits
│   ├── Better integration of model and human data
│   └── Appropriate model for appropriate question
│
└── Ethical implications
    ├── Fewer animals used for non-predictive studies
    ├── Better 3Rs implementation
    └── Alternative methods where models fail
```

## What Specifically Blocks The Unlock

| Blocking Factor | Type | Who's Working On It | Status |
|-----------------|------|---------------------|--------|
| No fundamentally better model exists | Biology constraint | Cannot fully fix | Accept |
| Regulatory requirements | Systemic | FDA modernization | Slow |
| Model inertia ("we always use X model") | Systemic | Cultural change | Very slow |
| Better models more expensive/slow | Economics | Trade-offs | Ongoing |
| Human disease etiology unknown | Knowledge gap | Basic research | Ongoing |
| Genetic background effects | Design choice | Diversity panels | Improving |
| SPF vs. real-world immune development | Design choice | "Dirty" mice | Emerging |
| Academic incentives favor model organisms | Systemic | Science reform | Minimal |

## Key Uncertainties

| Question | Why It Matters | How We'd Answer It |
|----------|---------------|-------------------|
| What fraction of failures are due to species vs. other factors? | Attribution | Systematic failure analysis |
| Can we identify which questions mice CAN answer? | Strategic model use | Meta-analysis by question type |
| Will organoids/organs-on-chip replace animals? | Future direction | Head-to-head validation |
| Can AI learn mouse-human translation function? | Computational fix | ML on paired data |
| Would different species translate better? | Model choice | Comparative studies |

## Confidence Summary

**Biology constraints identified:** 4
- 75 million years evolutionary divergence (irreducible)
- Immune system fundamental differences (irreducible)
- Brain complexity differences for CNS (irreducible)
- Disease etiology differences (many human diseases don't exist in mice)

**Knowledge gaps:** 2
- Which aspects of mouse biology DO translate
- How to build disease models that recapitulate human pathophysiology

**Tech gaps:** 2
- Humanized models that fully recapitulate human biology
- Scalable organoid/organ-on-chip systems

**Framing problems:** 3
- Treating all species differences as equal (some matter more than others)
- "Worked in mice" as validation (it's not)
- Using models to de-risk when they don't (false confidence)

**Design problems:** 2
- Inbred, young, SPF mice ≠ diverse, aged, pathogen-exposed humans
- Induced disease models ≠ natural disease

## Bottom Line

Model organism translation failure is **significantly a biology constraint**. Mice and humans are different organisms, and this cannot be engineered away. However, we make it WORSE through:

1. **Using wrong models for wrong questions** - induced models for disease mechanism
2. **Ignoring known limitations** - pretending mouse efficacy predicts human efficacy
3. **Not leveraging human data** - genetics, human tissues, early clinical data

**Strategic framework:**

| Use mice for | Don't use mice for |
|--------------|-------------------|
| Safety/toxicity | Efficacy prediction |
| PK/PD (with translation) | Complex disease outcomes |
| Target engagement | Behavioral/CNS endpoints |
| Mechanism studies | Immune response prediction |
| Dose selection | Final go/no-go |

**What would actually help:**
1. **Human genetics FIRST** - validate target in humans before mice
2. **Right model for right question** - don't expect mice to predict human efficacy
3. **Earlier human data** - Phase 0, microdosing, human tissue studies
4. **Humanized/spontaneous models** - where available and relevant
5. **Transparent failure analysis** - learn from what didn't translate

**Prediction:** The field will NOT find a better general model organism. Instead, it will:
- Reduce reliance on mouse efficacy data
- Increase use of human genetics, tissues, early clinical data
- Accept that efficacy prediction requires human data
- Use models for mechanism, safety, PK - not efficacy

**The hard truth:** After 40+ years, mice still don't predict human efficacy for most diseases. The field has been "hoping for better translation" when the biology says it's not coming. We need to work around the limitation, not pretend it will disappear.
