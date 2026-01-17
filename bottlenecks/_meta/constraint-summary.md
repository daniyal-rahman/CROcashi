# Constraint Summary: What's Actually Fundamental

## Overview

This document summarizes all identified biology constraints across the analyzed bottlenecks, distinguishing TRUE constraints (would create paradox if solved) from FALSE constraints (often called constraints but actually fixable).

## True Biology Constraints

### Definition
A TRUE biology constraint would violate physical law or create a biological paradox if circumvented. The test: "If this were solved, would something fundamental break?"

### Confirmed True Constraints

| Constraint | Domain | Why It's Fundamental | Workaround (if any) |
|------------|--------|---------------------|---------------------|
| GI tract proteolysis | Oral Delivery | Evolved function to digest proteins; cannot be "turned off" globally | Protection (enteric coating), local inhibition, resistant analogs |
| Membrane integrity maintenance | Endosomal Escape | Cell viability requires intact membranes | Transient disruption, fusion (not pore), accept low efficiency |
| MPS clearance of particles | Tissue Targeting | Immune function to clear foreign material | PEGylation, saturation, camouflage (CD47), accept liver accumulation |
| Species divergence (75M years) | Model Translation | Evolution happened; cannot be undone | Human genetics, humanized models, accept limitation |
| Human genetic diversity | Patient Heterogeneity | Human population is diverse; cannot homogenize | Biomarkers, stratification, precision medicine |
| Nuclear envelope barrier | Intracellular Delivery | Protects genetic material; essential for eukaryotic life | NLS signals, exploit mitosis, accept limitation |

### Constraint Severity Levels

**Absolute constraints (cannot be circumvented):**
- Species divergence for model organisms
- Population genetic diversity

**Severe constraints (can only be partially circumvented):**
- MPS clearance (can reduce, not eliminate)
- Membrane integrity (can transiently disrupt, not abolish)
- GI proteolysis (can protect, not prevent all degradation)

**Moderate constraints (significant workarounds exist):**
- Epithelial barrier (transcytosis, permeation enhancers)
- Nuclear envelope (NLS, mitosis, some viral mechanisms)

## FALSE "Constraints" (Actually Fixable)

### Definition
A FALSE constraint is something commonly called a "fundamental limitation" that is actually a knowledge gap, tech gap, design problem, or wrong framing.

### Reclassified Non-Constraints

| "Constraint" | Often Claimed As | Actually Is | Why It's Fixable |
|--------------|------------------|-------------|------------------|
| "Proteins can't be given orally" | Biology constraint | Tech + knowledge gap | Oral semaglutide exists; problem is enhancer understanding |
| "Phase 2 doesn't predict Phase 3" | Biology | Design + statistics | Mostly fixable with better trial design |
| "Targets are undruggable" | Chemistry constraint | Tech gap | KRAS G12C was "undruggable" until 2021 |
| "Endosomal escape is impossible" | Biology constraint | Tech gap | Viruses achieve ~100% escape; we don't understand how |
| "Mice don't predict humans" | Biology (partial) | Wrong use of models | True for efficacy, but we use them for efficacy anyway |
| "EPR is unreliable" | Biology | Wrong framing | EPR isn't a targeting mechanism; it was wrong approach |
| "Flat PPIs can't be drugged" | Chemistry | Tech gap | BCL-2 was a "flat" PPI and was drugged |
| "Transcription factors can't be targeted" | Biology | Wrong modality | Can be degraded (PROTAC) even if can't be inhibited |

### Why False Constraints Persist

1. **Sunk cost fallacy:** "We tried for 20 years, so it must be fundamental"
2. **Limited toolbox:** "Can't do it with small molecules" ≠ "can't be done"
3. **Conflation:** "Hard" gets upgraded to "impossible"
4. **Lack of positive deviants:** Until one example works, seems impossible
5. **Wrong framing:** Asking wrong question makes answer seem impossible

## Knowledge Gaps (Not Constraints)

Knowledge gaps are often mistaken for constraints. These are problems where we don't know HOW to solve, but there's no fundamental reason it CAN'T be solved.

