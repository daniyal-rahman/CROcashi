# "Undruggable" Targets

## What We're Trying To Do

Drug targets that current modalities cannot engage effectively: proteins without binding pockets, protein-protein interactions, transcription factors, scaffolding proteins, intrinsically disordered proteins. ~80% of the proteome is considered "undruggable" by conventional small molecules.

## Why It's Hard (First Principles)

### The Chemistry/Physics of Drug Binding

**From a medicinal chemist's perspective:**

A small molecule drug needs:
1. A binding site on the target (pocket, groove, surface)
2. Sufficient binding affinity (typically nM to pM)
3. Functional consequence of binding (inhibition, activation, allosteric modulation)
4. Drug-like properties (oral bioavailability, stability, selectivity)

**What makes a target "druggable":**
- Deep hydrophobic pocket (enzymes have active sites)
- Defined binding site for natural ligand (receptors have ligand sites)
- Conformational states that expose cryptic pockets
- Surface features that enable small molecule binding

**What makes a target "undruggable":**
- Flat protein-protein interaction surfaces (~1500-3000 Ų, shallow)
- No natural small molecule ligand (transcription factors)
- Intrinsically disordered (no stable structure to target)
- Scaffolding function (no enzymatic activity to inhibit)
- No allosteric site identified

### The Specific Challenges

**1. Protein-Protein Interactions (PPIs)**
- Interface area: 1500-3000 Ų
- Small molecule: covers ~300-1000 Ų
- Hot spots exist but are distributed
- Interface is flat (not pocket-like)
- *Shape mismatch between drugs and interface*

**2. Transcription Factors**
- Function by binding DNA and other proteins
- Often disordered until bound
- No enzymatic activity to inhibit
- Critical ones (MYC, TP53, RAS) are most wanted
- *Structure is function, and function is assembly*

**3. RAS Family (paradigm "undruggable")**
- Small GTPase, tight picomolar GDP/GTP binding
- Very few pockets identified
- 30+ years of failure
- KRAS G12C finally druggable (2021) via covalent approach
- *The poster child for undruggability*

**4. Intrinsically Disordered Proteins (IDPs)**
- ~30% of proteome has significant disorder
- No stable structure to target
- Function through transient interactions
- Examples: p53 transactivation domain, tau
- *Target is moving/doesn't exist as stable entity*

**5. Scaffolding/Structural Proteins**
- No enzymatic activity
- Function is to bring other proteins together
- Need to disrupt assembly, not enzyme activity
- *Nothing to inhibit in traditional sense*

### Barrier Decomposition

| Barrier | Why It Exists | Classification | Fixable? | What Would Fix It |
|---------|--------------|----------------|----------|-------------------|
| No deep binding pocket | Evolved without small molecule ligand | Biology | Partially | Cryptic pockets; covalent approaches; induced fit |
| PPI surfaces too large | Evolution optimized for protein binding | Biology | Partially | Stapled peptides; macrocycles; PROTACs |
| Intrinsic disorder | Functional flexibility | Biology | Partially | Target bound state; stabilize one conformation |
| No enzymatic activity | Scaffolding is the function | Biology | Reframe | Degrade, don't inhibit (PROTAC) |
| High affinity natural ligands | Evolution optimized binding | Chemistry challenge | Partially | Don't compete; use covalent; degrade |
| Flat surfaces | Interface topology | Physics | Partially | Larger molecules; multiple weak interactions |
| Selectivity | Related family members | Chemistry | Partially | Exploit differences; accept some promiscuity |

### The "Undruggable" Label Is Often Wrong

**Cases where "undruggable" was overcome:**

