# Genetic vs. Phenotypic Target Validation

## What We're Trying To Do

Prove that modulating a target (protein, pathway, gene) will produce therapeutic benefit in humans BEFORE investing $100M+ in drug development. This is the "right target" question.

## Why It's Hard (First Principles)

### The Validation Paradox

**From an epistemologist's perspective:**

We want to know if a drug against target X will work in humans. But we can't know this without building the drug and testing it in humans. Everything else is indirect evidence:

1. **Genetic evidence is correlational**
   - GWAS: SNP associated with disease ≠ SNP causes disease
   - Even Mendelian diseases: mutation causes disease ≠ reversing phenotype works
   - Direction matters: loss-of-function vs. gain-of-function
   - *Association ≠ Causation ≠ Druggability*

2. **Phenotypic screens find "what works" but not "why"**
   - Drug produces phenotype ≠ drug hits intended target
   - Polypharmacology: most drugs hit multiple targets
   - The "target" may be wrong even when drug works
   - *Mechanism is assumed, not proven*

3. **Model systems don't replicate human disease**
   - Mouse knockouts: binary manipulation in different biology
   - Cell lines: 2D, clonal, artificial environment
   - Organoids: better but still simplified
   - *Models validate in models, not in humans*

4. **Correlation structure confounds everything**
   - Disease pathways are interconnected
   - Hitting "downstream" vs. "upstream" targets differs
   - Feedback loops: inhibit A → B increases → disease persists
   - *You're intervening in a network, not a single node*

### The Two Validation Philosophies

**Genetic validation approach:**
```
Human genetics (GWAS/Mendelian) → Target identification → Drug development
```
- Strengths: Human data; causal direction sometimes clear
- Weaknesses: Effect sizes small; many genes, each minor contribution; druggability unknown

**Phenotypic validation approach:**
```
Phenotypic screen → Hit compound → Target identification (reverse pharmacology)
```
- Strengths: Know compound works; biology-agnostic
- Weaknesses: Don't know target; mechanism unclear; may not translate

**The ideal:** Convergent evidence from both approaches

### Barrier Decomposition

| Barrier | Why It Exists | Classification | Fixable? | What Would Fix It |
|---------|--------------|----------------|----------|-------------------|
| GWAS effect sizes tiny | Complex trait genetics | Biology | Accept | Use for prioritization, not proof |
| Correlation ≠ causation | Observational data | Statistics | Partially | Mendelian randomization; functional validation |
| Model organisms ≠ humans | Evolutionary divergence | Biology | Partially | Human-relevant models; human genetics |
| Phenotypic hits have unknown MOA | Screen design | Design | Yes | Chemoproteomics; genetic deconvolution |
| Target-disease relationship is networked | Biology | Biology | Understand | Systems biology; pathway analysis |
| Negative results not published | Academic incentives | Systemic | Yes | Preregistration; publication reform |
| Validation not predictive | Wrong metric | Framing | Yes | Predictive (Phase 3) not descriptive (biology) |
| Druggability unknown until tried | Chemistry | Tech gap | Partially | Structural biology; druggability prediction |

### The Evidence Hierarchy

**Strongest evidence (for human target validation):**
1. Human genetic proof-of-concept (natural knockouts healthy or protected)
2. Mendelian randomization (genetic instrument → outcome)
3. Multiple independent genetic signals pointing to same target
4. Phenotypic screen hit + genetic support convergent

**Moderate evidence:**
5. Single GWAS hit with functional validation
6. Mouse knockout recapitulates disease
7. Phenotypic screen with target ID

**Weak evidence:**
8. In vitro activity
9. Correlation studies
10. Pathway proximity to validated target

## What Works (Positive Deviants)

### 1. PCSK9 - The Gold Standard

**Why it worked:**
- Human genetics: PCSK9 loss-of-function → low LDL + CV protection
- Natural knockouts exist (healthy, very low LDL)
- Direction clear: inhibiting PCSK9 mimics protective mutations
- Outcome clear: CV events, well-established LDL-outcome relationship

**Key insight:** When natural human experiments exist (loss-of-function mutations), validation confidence is highest.

### 2. SGLT2 Inhibitors - Phenotypic Origin, Genetic Confirmation

**What happened:**
- Phenotypic discovery: phlorizin (natural product) causes glucosuria
- Mechanism discovered later (SGLT2)
- Human genetics: SGLT2 mutations cause familial renal glucosuria (benign)
- Drugs developed, unexpected CV benefit discovered

**Key insight:** Convergent evidence (phenotypic + genetic) is powerful. Sometimes benefits exceed predictions.

### 3. IL-23 Pathway (Psoriasis/IBD)

**Why it worked:**
- GWAS strongly implicated IL-23R in psoriasis and IBD
- Functional studies confirmed IL-23 pathway role
- Anti-IL-23 antibodies produced strong effects

**Key insight:** Strong, replicated genetic signal + mechanistic understanding = high validation confidence.

### 4. Amyloid-β (Alzheimer's) - The Cautionary Tale

