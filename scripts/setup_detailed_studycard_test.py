#!/usr/bin/env python3
"""
Setup script for detailed study card testing with longer document.

This script creates a minimal test database with:
- One company (Cassava Sciences)
- One trial (Phase 2 simufilam trial)
- One detailed document (Phase 2 trial paper with full methodology and results)
- One study card task

This allows us to test the new direct LLM card generation approach.
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def setup_detailed_test_data():
    """Create the detailed test data for study card testing."""
    
    # Database connection
    database_url = os.getenv('DATABASE_URL', 'postgresql://ncfd:ncfd@localhost:5433/lit_test')
    
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Setting up detailed study card test data...")
        
        # Clear any existing test data
        print("Clearing existing test data...")
        cur.execute("DELETE FROM tasks WHERE task_key = 'test_studycard_1_phase2'")
        cur.execute("DELETE FROM trial_doc_candidates WHERE trial_id = 1")
        cur.execute("DELETE FROM document_links WHERE trial_id = 1")
        cur.execute("DELETE FROM document_text WHERE doc_id = 1")
        cur.execute("DELETE FROM documents WHERE doc_id = 1")
        cur.execute("DELETE FROM trials WHERE trial_id = 1")
        cur.execute("DELETE FROM companies WHERE company_id = 1")
        
        # Insert company
        print("Inserting company...")
        cur.execute("""
            INSERT INTO companies (company_id, name, name_norm, created_at, updated_at)
            VALUES (1, 'Cassava Sciences, Inc.', 'cassava sciences inc', NOW(), NOW())
        """)
        
        # Insert trial (Phase 2 trial for simufilam)
        print("Inserting trial...")
        cur.execute("""
            INSERT INTO trials (trial_id, nct_id, brief_title, sponsor_text, sponsor_company_id, 
                              phase, indication, status, created_at, updated_at)
            VALUES (1, 'NCT05515666', 'A Phase 2 Study of Simufilam in Patients with Alzheimer''s Disease', 
                   'Cassava Sciences, Inc.', 1, 'PHASE2', 'Alzheimer''s Disease', 'RECRUITING', NOW(), NOW())
        """)
        
        # Insert detailed study document
        print("Inserting detailed document...")
        cur.execute("""
            INSERT INTO documents (doc_id, source_type, title, pmid, pmcid, nct_id, status, discovered_at)
            VALUES (1, 'Paper', 'Simufilam Reverses Aberrant Receptor Interactions of Filamin A in Alzheimer''s Disease: A Phase 2 Randomized Controlled Trial', 
                   '37762230', 'PMC9706102', 'NCT05515666', 'discovered', NOW())
        """)
        
        # Insert detailed full text
        print("Inserting detailed document text...")
        detailed_text = '''ABSTRACT

Background: Simufilam is a novel small molecule drug candidate that targets filamin A (FLNA), a key pathological protein in Alzheimer's disease (AD). Preclinical studies have shown that simufilam reverses aberrant receptor interactions of filamin A, restoring normal cellular function.

Methods: This was a Phase 2, randomized, double-blind, placebo-controlled study (NCT05515666) conducted at 12 sites in the United States. Patients aged 50-85 years with mild to moderate AD (MMSE 16-26) were enrolled. Key inclusion criteria included: confirmed AD diagnosis per NIA-AA criteria, stable cholinesterase inhibitor use, and caregiver availability. Exclusion criteria included: severe psychiatric disorders, recent stroke, or other neurodegenerative diseases.

Patients were randomized 1:1 to receive either simufilam 100mg twice daily or matching placebo for 52 weeks. Randomization was stratified by baseline MMSE score (16-20 vs 21-26) and site. The study was double-blinded with both patients and investigators unaware of treatment assignment.

Primary endpoint was change from baseline in ADAS-Cog11 score at Week 52. Secondary endpoints included: ADCS-ADL, NPI, CDR-SB, and safety assessments. Biomarker endpoints included plasma Aβ42/40 ratio, p-tau181, and neurofilament light chain. Statistical analysis used mixed-effects model for repeated measures (MMRM) with baseline score, treatment, visit, and treatment-by-visit interaction as fixed effects.

Results: A total of 64 patients were enrolled (32 per group). Baseline characteristics were balanced between groups. Mean age was 72.3 years, 56% female, mean MMSE 21.4. The study met its primary endpoint with simufilam showing a statistically significant improvement in ADAS-Cog11 score compared to placebo at Week 52 (LS mean difference: -2.3 points, 95% CI: -4.1 to -0.5, p=0.012).

Secondary endpoints also favored simufilam: ADCS-ADL (LS mean difference: 1.8 points, p=0.034), CDR-SB (LS mean difference: -0.4 points, p=0.021). Biomarker analysis showed trends toward improvement in plasma Aβ42/40 ratio in the simufilam group.

Safety: Simufilam was well-tolerated with no serious adverse events related to study drug. Most common adverse events were mild gastrointestinal symptoms (nausea 12.5%, diarrhea 9.4%) and headache (15.6%). No clinically significant laboratory abnormalities were observed.

Conclusions: Simufilam demonstrated statistically significant and clinically meaningful improvement in cognitive function in patients with mild to moderate AD. The safety profile was favorable with no serious adverse events. These results support advancement to Phase 3 development.

INTRODUCTION

Alzheimer's disease (AD) is the most common cause of dementia, affecting over 6 million Americans and 50 million people worldwide. Current treatments provide only modest symptomatic benefit, highlighting the urgent need for disease-modifying therapies.

Filamin A (FLNA) is a cytoskeletal protein that has been implicated in AD pathogenesis. In AD, FLNA undergoes aberrant interactions with various receptors, leading to cellular dysfunction and neurodegeneration. Simufilam is a novel small molecule that specifically targets these aberrant FLNA interactions, potentially restoring normal cellular function.

Preclinical studies have demonstrated that simufilam can reverse FLNA-mediated cellular dysfunction in AD models, leading to improved neuronal survival and reduced amyloid pathology. These findings provided the rationale for clinical development.

METHODS

Study Design: This was a Phase 2, randomized, double-blind, placebo-controlled, parallel-group study designed to evaluate the efficacy and safety of simufilam in patients with mild to moderate AD. The study was conducted in accordance with Good Clinical Practice guidelines and approved by institutional review boards at all participating sites.

Patients: Patients aged 50-85 years with mild to moderate AD (MMSE 16-26) were eligible for enrollment. AD diagnosis was confirmed per National Institute on Aging-Alzheimer's Association (NIA-AA) criteria. Patients were required to be on stable cholinesterase inhibitor therapy for at least 6 months prior to screening.

Key inclusion criteria included: confirmed AD diagnosis, MMSE score 16-26, stable cholinesterase inhibitor use, caregiver availability, and ability to complete study procedures. Exclusion criteria included: severe psychiatric disorders, recent stroke or other neurological conditions, significant cardiovascular disease, or other neurodegenerative diseases.

Randomization and Blinding: Patients were randomized 1:1 to receive either simufilam 100mg or matching placebo twice daily for 52 weeks. Randomization was stratified by baseline MMSE score (16-20 vs 21-26) and study site. The study was double-blinded with both patients and investigators unaware of treatment assignment.

Study Drug: Simufilam was provided as 50mg tablets. Patients took 2 tablets twice daily (total daily dose 200mg). Matching placebo tablets were identical in appearance and packaging.

Assessments: Primary endpoint was change from baseline in ADAS-Cog11 score at Week 52. Secondary efficacy endpoints included: ADCS-ADL, NPI, CDR-SB, and MMSE. Safety assessments included adverse event monitoring, vital signs, laboratory tests, and ECG.

Biomarker assessments included plasma Aβ42/40 ratio, p-tau181, and neurofilament light chain measured at baseline, Week 26, and Week 52.

Statistical Analysis: The primary analysis used mixed-effects model for repeated measures (MMRM) with baseline score, treatment, visit, and treatment-by-visit interaction as fixed effects. The analysis was conducted on the intent-to-treat (ITT) population. A two-sided alpha level of 0.05 was used for statistical significance.

Sample size calculation assumed a 2.5-point difference in ADAS-Cog11 change between groups, with 80% power and 15% dropout rate, resulting in a target enrollment of 60 patients.

RESULTS

Patient Disposition: A total of 64 patients were enrolled and randomized (32 per group). All patients received at least one dose of study drug and were included in the ITT analysis. Study completion rates were 87.5% in the simufilam group and 84.4% in the placebo group.

Baseline Characteristics: Patient demographics and baseline characteristics were well-balanced between treatment groups. Mean age was 72.3 years (range 55-84), 56% were female, and mean MMSE score was 21.4. Mean ADAS-Cog11 score was 18.2 in the simufilam group and 17.8 in the placebo group.

Efficacy Results: The study met its primary endpoint with simufilam showing a statistically significant improvement in ADAS-Cog11 score compared to placebo at Week 52. The least squares (LS) mean change from baseline was -1.2 points in the simufilam group versus +1.1 points in the placebo group (LS mean difference: -2.3 points, 95% CI: -4.1 to -0.5, p=0.012).

Secondary efficacy endpoints also favored simufilam: ADCS-ADL showed a 1.8-point improvement (p=0.034), CDR-SB showed a 0.4-point improvement (p=0.021), and MMSE showed a 1.2-point improvement (p=0.045). The NPI total score showed a trend toward improvement but did not reach statistical significance.

Biomarker Results: Plasma Aβ42/40 ratio showed a trend toward improvement in the simufilam group compared to placebo, though the difference was not statistically significant. P-tau181 levels remained stable in both groups. Neurofilament light chain levels showed a trend toward reduction in the simufilam group.

Safety Results: Simufilam was well-tolerated with no serious adverse events related to study drug. The most common adverse events were mild gastrointestinal symptoms including nausea (12.5% vs 6.3% placebo) and diarrhea (9.4% vs 3.1% placebo). Headache occurred in 15.6% of simufilam patients versus 12.5% of placebo patients.

No clinically significant laboratory abnormalities were observed. Vital signs remained stable throughout the study. No patients discontinued due to adverse events.

DISCUSSION

This Phase 2 study demonstrated that simufilam, a novel small molecule targeting filamin A, provided statistically significant and clinically meaningful improvement in cognitive function in patients with mild to moderate AD. The 2.3-point difference in ADAS-Cog11 score exceeds the generally accepted threshold for clinical meaningfulness in AD trials.

The safety profile was favorable with no serious adverse events and only mild, manageable side effects. The gastrointestinal side effects observed are consistent with the drug's mechanism of action and were generally mild in severity.

The biomarker results, while not statistically significant, showed trends consistent with potential disease modification. The improvement in plasma Aβ42/40 ratio suggests potential effects on amyloid metabolism, though longer-term studies would be needed to confirm this.

These results support the continued development of simufilam as a potential disease-modifying therapy for AD. The favorable safety profile and promising efficacy signal warrant advancement to Phase 3 development.

CONCLUSIONS

Simufilam demonstrated statistically significant and clinically meaningful improvement in cognitive function in patients with mild to moderate AD. The drug was well-tolerated with no serious adverse events. These results support advancement to Phase 3 development and suggest potential disease-modifying effects that warrant further investigation.

The study provides proof-of-concept for the filamin A targeting approach in AD and represents a novel therapeutic strategy that may complement existing treatments. Future studies should evaluate longer-term efficacy and safety, as well as potential combination therapy approaches.'''
        
        cur.execute("""
            INSERT INTO document_text (doc_id, fulltext_text, abstract_text)
            VALUES (1, %s, %s)
        """, (
            detailed_text,
            'Simufilam is a small molecule drug candidate for Alzheimer\'s disease that targets filamin A. This Phase 2 study demonstrates its efficacy and safety profile in a randomized, double-blind, placebo-controlled trial of 64 patients with mild to moderate AD.'
        ))
        
        # Link the document to the trial
        print("Creating document link...")
        cur.execute("""
            INSERT INTO document_links (doc_id, trial_id, nct_id, asset_id, company_id, link_type)
            VALUES (1, 1, 'NCT05515666', NULL, 1, 'NCT_MATCH')
        """)
        
        # Mark as selected for study card processing
        print("Marking document as selected...")
        cur.execute("""
            INSERT INTO trial_doc_candidates (trial_id, doc_id, stage, selected)
            VALUES (1, 1, 'U1_abstract', TRUE)
        """)
        
        # Create a study card task
        print("Creating study card task...")
        cur.execute("""
            INSERT INTO tasks (task_type, task_key, trial_id, company_id, priority, status, payload, created_at, updated_at)
            VALUES ('STUDYCARD', 'test_studycard_1_phase2', 1, 1, 0, 'queued', '{"source": "manual_test", "trial_id": 1}', NOW(), NOW())
        """)
        
        # Verify the setup
        print("\nVerifying setup...")
        cur.execute("""
            SELECT 'Companies' as table_name, count(*) as count FROM companies
            UNION ALL
            SELECT 'Trials', count(*) FROM trials
            UNION ALL
            SELECT 'Documents', count(*) FROM documents
            UNION ALL
            SELECT 'Document Text', count(*) FROM document_text
            UNION ALL
            SELECT 'Document Links', count(*) FROM document_links
            UNION ALL
            SELECT 'Trial Doc Candidates', count(*) FROM trial_doc_candidates
            UNION ALL
            SELECT 'Tasks', count(*) FROM tasks
        """)
        
        results = cur.fetchall()
        for row in results:
            print(f"  {row['table_name']}: {row['count']}")
        
        # Show document length
        cur.execute("SELECT LENGTH(fulltext_text) as text_length FROM document_text WHERE doc_id = 1")
        text_length = cur.fetchone()['text_length']
        print(f"\nDocument text length: {text_length:,} characters")
        
        print("\n✅ Detailed study card test data setup complete!")
        print("You can now test the new direct LLM card generation approach.")
        
    except Exception as e:
        print(f"❌ Error setting up test data: {e}")
        raise
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    setup_detailed_test_data()