| Target | Why "Undruggable" | How It Was Drugged |
|--------|-------------------|-------------------|
| KRAS G12C | No binding site; super-tight GTP binding | Covalent inhibitor to mutant cysteine (sotorasib) |
| BCL-2 | PPI (BCL-2/BH3) | Fragment-based design; deep groove exploitation (venetoclax) |
| MDM2-p53 | PPI | Hot spot targeting; nutlins fill p53-binding pocket |
| BET bromodomains | No small molecule ligand | Discovered cryptic pocket; acetyl-lysine mimics |
| PD-1/PD-L1 | PPI (immune checkpoint) | Antibodies (not small molecule, but drugged) |

**Key insight:** "Undruggable" often means "undruggable with current approaches" or "we haven't tried hard enough."

## What Works (Positive Deviants)

### 1. KRAS G12C Inhibitors - The Breakthrough

**What worked:**
- Covalent approach: target mutant cysteine (G12C)
- Trap KRAS in inactive GDP-bound state
- Switch II pocket identified and exploited
- Sotorasib and adagrasib approved (2021-2022)

**Why it took 40 years:**
- Needed the right mutation (G12C creates targetable cysteine)
- Needed covalent chemistry advances
- Needed to abandon competitive GTP binding approach
- Switch II pocket was cryptic, only visible in GDP state

**Key insight:** Changed the approach (covalent, trap inactive state) rather than trying harder with old approaches. The target was druggable with the RIGHT approach.

### 2. BCL-2/Venetoclax - PPI That Worked

**What worked:**
- BCL-2 has a hydrophobic groove for BH3 domain binding
- Fragment-based screening found starting points
- Aggressive optimization led to venetoclax
- Ki ~1 nM; selective over BCL-xL

**Why it worked when most PPIs don't:**
- BCL-2 has a GROOVE, not a flat surface
- Natural peptide (BH3) fits in groove
- Small molecule can occupy same groove
- *Not all PPIs are equally flat*

**Key insight:** BCL-2 is a PPI with favorable topology. It's the exception, not the rule.

### 3. PROTACs - Reframing the Problem

**What works:**
- Don't inhibit the target; destroy it
- Bifunctional molecule: target binder + E3 ligase recruiter
- Bring target to degradation machinery
- Works on targets without functional pockets

**Why it's powerful:**
- Only need binding, not functional inhibition
- Catalytic: one PROTAC can degrade multiple target molecules
- Can degrade scaffolding proteins, transcription factors

**Current limitations:**
- Molecular weight (~1000 Da): PK challenges
- Tissue distribution limited
- E3 ligase availability varies by tissue
- Selectivity still required (wrong E3 = wrong tissue)

**Key insight:** Changed the question from "how to inhibit" to "how to eliminate."

### 4. Molecular Glues - Small Molecules Creating New PPIs

**What works:**
- Thalidomide/lenalidomide: bring cereblon E3 ligase to neo-substrates
- Induce degradation of proteins not normally degraded
- Small molecule (not bifunctional like PROTAC)
- Some are highly selective

**Why it's exciting:**
- Small molecule size (oral bioavailability)
- Can target "undruggable" proteins via degradation
- Expanding the targetable space

**Key insight:** Create new biology (new PPI) rather than inhibiting existing biology.

### 5. Macrocycles and Stapled Peptides - Larger Molecules

**What works:**
- Larger surface coverage than small molecules
- Stapled peptides stabilize helices for PPI disruption
- Macrocycles can have better PK than linear peptides
- Some achieve oral bioavailability

