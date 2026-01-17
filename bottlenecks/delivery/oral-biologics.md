# Oral Biologics

## What We're Trying To Do

Deliver protein therapeutics (antibodies, peptides, enzymes, nucleic acids) via the oral route instead of injection. This would transform patient compliance, reduce healthcare costs, and enable indications where daily/continuous dosing is needed.

## Why It's Hard (First Principles)

### The Biology/Physics/Chemistry

**From a physicist's perspective:**

The GI tract is an external-internal interface optimized for one job: break complex organic molecules into components, absorb what's useful, exclude what's harmful. A 150 kDa antibody hitting this system faces:

1. **Chemical degradation** (thermodynamics + enzymatic catalysis)
   - Stomach pH 1-3 denatures tertiary structure (thermodynamically favored unfolding)
   - Pepsin cleaves after hydrophobic residues (Phe, Tyr, Trp, Leu)
   - Small intestine: trypsin (after Lys, Arg), chymotrypsin (after aromatics), carboxypeptidases
   - Half-life of unprotected protein in gastric fluid: minutes
   - *This is what the GI tract evolved to do*

2. **Physical barrier** (epithelial tight junctions)
   - Paracellular pores: ~4-8 Å (allow ions, small molecules)
   - Antibody: ~150 Å diameter
   - Physical size exclusion: >99.99% of large molecules rejected
   - *But: barrier is not absolute - transcytosis, M-cells exist*

