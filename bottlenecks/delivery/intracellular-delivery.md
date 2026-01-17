# Intracellular Delivery

## What We're Trying To Do

Get therapeutic cargo (proteins, nucleic acids, small molecule conjugates) into the cytoplasm or nucleus of target cells at functional concentrations, without killing the cells or triggering immune responses.

## Why It's Hard (First Principles)

### The Biology/Physics/Chemistry

**From a physicist's perspective:**

The cell is a fortress with multiple defense layers. To get inside, you must either:
1. Pass through the membrane (requires overcoming the hydrophobic barrier)
2. Get taken up by the cell's own processes (endocytosis → trapped in vesicles)
3. Physically breach the membrane (damages cell)

**The defense layers:**

1. **Plasma membrane: 5 nm lipid bilayer**
   - ~40 Å hydrophobic core
   - Permeability coefficient: charged molecules ~10⁻¹² cm/s (essentially impermeable)
   - Small neutral molecules can diffuse (Rule of 5: <500 Da, logP 1-5, etc.)
   - Large polar molecules (proteins, nucleic acids): impermeable by passive diffusion
   - *Fundamental barrier for biologics*

2. **Endocytosis: the cell's intake system**
   - Cells internalize ~100% of plasma membrane surface per hour (recycling)
   - Multiple pathways: clathrin-mediated, caveolae, macropinocytosis, phagocytosis
   - ALL lead to endosomes → lysosomes (see endosomal-escape.md)
   - *Entry is easy; escape is hard*

3. **Cytoplasmic surveillance**
   - Once in cytoplasm, nucleic acids trigger innate immunity
   - Pattern recognition receptors: RIG-I (dsRNA), cGAS (dsDNA), etc.
   - Protein quality control: ubiquitination, proteasomal degradation
   - *Surviving the cytoplasm is another challenge*

4. **Nuclear envelope: additional barrier**
   - Nuclear pore complex: ~9 nm channel, larger for active transport
   - Passive diffusion cutoff: ~40 kDa
   - Larger proteins need nuclear localization signals (NLS)
   - Mitosis briefly opens nuclear envelope (dividing cells only)
   - *For nuclear targets, TWO membranes to cross*

### Barrier Decomposition

