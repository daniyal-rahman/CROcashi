
# 1) Martin’s short thesis on Cassava (the essentials)

**Who/where:** Martin Shkreli’s 38-page PDF “On the Impossible: Why Cassava’s simufilam will fail Phase 3.” (Nov 2024). It argues failure was inevitable and explains why.&#x20;

**Core planks (condensed):**

* **Phase 2 evidence was negative or spun.** The only controlled piece—the **randomized-withdrawal Phase 2 (CMS)**—showed **no statistical difference** drug vs placebo; earlier Phase 2a/2b cognition claims were **manipulated/spun**, and later drew **SEC charges** over misleading statements about the trial. ([SEC][1])
* **Mechanism/chemistry don’t add up.** Simufilam is *not* a plausible high-affinity protein-protein interaction inhibitor of FLNA; claimed binding is weak (\~µM), **PK and brain partitioning are poor**, so you can’t reach target-coverage needed for an effect—**even if** the FLNA hypothesis were right.&#x20;
* **Biology is implausible / chain is tortured.** The FLNA → Aβ/α7nAChR/TLR signaling story is too indirect and poorly supported to drive clinical benefit; the key academic proponent (Wang) became the subject of **federal fraud charges** tied to simufilam-related research. ([Department of Justice][2])
* **Trial-design tells a story of bias.** A year-long **open-label** lead-in followed by RW is selection-biased; **post-hoc subgrouping (mild vs moderate)** was highlighted **without proper multiplicity control**, a classic way to generate “wins” that disappear in de-novo Phase 3.&#x20;
* **Prediction:** Phase 3 would fail—and it did (both **RETHINK-ALZ** and **REFOCUS-ALZ**). ([MarketWatch][3])

> ⚠️ **Your TNF/BBB memory**
> That “**TNF is a homo-trimer that won’t cross the BBB** and can’t reach a therapeutic brain dose” critique is about **INmune Bio’s XPro1595 (a dominant-negative soluble-TNF biologic)**—*not* Cassava’s simufilam (a small molecule). XPro is literally designed to form **heterotrimers** with soluble TNF and has public claims about BBB exposure; that’s a different program. ([Alzheimer's Discovery Foundation][4], [PMC][5])

# 2) Would your pipeline make the same arguments? (critical pass/fail)

### What your system can already capture (or can with tiny tweaks)

* **RW after OLE is fragile evidence.** If you add/keep a primitive like **S7b: randomized-withdrawal after OLE**, your engine can flag the **design-bias** Martin calls out (moderate LR). You’ve already sketched this; ship it.&#x20;
* **Subgroup-only emphasis.** Your **S3** can (and should) tag **post-hoc, unadjusted, non-significant** subgroup highlighting (set significance=false, adjusted=false; low–moderate LR). That mirrors his “multiplicity” critique.&#x20;
* **Company-only narrative / reframing.** A light-weight **“narrative reframing / company-only source”** primitive (what we called **S10/S11**) would reflect his skepticism about PR-driven efficacy claims. You’ve started to add this—good.

### What your system **cannot** reproduce yet (and needs to, to match the thesis)

1. **Preclinical plausibility & exposure math (big gap).**
   Martin’s most load-bearing point is **potency × exposure × brain partition** ⇒ **no feasible target coverage**. You need a **PK/PD plausibility module** that:

   * extracts/estimates **Kd/IC50** for the proposed binding (or flags “unknown/contested”),
   * pulls **brain\:plasma or CSF concentrations** from human PK or analogs,
   * computes **coverage = (unbound brain concentration / Kd)** and flags when coverage ≪ 1×.
     Without this, you can’t formalize the “can’t possibly reach effect size” argument.&#x20;

2. **Mechanism credibility / data-integrity gate.**
   His critique leans on **questionable foundational data** (CUNY report, **DOJ indictment** of Wang; **SEC** settlement over Phase 2 claims). Add a **D1: Data-integrity risk** gate that lights up when there are **formal enforcement actions or institutional findings** tied to the mechanism’s core evidence. Weight it meaningfully. ([Department of Justice][2], [SEC][1])

3. **Dose–response & time-course sanity.**
   He notes **no dose-dependence** and **late cognitive “improvements”** after single dosing paradigms—physiology-implausible. Add a **dose-response sanity check** (does effect rise with dose/exposure?) and a **time-course plausibility** rule (lags consistent with MOA?). Your current stack doesn’t encode this.

4. **Protein–protein interaction feasibility check.**
   His “PPI inhibitor implausibility” point is general drug-design priors (very few small-molecule PPI inhibitors, especially for huge scaffolds like FLNA). A **class-prior module** that penalizes unvalidated PPI claims without structural/biophysical corroboration would reproduce this signal.&#x20;

5. **Publication vs PR weighting.**
   He hammers the absence of peer-review for the “positive” reads. You only partially encode this. Make **peer-reviewed, pre-registered, blinded RCT** evidence a higher weight class; down-weight **open-label/PR** by default.

### Bottom line on your pipeline

* You can already mirror his **trial-design/statistics** criticism (RW-after-OLE; subgroup misuse; narrative reframing).
* You **cannot** mirror his **pharmacology & integrity** criticisms without new modules for **PK/brain exposure math**, **PPI/mechanism priors**, and a **data-integrity gate** tied to **SEC/DOJ/CUNY** actions.

If you want, I’ll draft the minimal new primitives (names, inputs, decision rules, suggested LRs) so you can wire them in quickly.

* [MarketWatch](https://www.marketwatch.com/story/cassava-sciences-stock-halted-down-5-after-alzheimers-disease-trial-fails-to-meet-its-goals-8b86b3f9?utm_source=chatgpt.com)
* [MarketWatch](https://www.marketwatch.com/story/cassava-sciences-settles-sec-charges-of-misleading-alzheimers-trial-claims-0edefa16?utm_source=chatgpt.com)
* [reuters.com](https://www.reuters.com/legal/us-professor-charged-with-manipulating-data-alzheimers-drug-trial-2024-06-28/?utm_source=chatgpt.com)

[1]: https://www.sec.gov/newsroom/press-releases/2024-151?utm_source=chatgpt.com "SEC Charges Cassava Sciences, Two Former Executives ..."
[2]: https://www.justice.gov/archives/opa/pr/professor-charged-operating-multimillion-dollar-grant-fraud-scheme?utm_source=chatgpt.com "Professor Charged for Operating Multimillion-Dollar Grant ..."
[3]: https://www.marketwatch.com/story/cassava-sciences-stock-halted-down-5-after-alzheimers-disease-trial-fails-to-meet-its-goals-8b86b3f9?utm_source=chatgpt.com "Cassava Sciences' stock craters after Alzheimer's disease trial fails to meet its goals"
[4]: https://www.alzdiscovery.org/uploads/cognitive_vitality_media/XPro1595_UPDATE_%28drug_in_development%29.pdf?utm_source=chatgpt.com "XPro1595"
[5]: https://pmc.ncbi.nlm.nih.gov/articles/PMC5464789/?utm_source=chatgpt.com "Peripheral administration of the soluble TNF inhibitor ..."