3. **Transport kinetics** (competing with degradation)
   - Transit time through stomach: 0.5-4 hours
   - Transit through small intestine: 3-5 hours
   - Absorption window for large molecules: limited regions (ileum, Peyer's patches)
   - Race condition: absorption must happen faster than degradation

4. **First-pass metabolism**
   - Portal vein → liver before systemic circulation
   - Hepatic extraction for some peptides
   - *But: lymphatic absorption bypasses this*

### Barrier Decomposition

| Barrier | Why It Exists | Classification | Fixable? | What Would Fix It |
|---------|--------------|----------------|----------|-------------------|
| Gastric acid denaturation | pH 1-3 unfolds proteins thermodynamically | Physics constraint | Yes | Enteric coating (standard tech, solved) |
| Pepsin/protease degradation | Evolved function of GI tract to digest proteins | Biology constraint (partial) | Partially | Protease inhibitors co-administration; enzyme-resistant analogs; encapsulation |
| Tight junction exclusion | Epithelium evolved to be selective barrier | Biology constraint (partial) | Partially | Permeation enhancers; transcytosis hijacking; target M-cells |
| Mucus layer | Physical barrier ~100-800 μm, traps particles | Biology constraint (partial) | Yes | Mucus-penetrating nanoparticles; mucolytic co-admin |
| Molecular size (>500 Da cutoff) | Paracellular pores physically small | Physics constraint | No (for that route) | Use transcellular route instead (reframe) |
| Low bioavailability (~1-2%) | Multiple barriers compound | Aggregate effect | Partially | Potency × absorption optimization; accept low bioavailability if drug is potent enough |
| Inter-patient variability | Fed/fasted state, pH variation, transit time | Biology + environment | Partially | Standardized dosing conditions; adaptive formulations |

### Key Insight: The "Biology Constraint" Test

**Is gastric degradation a true biology constraint?**
- If we completely protected a protein from degradation, would this create a paradox? NO
- The GI tract doesn't "need" to destroy therapeutic proteins - it's collateral damage
- **Classification: Biology constraint that CAN be circumvented without paradox**

**Is the epithelial barrier a true biology constraint?**
- If we got a protein across the epithelium, would this break something fundamental? NO
- Natural mechanisms exist (transcytosis, M-cells) that transport macromolecules
- The barrier is semi-permeable, not absolute
- **Classification: Partial biology constraint - workarounds exist**

## What Works (Positive Deviants)

### 1. Oral Semaglutide (Rybelsus) - The Proof of Concept

**What it is:** GLP-1 analog + SNAC (sodium N-[8-(2-hydroxybenzoyl) amino] caprylate)

**Why it works when it shouldn't:**
- SNAC creates local pH microenvironment (~neutral) protecting semaglutide
- SNAC may enhance transcellular absorption (mechanism not fully characterized)
- Semaglutide is already highly potent (active at low nM), so ~1% bioavailability is sufficient
- Modified to resist DPP-4 degradation

**Key insight:** You don't need high bioavailability if your drug is potent enough. The field was framing the problem as "get more across" when the real frame is "get enough across for efficacy."

### 2. Cyclosporine (Sandimmune/Neoral)

**What it is:** Cyclic peptide (11 amino acids), immunosuppressant

**Why it works:**
- Cyclic structure resistant to proteases
- Highly lipophilic (logP ~3) - crosses via transcellular route
- N-methylation of 7 amides reduces hydrogen bonding, improves membrane permeability

**Key insight:** Molecular engineering can create peptides that don't follow rules derived from average peptides.

### 3. Octreotide (in development - Chiasma/Mycapssa)

**What it is:** Somatostatin analog with transient permeability enhancer (TPE)

**Why it's notable:**
- Uses medium-chain fatty acids to transiently open tight junctions
- Shows that the "impermeable barrier" can be made permeable

### 4. Natural oral tolerance mechanisms

**The paradox:** We CAN absorb intact proteins orally - that's how oral immunotherapy works. Antigen sampling in Peyer's patches requires intact protein transport.

**Key insight:** The gut is not absolutely impermeable to proteins. The question is quantitative (how much) not qualitative (whether).

## What Solving This Would Unlock

```
Oral biologics solved
↓
├── Patient compliance transformation
│   ├── Chronic diseases become manageable (no injection burden)
│   ├── Pediatric formulations feasible
│   └── Self-administration in low-resource settings
│
├── New therapeutic windows
│   ├── Daily dosing of short-half-life biologics
│   ├── Meal-time insulin possible
│   └── GI-local delivery (IBD, gut infections)
│
├── Cost structure change
│   ├── No cold chain required (stable formulations)
│   ├── No healthcare worker for administration
│   └── Manufacturing shift from sterile injectables
│
└── New drug classes enabled
    ├── Oral mRNA (gut-local or systemic)
    ├── Oral antibodies for GI targets
    └── Oral enzymes for metabolic diseases
```

## What Specifically Blocks The Unlock

| Blocking Factor | Type | Who's Working On It | Status |
|-----------------|------|---------------------|--------|
| SNAC mechanism not fully understood | Knowledge gap | Academic labs, Novo Nordisk | Partial - empirically works, mechanism unclear |
| Permeation enhancers cause local inflammation | Tech gap + safety | Chiasma, Enteris, many startups | Mixed results - need safer enhancers |
| Bioavailability too low for less potent drugs | Design constraint | Entire field | Partially solved - engineer potency |
| Inter-patient variability too high | Knowledge gap | Clinical development teams | Active area - need predictive biomarkers |
| No general platform for antibodies | Tech gap | Rani Therapeutics (injection), others | Early stage - no proven solution yet |
| Formulation stability challenges | Tech gap | Formulation companies | Partially solved - case by case |
| Regulatory path unclear for enhancers | Regulatory gap | FDA, EMA engagement | Evolving - oral semaglutide set precedent |

## Key Uncertainties

| Question | Why It Matters | How We'd Answer It |
|----------|---------------|-------------------|
| What is SNAC's actual mechanism? | Would enable rational design of better enhancers | Structural biology + transport studies in tissue |
| What's the ceiling for transcellular absorption? | Determines if route is viable for antibodies | Systematic study of uptake vs. molecular properties |
| Can we target FcRn in gut for transcytosis? | Natural mechanism for IgG transport | Test FcRn-binding variants in gut tissue models |
| Is local inflammation from enhancers acceptable? | Safety/efficacy tradeoff | Long-term clinical studies with histology |
| What predicts responders vs. non-responders? | Enable patient selection or adaptive dosing | Biomarker studies in semaglutide patients |

## Confidence Summary

**Biology constraints identified:** 2 (partial)
- GI proteolytic environment (circumventable with protection)
- Epithelial barrier (circumventable with enhancers/transcytosis)

**Knowledge gaps:** 3
- SNAC/enhancer mechanism of action
- Optimal transcytosis pathway to hijack
- Predictors of inter-patient variability

**Tech gaps:** 4
- Safe, effective permeation enhancers
- General antibody oral delivery platform
- Stable solid formulations for labile proteins
- Manufacturing at scale with enhancers

**Framing problems:** 1 (major)
- Field optimizes for bioavailability % when they should optimize for (bioavailability × potency) - oral semaglutide proves 1% is enough if drug is potent

## Bottom Line

Oral biologics is **NOT** blocked by fundamental biology constraints. The GI tract's proteolytic and barrier functions can be circumvented without creating paradoxes. The real blockers are:

1. **Knowledge gap:** We don't fully understand what makes oral semaglutide work
2. **Framing:** The field chases high bioavailability when potency × bioavailability is what matters
3. **Tech gap:** No general platform yet, solutions are case-by-case

**Prediction:** Oral biologics will become routine for peptides within 10 years, following the semaglutide playbook (high potency + enhancer). Oral antibodies will require new approaches (likely transcytosis hijacking or physical delivery devices).