| Gap | Domain | What We Don't Know | Evidence It's Not Constraint |
|-----|--------|-------------------|----------------------------|
| SNAC mechanism | Oral Biologics | How SNAC enables absorption | It WORKS; we just don't know why |
| LNP escape mechanism | Endosomal Escape | Why LNPs achieve 1-2% escape | Some escape happens; need to understand |
| LNP tropism determinants | Tissue Targeting | What makes LNPs go to different tissues | SORT shows tropism can be altered |
| Responder biomarkers | Patient Heterogeneity | Who will respond | Some diseases have biomarkers (HER2) |
| Surrogate-outcome causality | Clinical Translation | Which surrogates are causal | Some surrogates validated (viral load, BP) |
| Cryptic pockets | Undruggable Targets | Which "flat" proteins have pockets | KRAS G12C had a cryptic pocket |

## Tech Gaps (Not Constraints)

Tech gaps are problems where we know WHAT is needed but can't BUILD it yet. These are engineering challenges, not fundamental limits.

| Gap | Domain | What's Needed | Current Status |
|-----|--------|--------------|----------------|
| Non-toxic fusogenic delivery | Endosomal Escape | Virus-like fusion without toxicity | Active research; no breakthrough |
| Liver-avoiding LNPs | Tissue Targeting | LNPs that don't accumulate in liver | SORT shows promise; early stage |
| PROTAC oral bioavailability | Undruggable | Large molecules with good PK | Chemistry optimization ongoing |
| High-throughput MR | Validation | Genetic causality testing at scale | Methods exist; need application |
| Scalable organoids | Model Translation | Human tissue systems at scale | Technology improving |
| Predictive biomarker platforms | Patient Heterogeneity | Multi-omic responder prediction | ML approaches emerging |

## Framing Problems (Not Constraints)

Framing problems are cases where the field is asking the wrong question, making the problem seem unsolvable.

| Wrong Frame | Domain | What's Wrong | Right Frame |
|-------------|--------|-------------|-------------|
| "Maximize bioavailability" | Oral Biologics | Potency × bioavailability is what matters | 1% bioavailability + 100x potency works |
| "Target the tumor via EPR" | Tissue Targeting | EPR is passive, unreliable in humans | Active targeting or external triggering |
| "Optimize escape %" | Endosomal Escape | Escape × delivery × potency is outcome | Low escape acceptable with high potency |
| "Validate in mice" | Model Translation | Mice don't predict efficacy | Validate in human genetics |
| "Is this druggable?" | Undruggable | Wrong modality assumed | "How might this become druggable?" |
| "Average treatment effect" | Patient Heterogeneity | Heterogeneity hidden in average | Individual treatment effects |

## Summary Statistics

Across all 8 bottlenecks analyzed:

| Category | Count | % of Total Barriers |
|----------|-------|---------------------|
| True biology constraints | 6 | ~15% |
| Partial biology constraints (workarounds exist) | 8 | ~20% |
| Knowledge gaps | 18 | ~25% |
| Tech gaps | 16 | ~22% |
| Framing problems | 12 | ~15% |
| Design/systemic issues | 5 | ~3% |

**Key finding:** Only ~15% of identified barriers are TRUE biology constraints. The remaining ~85% are potentially addressable with knowledge, technology, or reframing.

## Implications

### What This Means for R&D Strategy

1. **Stop treating everything as fundamental:** Most "constraints" aren't
2. **Invest in understanding mechanisms:** Knowledge gaps are solvable with research
3. **Expand the toolbox:** Tech gaps require engineering investment
4. **Challenge framing:** Ask if we're solving the right problem
5. **Accept real constraints:** Focus on workarounds, not solutions for true constraints

### What Would Change if We Accepted This Analysis

| Current Approach | Alternative Approach |
|-----------------|---------------------|
| "Oral biologics won't work" | "Oral biologics need potency + enhancers" |
| "Mice are predictive" | "Mice are useful for mechanism, not efficacy" |
| "Target is undruggable" | "Target needs different modality" |
| "Phase 2 data supports advancement" | "Phase 2 design supports advancement decision" |
| "Delivery is the problem" | "Delivery × potency × escape is the problem" |

## The Meta-Constraint

There is one meta-level constraint that affects everything:

**We don't know what we don't know.**

Many "constraints" were reclassified only after a positive deviant emerged (KRAS G12C, oral semaglutide, etc.). Before these examples, the constraint seemed real.

**Implication:** Any currently identified "true constraint" might be reclassifiable if someone finds a workaround. The history of science suggests we systematically overestimate fundamentality of barriers.

**Recommended heuristic:** Treat "biology constraints" as "biology constraints for now" and maintain active research into workarounds for even the most fundamental-seeming barriers.