| Barrier | Why It Exists | Classification | Fixable? | What Would Fix It |
|---------|--------------|----------------|----------|-------------------|
| Plasma membrane impermeability | Defines cell boundary, maintains gradients | Physics + Biology | Bypass | Carrier-mediated, endocytosis, physical methods |
| Endocytic trafficking to lysosomes | Sampling mechanism, nutrient uptake | Biology | Escape timing | Endosomal escape (see separate file) |
| Cytoplasmic nucleases/proteases | Quality control, defense | Biology | Yes | Chemical modifications (2'-OMe, PTO backbone, D-amino acids) |
| Innate immune sensing | Pathogen defense | Biology | Manage | Modified bases, sequence optimization, avoid PAMP motifs |
| Nuclear envelope | Genetic material protection | Biology | Partially | NLS tags, exploit mitosis, AAV capsids |
| Aggregation/mislocalization | Crowded cytoplasm | Physics | Partially | Solubilizing tags, active trafficking |

### Delivery Method Trade-offs

| Method | Entry Route | Escape Needed? | Scalability | Toxicity | Cell Type Limits |
|--------|-------------|----------------|-------------|----------|------------------|
| LNPs | Endocytosis | Yes (~1-2%) | Excellent | Low-moderate | All |
| Electroporation | Direct pores | No | Limited (cells) | Moderate | Ex vivo mostly |
| Viral vectors | Endocytosis + fusion | Yes (virus-mediated) | Good | Low | Tropism-dependent |
| Cell-penetrating peptides | Mixed (direct + endo) | Partially | Good | Variable | All |
| Microinjection | Direct | No | Poor | High | Single cells |
| Microfluidic squeeze | Direct pores | No | Moderate | Moderate | Ex vivo |

## What Works (Positive Deviants)

### 1. AAV Gene Therapy - The Gold Standard

**What works:** AAV delivers genes to multiple tissues (eye, CNS, liver, muscle)

**Why it works:**
- Viral capsid evolved for this job
- Receptor-mediated entry (AAVR, glycans)
- Endosomal escape: capsid has evolved fusogenic regions
- Nuclear entry: VP1/VP2 phospholipase + NLS
- Long-term expression in post-mitotic cells

**Key insight:** Viruses solved intracellular delivery over millions of years. We're trying to replicate evolution's work in decades.

**Limitations:**
- Immunogenicity limits redosing
- Packaging capacity (~4.7 kb)
- Manufacturing complexity
- Pre-existing immunity in population

### 2. LNP-mRNA (COVID Vaccines) - Scalable Enough

**What works:** Hundreds of millions vaccinated

**Why it works:**
- mRNA only needs cytoplasmic delivery (no nuclear entry)
- 1-2% escape is enough for vaccination (immune amplification)
- Chemical modifications reduce innate immune response
- Lipid composition optimized iteratively over decades

**Key insight:** For some applications, low efficiency is acceptable if:
1. Amplification mechanism exists (immune system, protein expression)
2. Dose can be increased (safe margin)
3. Single/few doses sufficient

### 3. Electroporation for CAR-T - Ex Vivo Scalable

**What works:** mRNA/DNA delivery to T cells for CAR-T manufacturing

**Why it works:**
- Cells outside body - can use more aggressive methods
- Transient pores from electric field
- Direct cytoplasmic access, no endosomal trap
- >90% transfection efficiency achievable

**Key insight:** Ex vivo delivery solves many problems. Cells can be selected/recovered.

### 4. Small Molecule Pro-drugs - Chemistry to the Rescue

**What works:** Remdesivir pro-drug → triphosphate in cells

**Why it works:**
- Parent compound designed for membrane permeability
- Cellular enzymes convert to active form
- Accumulates in cells through metabolic trapping

**Key insight:** If you can make it a small molecule, the problem is largely solved. Delivery is a biologics problem.

### 5. Conjugates with CPPs (Limited Success)

**What works:** Tat-peptide conjugates for some applications

**Why it partially works:**
- Cationic charge enables membrane association
- Can induce macropinocytosis
- Some direct translocation (controversial)

**Why it mostly fails:**
- Endosomal trapping still dominant
- Dose-limiting toxicity at high concentrations
- Cell-type variability

**Key insight:** CPPs are not a general solution - they shift the problem, don't solve it.

## What Solving This Would Unlock

```
Efficient intracellular delivery solved (>30% efficiency, all cell types)
↓
├── Protein therapeutics for intracellular targets
│   ├── Transcription factors delivered
│   ├── Cytoplasmic enzyme replacement
│   └── Intracellular antibodies (intrabodies)
│
├── Gene editing scaled
│   ├── In vivo CRISPR to any tissue
│   ├── Prime editing efficiency viable
│   └── Epigenetic editors delivered
│
├── RNA therapeutics broadly applicable
│   ├── siRNA beyond liver
│   ├── mRNA for secreted proteins (any tissue)
│   └── Circular RNA approaches enabled
│
└── New modalities feasible
    ├── Proteolysis-targeting chimeras (PROTACs) intracellular
    ├── Molecular machines delivered
    └── Synthetic transcription programs
```

## What Specifically Blocks The Unlock

| Blocking Factor | Type | Who's Working On It | Status |
|-----------------|------|---------------------|--------|
| Endosomal escape ceiling ~1-2% | See endosomal-escape.md | Many | Plateau |
| No universal delivery platform | Tech gap | Many companies | Fragmented approaches |
| Toxicity-efficacy tradeoff | Fundamental tension | Everyone | Inherent to approach |
| Cell type variability | Biology | Tropism engineering | Partial solutions (AAV variants) |
| Immune response limits redosing | Biology | Immunology + engineering | Active area |
| Scalable non-viral nuclear delivery | Tech gap | Few | Under-resourced |
| Efficiency measurement standardization | Field problem | Academics | Improving |

## Key Uncertainties

| Question | Why It Matters | How We'd Answer It |
|----------|---------------|-------------------|
| Is there a non-viral approach that can match viral efficiency? | Determines platform choice | Head-to-head comparisons, mechanism studies |
| Can we achieve >30% efficiency without toxicity? | Current ceiling is ~1-2% | Systematic toxicity-efficacy mapping |
| Which cell types are fundamentally harder? | Focus resources | Cross-cell-type efficiency mapping |
| Can physical methods (electroporation, microfluidics) scale to in vivo? | Would bypass chemistry | Engineering advances |
| Is nuclear delivery fundamentally harder than cytoplasmic? | Separate problem or same? | Mechanistic studies |

## Confidence Summary

**Biology constraints identified:** 4
- Plasma membrane impermeability to large polar molecules
- Endocytic trafficking to lysosomes
- Innate immune sensing of foreign nucleic acids
- Nuclear envelope barrier for nuclear targets

**Knowledge gaps:** 3
- Mechanism of rare successful endosomal escape events
- Determinants of cell-type-specific delivery efficiency
- Fate of cargo after cytoplasmic entry

**Tech gaps:** 4
- Non-viral system matching viral efficiency
- Scalable physical delivery for in vivo
- Non-toxic membrane-disrupting agents
- Universal platform (not target/tissue-specific)

**Framing problems:** 2
- Delivery efficiency vs. therapeutic efficiency (former often measured, latter matters)
- Focus on entry when escape is the bottleneck

## Bottom Line

Intracellular delivery is blocked at multiple levels, but **endosomal escape is the rate-limiting step** for most non-viral approaches. Viruses show the ceiling is high (>90%), but replicating their evolved mechanisms with synthetic systems remains elusive.

**Strategic insight:**
- For cytoplasm-only targets (mRNA), accept 1-2% efficiency and engineer high-potency cargo
- For nuclear targets (DNA, gene editing), either use viral vectors or ex vivo physical methods
- The "general non-viral intracellular delivery platform" doesn't exist and may not be achievable without mimicking viral mechanisms

**What would change the game:**
1. Non-immunogenic viral capsid variants (AAV without immunity issues)
2. Scalable physical delivery (microfluidics/squeeze for in vivo)
3. Breakthrough in endosomal escape chemistry (fusion vs. pore)
4. Accepting that different targets need different solutions (no universal platform)

**Prediction:** The field will bifurcate:
- Liver/hepatocyte delivery: LNPs will dominate (already good enough)
- Ex vivo cell engineering: physical methods will dominate
- In vivo non-liver: viral vectors will remain necessary for efficiency
- The "non-viral to any cell" platform remains elusive