**What happened:**
- Genetic evidence: APP, PSEN1/2 mutations cause familial AD
- Amyloid plaques are pathological hallmark
- Decades of anti-amyloid drugs: minimal clinical benefit
- Recent approvals (aducanumab, lecanemab) controversial

**Why it partially failed:**
- Genetics validated amyloid in FAMILIAL AD (~1% of cases)
- Sporadic AD may have different drivers
- Timing: removing amyloid after neurodegeneration too late?
- Target validated ≠ druggable in practical sense

**Key insight:** Genetic validation doesn't guarantee druggability or that intervention at any stage works.

### 5. Negative Control: HDL-Raising

**What happened:**
- Observational: high HDL associated with lower CV risk
- Drugs that raise HDL (CETP inhibitors, niacin) didn't reduce CV events
- Mendelian randomization later showed: HDL-raising genes don't protect

**Key insight:** Observational association + biological plausibility is INSUFFICIENT. Genetic causal evidence matters.

## What Solving This Would Unlock

```
Reliable target validation (>80% predictive of Phase 3)
↓
├── Rational portfolio decisions
│   ├── Kill bad programs early (save $100M+)
│   ├── Double down on high-confidence targets
│   └── Risk-adjusted investment decisions
│
├── "Undruggable" targets prioritized correctly
│   ├── Worth investing in hard chemistry if target is validated
│   ├── Not worth it if target is speculative
│   └── Resource allocation optimized
│
├── Mechanism-based combinations
│   ├── Combine on validated pathways
│   ├── Avoid redundant targeting
│   └── Synergy predicted from network position
│
└── Faster development cycles
    ├── Skip "validation" experiments that don't validate
    ├── Go to humans earlier with genetic confidence
    └── More clinical experiments, fewer preclinical
```

## What Specifically Blocks The Unlock

| Blocking Factor | Type | Who's Working On It | Status |
|-----------------|------|---------------------|--------|
| GWAS hits not functionally validated | Knowledge + Resource | Academic labs; Open Targets | Slow |
| No systematic human knockout database | Data gap | UK Biobank; gnomAD; Iceland | Building |
| Mendelian randomization not applied widely | Adoption lag | Academic epidemiology | Growing |
| Preclinical validation studies not predictive | Wrong metric | Industry knows, hard to change | Stuck |
| Negative results hidden | Systemic | Publication reform efforts | Slow |
| Drug failures attributed to "target" when it's drug | Framing | Better failure analysis | Improving |
| Animal models entrenched despite poor translation | Systemic + regulatory | FDA flexibility; alternatives | Slow |

## Key Uncertainties

| Question | Why It Matters | How We'd Answer It |
|----------|---------------|-------------------|
| What fraction of Phase 2/3 failures are target failures vs. drug failures? | Scope of problem | Systematic failure analysis |
| Can we predict druggability from structure + genetics? | Prioritization | ML on structure + outcome data |
| How many "validated" targets are actually invalid? | Current confidence calibration | Retrospective analysis |
| Does genetic validation strength predict clinical success? | Quantitative guide | Meta-analysis of genetic evidence → outcome |
| Are phenotypic hits with unknown MOA safer bets? | Strategy choice | Compare success rates |

## Confidence Summary

**Biology constraints identified:** 2
- Complex diseases have many small-effect contributors (can't all be drugged)
- Network effects: single node intervention may be insufficient

**Knowledge gaps:** 4
- Functional interpretation of most GWAS hits
- Complete human knockout phenotypes
- Target-disease causal relationships for most diseases
- Druggability prediction accuracy

**Tech gaps:** 1
- High-throughput functional validation of genetic variants

**Framing problems:** 3 (major)
- "Validation" in model organisms doesn't validate in humans
- Treating all genetic evidence as equal (effect size, direction matter)
- Blaming "target" when drug/dose/timing may be wrong

**Systemic problems:** 2
- Negative results not published
- Sunk cost fallacy on invalid targets

## Bottom Line

Target validation is **fundamentally uncertain** - we cannot prove a target will work in humans without testing in humans. But we can **massively improve our prior probability** by:

1. **Prioritize human genetic evidence** - especially loss-of-function (tells you inhibition is safe/effective)
2. **Require Mendelian randomization** - for any non-genetic validation claim
3. **Look for convergent evidence** - phenotypic + genetic + mechanistic
4. **Accept uncertainty** - validation de-risks, it doesn't guarantee
5. **Do failure autopsies** - was it target or drug?

**The quantitative goal:** Current Phase 2 success rates of ~25-30% suggest target selection is ~50% correct (assuming ~50% of failures are target-related). With rigorous genetic validation, this could improve to ~70-80%.

**Prediction:** Genetically validated targets (strong human genetic evidence, MR support) will have 2-3x higher Phase 2/3 success rates than non-genetically validated targets. The industry will shift toward genetic prioritization, but slowly because of sunk costs in existing programs.

**The hard truth:** Most "validated" targets in the literature are not validated in any predictive sense. The word "validated" has been debased to mean "we did some experiments" rather than "this will likely work in humans."