**Examples:**
- Stapled peptide targeting MDM2-p53
- Cyclosporine: oral macrocycle (shows it's possible)

**Key insight:** Between small molecules and biologics lies a middle ground.

## What Solving This Would Unlock

```
"Undruggable" targets druggable
↓
├── Major diseases addressed
│   ├── KRAS in 30%+ of cancers (partially solved)
│   ├── MYC: amplified in many cancers
│   ├── p53: mutated in >50% of cancers
│   └── Tau/alpha-synuclein: neurodegeneration
│
├── Target space expanded
│   ├── ~20% druggable → ~60% druggable
│   ├── Validated targets no longer blocked by chemistry
│   └── Genetic validation without druggability filter
│
├── Diseases of scaffolding/assembly
│   ├── Chaperonopathies
│   ├── Cytoskeletal diseases
│   └── Signaling scaffold diseases
│
└── Combination potential
    ├── Degrade one target, inhibit another
    ├── Multi-node pathway intervention
    └── Resistance mechanisms targetable
```

## What Specifically Blocks The Unlock

| Blocking Factor | Type | Who's Working On It | Status |
|-----------------|------|---------------------|--------|
| No general solution for flat PPIs | Tech gap | Many academic/industry | Active; no breakthrough |
| PROTAC PK challenges | Tech gap | Arvinas, C4, many | Improving |
| MYC still undrugged | Tech gap | Many have tried | No success yet |
| p53 restoration hard | Biology + tech | Multiple approaches | Limited success |
| IDP targeting conceptually hard | Knowledge gap | Academic research | Early |
| Molecular glue discovery serendipitous | Tech gap | Systematic screens emerging | Early |
| Selectivity for PPI disruptors | Chemistry | Case by case | Variable |
| Oral bioavailability for larger molecules | Chemistry/formulation | Formulation science | Incremental |

## Key Uncertainties

| Question | Why It Matters | How We'd Answer It |
|----------|---------------|-------------------|
| What fraction of "undruggable" is truly undruggable? | Scope | Systematic cryptic pocket surveys |
| Can IDPs be targeted in their bound state? | Strategy | Structural biology of complexes |
| Will molecular glue discovery become systematic? | Platform potential | ML on glue mechanisms |
| Can PROTACs achieve small molecule-like PK? | Platform viability | Chemistry optimization |
| Is there a universal E3 ligase for tissue-agnostic degradation? | PROTAC utility | E3 expression mapping |

## Confidence Summary

**Biology constraints identified:** 2 (partial)
- Flat PPI surfaces (physics, but can be worked around with larger molecules)
- Intrinsic disorder (hard, but bound states can be targeted)

**Knowledge gaps:** 3
- Cryptic pocket landscapes for most "undruggable" proteins
- IDP drugging strategies
- Molecular glue design rules

**Tech gaps:** 4
- General PPI disruption platform
- PROTAC PK optimization
- Systematic molecular glue discovery
- Oral macrocycle design

**Framing problems:** 2 (major)
- "Undruggable" as binary (when it's a spectrum)
- Inhibition as only modality (when degradation/stabilization exist)

## Bottom Line

"Undruggable" is **largely a tech/knowledge gap, NOT a biology constraint**. The history of KRAS shows that:
1. What seems impossible becomes possible with new approaches
2. "Undruggable" often means "undruggable with small molecules that occupy enzymatic pockets"
3. Reframing (degradation, covalent, macrocycle) opens new paths

**The true biology constraints:**
- Some proteins truly have no accessible surfaces (rare)
- Some functions require the protein to exist (can't degrade it)
- Some proteins are essential for healthy cells too (selectivity limit)

**What will expand the druggable proteome:**
1. **Covalent chemistry** - expanded toolbox for reactive amino acids
2. **PROTACs/molecular glues** - degrade what you can't inhibit
3. **Macrocycles/stapled peptides** - larger molecules for larger surfaces
4. **Cryptic pocket discovery** - computational + experimental mapping
5. **Allosteric approaches** - don't compete with natural ligand

**Prediction:** The "druggable" fraction will increase from ~20% to ~50% of disease-relevant proteins within 15 years, primarily through degradation approaches (PROTACs, molecular glues) and covalent chemistry. True "undruggable" (~20% of proteome) will remain challenging but smaller than currently thought.

**The hard truth:** We've been too quick to call targets "undruggable" because our toolbox was limited. As the toolbox expands, so does what's druggable. The question isn't "is this druggable?" but "how might this become druggable?"
