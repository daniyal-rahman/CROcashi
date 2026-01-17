# Tissue-Specific Delivery

## What We're Trying To Do

Deliver therapeutics (small molecules, nanoparticles, biologics) to a specific tissue while minimizing accumulation elsewhere. The goal is to maximize target exposure while minimizing systemic toxicity.

## Why It's Hard (First Principles)

### The Biology/Physics/Chemistry

**From a physicist's perspective:**

When you inject something into blood, physics and biology conspire to send it to the liver. Understanding why requires decomposing the transport problem:

1. **Blood flow distribution is unequal**
   - Liver receives ~25% of cardiac output (portal vein + hepatic artery)
   - Tumor might receive <1% of cardiac output
   - First-pass effect: anything from GI tract hits liver first
   - *This is anatomy, not modifiable*

2. **Capillary structure varies dramatically**
   - Continuous capillaries (brain, muscle): tight junctions, no fenestrations
   - Fenestrated capillaries (kidney, GI): 60-80 nm pores
   - Sinusoidal capillaries (liver, spleen, bone marrow): 100-200 nm gaps, no basement membrane
   - *Liver is literally more permeable to particles*

3. **The Mononuclear Phagocyte System (MPS) is designed to clear particles**
   - Kupffer cells (liver macrophages): 80-90% of body's fixed macrophages
   - Splenic macrophages: secondary clearing site
   - Any "foreign" particle gets opsonized (complement, antibodies) → phagocytosed
   - *This is immune function, evolved to clear debris and pathogens*

4. **Size determines fate**
   - <5 nm: renal filtration (kidney clearance)
   - 5-200 nm: MPS clearance (liver/spleen)
   - >200 nm: pulmonary capillary filtration (lung first-pass)
   - *There's no "safe" size range that avoids all clearance*

5. **Surface chemistry determines opsonization**
   - Hydrophobic surfaces → rapid protein corona → opsonization → clearance
   - Charged surfaces → complement activation → clearance
   - PEGylation reduces but doesn't eliminate opsonization
   - *Biology actively recognizes and clears foreign particles*

### Barrier Decomposition

| Barrier | Why It Exists | Classification | Fixable? | What Would Fix It |
|---------|--------------|----------------|----------|-------------------|
| Liver blood flow (25% CO) | Anatomical structure for metabolic function | Biology constraint | No | Cannot change; must outcompete with targeting |
| Sinusoidal fenestrations | Liver needs rapid exchange with blood | Biology constraint | No | Cannot change; can exploit for liver targeting |
| Kupffer cell clearance | Immune function to clear debris/pathogens | Biology constraint | Partially | Pre-dosing to saturate; PEGylation; CD47 ("don't eat me") |
| Opsonization (complement) | Immune recognition of foreign surfaces | Biology constraint | Partially | Surface chemistry engineering; biomimetic surfaces |
| Tumor hypoperfusion | Chaotic vasculature from rapid growth | Disease pathology | Partially | Vascular normalization (anti-VEGF paradox) |
| Tight junctions (brain, etc.) | Barrier function protecting organ | Biology constraint | Partially | Hijack transcytosis; focused ultrasound |
| Non-specific uptake | Cells endocytose what they contact | Biology baseline | Yes (reframe) | Make target cells take up MORE, not others take up LESS |

### The EPR Myth - A Case Study in Wrong Framing

**The claim:** Tumors have Enhanced Permeability and Retention (EPR) - leaky vessels + poor lymphatic drainage = nanoparticle accumulation.

**The reality:**
- EPR works in mouse xenografts (fast-growing, highly vascularized)
- Human tumors: EPR varies enormously (some: none; some: modest)
- Meta-analysis: only ~0.7% of injected nanoparticle dose reaches tumor
- EPR is not a targeting mechanism - it's passive accumulation in a subset of tumors

**The reframe:** EPR is not a reliable delivery mechanism. Active targeting (ligand-receptor, transcytosis, external triggering) needed.

## What Works (Positive Deviants)

### 1. Antibody-Drug Conjugates (ADCs) - Active Targeting

**What works:** Trastuzumab deruxtecan (Enhertu) for HER2+ cancers

**Why it works:**
- Antibody provides specificity (only binds HER2+ cells)
- High drug-to-antibody ratio (8:1)
- Bystander effect: released payload kills nearby HER2- cells
- Linker chemistry tuned for intracellular release

**Key insight:** Targeting works when:
1. Target is truly differential (HER2 overexpressed 100x in tumor vs. normal)
2. Payload is potent enough that small delivery % is sufficient
3. Mechanism doesn't require reaching every cell (bystander effect)

### 2. LNPs to Liver - Going With the Flow

**What works:** Onpattro (patisiran) - siRNA to hepatocytes

**Why it works:**
- LNPs naturally accumulate in liver (don't fight physics)
- ApoE coating in blood → LDLR-mediated uptake by hepatocytes
- Hepatocyte target is high-expressing (lots of LDLR)
- Not fighting MPS - exploiting it

**Key insight:** Liver delivery is easy. The hard problem is delivering anywhere ELSE.

### 3. Intrathecal/Local Delivery - Bypassing Systemic Distribution

**What works:** Spinraza (nusinersen) - intrathecal for spinal muscular atrophy

**Why it works:**
- Direct injection into CSF bypasses BBB
- CSF volume is small (~150 mL) vs. blood (~5 L)
- Drug stays compartmentalized

**Key insight:** Sometimes the solution is to avoid systemic delivery entirely.

### 4. CAR-T Cells - Active Hunting

**What works:** Kymriah, Yescarta - CAR-T cells find and kill tumors

**Why it works:**
- Cells actively migrate to target tissue
- Proliferate at target site
- Self-amplifying delivery mechanism

**Key insight:** Biological delivery vehicles (cells) have capabilities synthetic particles don't (migration, proliferation, sensing).

### 5. Irinotecan Liposome (Onivyde) - The Rare EPR Success

**What works:** Liposomal irinotecan for pancreatic cancer

**Why it works (partially):**
- Pancreatic tumors have some EPR (highly stromal, but some leakiness)
- Liposome protects drug, releases slowly
- Modest improvement over free drug (not transformative)

**Key insight:** EPR can help at the margin, but it's not a targeting mechanism.

## What Solving This Would Unlock

```
Tissue-specific delivery solved
↓
├── Oncology transformation
│   ├── Toxic chemotherapy at tumor-only doses
│   ├── Immunotherapy without systemic inflammation
│   └── siRNA/mRNA to any solid tumor
│
├── CNS diseases addressable
│   ├── Alzheimer's (clear amyloid, deliver growth factors)
│   ├── Parkinson's (local dopamine restoration)
│   └── Brain tumors (chemo without cognitive damage)
│
├── Autoimmune precision
│   ├── Tolerance induction at specific sites
│   ├── Local immunosuppression without systemic effects
│   └── Target autoreactive cells only
│
└── Gene therapy to any organ
    ├── AAV tissue tropism expanded
    ├── LNP beyond liver
    └── CRISPR to specific cell types
```

## What Specifically Blocks The Unlock

| Blocking Factor | Type | Who's Working On It | Status |
|-----------------|------|---------------------|--------|
| MPS clearance dominates | Biology constraint | PEGylation (partial), CD47 coating, Kupffer depletion | Incremental progress |
| No good liver-avoiding LNP | Tech gap | Selective ORgan Targeting (SORT), many academic labs | Early - 6th gen LNPs emerging |
| Target antigens not differential enough | Biology constraint | Better target discovery needed | Ongoing |
| Active targeting doesn't overcome distribution | Framing problem | Field focuses on targeting ligand, not total delivery | Shifting understanding |
| EPR unreliable in humans | Wrong framing | Move to active mechanisms (transcytosis, external trigger) | Field waking up to this |
| BBB too effective | Biology constraint | FUS-BBB opening, transcytosis hijacking (transferrin receptor) | Multiple approaches, none dominant |
| Manufacturing complexity for targeted particles | Tech gap | Process development teams | Solvable with resources |

## Key Uncertainties

| Question | Why It Matters | How We'd Answer It |
|----------|---------------|-------------------|
| What determines LNP tropism beyond charge/size? | Would enable rational design | Systematic library screens with sequencing readout |
| Can transcytosis be hijacked efficiently? | Alternative to EPR for tumors | Mechanism studies on transferrin receptor, LRP1 |
| Is pre-saturating MPS viable clinically? | Would increase delivery to other organs | Clinical studies with decoy particles |
| What's the actual biodistribution in human tumors? | EPR reality check | Better imaging; tumor biopsies with quantification |
| Can external triggering (FUS, light, magnet) scale? | Would solve targeting with physics | Engineering + clinical feasibility studies |

## Confidence Summary

**Biology constraints identified:** 4
- Liver blood flow distribution (anatomical)
- Kupffer cell/MPS clearance (immune function)
- Sinusoidal fenestrations (liver architecture)
- Tissue-specific capillary structures (developmental)

**Knowledge gaps:** 3
- What determines LNP tropism
- Optimal transcytosis targets per tissue
- Real EPR magnitude in human tumors

**Tech gaps:** 3
- Liver-avoiding LNP formulations
- Scalable active targeting manufacture
- External triggering devices that are practical

**Framing problems:** 2 (major)
- EPR reliance when active targeting needed
- Optimizing targeting LIGAND when the problem is total DELIVERY (MPS dominates)

## Bottom Line

Tissue-specific delivery IS fundamentally constrained by biology - the MPS exists to clear particles, and the liver's architecture favors particle accumulation. These are real constraints, not solvable.

However, the field has been working on the WRONG PROBLEM:
1. **Active targeting ligands don't help much** because MPS clearance dominates before targeting happens
2. **EPR is not reliable** in humans despite working in mice
3. **The question isn't "how to target" but "how to avoid liver first"**

**The highest-leverage interventions are:**
1. MPS pre-saturation or evasion (CD47, Kupffer depletion)
2. Route change (local, intrathecal, inhalation)
3. SORT-type approaches for non-liver LNP targeting
4. External triggering (FUS, heat, light) for spatially controlled release
5. Biological vehicles (cells) that actively migrate

**Prediction:** Liver will remain the "default" target for nanoparticles. Other organs will require either local delivery, active cell-based vehicles, or external triggering. The EPR-dependent passive targeting paradigm should be abandoned.
