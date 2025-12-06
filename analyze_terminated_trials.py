"""
Analyze terminated Phase 2/3 trials with full context.

For each terminated trial, shows:
- Company and drug
- Company's portfolio (other trials, termination rate)
- Drug's history (other trials, what phase it was in before)
- Timeline (what happened before termination)
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from sqlalchemy import text

def analyze_terminated_trials(limit=5, company_sponsored_only=True):
    """
    Analyze terminated Phase 2/3 trials with full context.
    
    Args:
        limit: Number of trials to analyze
        company_sponsored_only: If True, only include trials with company sponsors
    """
    
    with get_db_session() as session:
        print('=' * 80)
        print('TERMINATED PHASE 2/3 TRIALS - COMPANY-SPONSORED ANALYSIS')
        print('=' * 80)
        print()
        
        if company_sponsored_only:
            print('Scope: Company-sponsored trials only (commercial intent, clearer failure signals)')
        else:
            print('Scope: All terminated trials')
        print()
        
        # Get unique terminated trials with company and primary drug
        # Prioritize: company lead_sponsor > company collaborator
        query = text('''
            WITH trial_companies AS (
                SELECT DISTINCT ON (t.trial_id)
                    t.trial_id,
                    t.nct_id,
                    t.trial_title,
                    t.phase,
                    t.status,
                    t.start_date,
                    t.primary_completion_date,
                    t.completion_date,
                    c.company_id,
                    c.name as company_name,
                    ts.sponsor_role
                FROM clinical_trials t
                JOIN trial_sponsors ts ON t.trial_id = ts.trial_id 
                    AND ts.entity_type = 'company'
                LEFT JOIN companies c ON ts.entity_id = c.company_id
                WHERE t.phase IN ('PHASE2', 'PHASE3')
                  AND t.status = 'terminated'
                  AND t.deleted_at IS NULL
                ORDER BY t.trial_id, 
                    CASE ts.sponsor_role 
                        WHEN 'lead_sponsor' THEN 1 
                        WHEN 'collaborator' THEN 2 
                        ELSE 3 
                    END,
                    c.name NULLS LAST
            ),
            trial_drugs_primary AS (
                SELECT DISTINCT ON (t.trial_id)
                    t.trial_id,
                    d.drug_id,
                    d.primary_name as drug_name
                FROM clinical_trials t
                JOIN trial_drugs td ON t.trial_id = td.trial_id
                JOIN drugs d ON td.drug_id = d.drug_id
                WHERE t.phase IN ('PHASE2', 'PHASE3')
                  AND t.status = 'terminated'
                  AND t.deleted_at IS NULL
                ORDER BY t.trial_id, d.primary_name
            )
            SELECT DISTINCT ON (tc.trial_id)
                tc.trial_id,
                tc.nct_id,
                tc.trial_title,
                tc.phase,
                tc.status,
                tc.start_date,
                tc.primary_completion_date,
                tc.completion_date,
                tc.company_id,
                tc.company_name,
                td.drug_id,
                td.drug_name
            FROM trial_companies tc
            LEFT JOIN trial_drugs_primary td ON tc.trial_id = td.trial_id
            ORDER BY tc.trial_id, tc.phase, tc.nct_id
            LIMIT :limit
        ''')
        
        results = session.execute(query, {'limit': limit}).fetchall()
        
        print(f'Analyzing {len(results)} terminated Phase 2/3 trials:')
        print()
        
        for i, row in enumerate(results, 1):
            trial_id = row[0]
            nct_id = row[1] or 'N/A'
            title = (row[2] or 'N/A')[:70]
            phase = row[3] or 'N/A'
            status = row[4] or 'N/A'
            start_date = row[5]
            primary_completion = row[6]
            completion = row[7]
            company_id = row[8]
            company_name = row[9] or 'Unknown'
            drug_id = row[10]
            drug_name = row[11] or 'Unknown'
            
            print(f'{i}. {nct_id} ({phase}) - {status.upper()}')
            print(f'   Title: {title}...')
            print(f'   Company: {company_name}')
            print(f'   Drug: {drug_name}')
            if start_date:
                print(f'   Started: {start_date}')
            if primary_completion:
                print(f'   Primary completion: {primary_completion}')
            if completion:
                print(f'   Completed: {completion}')
            print()
            
            # Company portfolio analysis
            if company_id:
                print('   COMPANY PORTFOLIO:')
                
                # All company trials
                query2 = text('''
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN status = 'terminated' THEN 1 END) as terminated,
                        COUNT(CASE WHEN status = 'withdrawn' THEN 1 END) as withdrawn,
                        COUNT(CASE WHEN phase IN ('PHASE2', 'PHASE3') THEN 1 END) as phase23,
                        COUNT(CASE WHEN phase IN ('PHASE2', 'PHASE3') AND status = 'terminated' THEN 1 END) as phase23_term
                    FROM clinical_trials t
                    JOIN trial_sponsors ts ON t.trial_id = ts.trial_id
                    WHERE ts.entity_id = :company_id
                      AND ts.entity_type = 'company'
                      AND t.deleted_at IS NULL
                ''')
                
                company_stats = session.execute(query2, {'company_id': company_id}).fetchone()
                if company_stats:
                    total = company_stats[0]
                    terminated = company_stats[1]
                    withdrawn = company_stats[2]
                    phase23 = company_stats[3]
                    phase23_term = company_stats[4]
                    
                    print(f'     - Total trials: {total}')
                    if total > 0:
                        print(f'     - Terminated: {terminated} ({terminated/total*100:.1f}%)')
                        print(f'     - Withdrawn: {withdrawn}')
                        print(f'     - Phase 2/3 trials: {phase23}')
                        if phase23 > 0:
                            print(f'     - Phase 2/3 terminated: {phase23_term} ({phase23_term/phase23*100:.1f}%)')
                
                # Company's other drugs
                query3 = text('''
                    SELECT COUNT(DISTINCT d.drug_id) as drug_count
                    FROM company_drugs cd
                    JOIN drugs d ON cd.drug_id = d.drug_id
                    WHERE cd.company_id = :company_id
                      AND cd.deleted_at IS NULL
                ''')
                
                drug_count = session.execute(query3, {'company_id': company_id}).scalar()
                print(f'     - Total drugs in portfolio: {drug_count or 0}')
                
                # Company's other Phase 2/3 trials (context)
                query4 = text('''
                    SELECT 
                        t.nct_id,
                        t.trial_title,
                        t.phase,
                        t.status,
                        t.start_date,
                        d.primary_name as drug_name
                    FROM clinical_trials t
                    JOIN trial_sponsors ts ON t.trial_id = ts.trial_id
                    LEFT JOIN trial_drugs td ON t.trial_id = td.trial_id
                    LEFT JOIN drugs d ON td.drug_id = d.drug_id
                    WHERE ts.entity_id = :company_id
                      AND ts.entity_type = 'company'
                      AND t.phase IN ('PHASE2', 'PHASE3')
                      AND t.trial_id != :current_trial_id
                      AND t.deleted_at IS NULL
                    ORDER BY t.start_date NULLS LAST, t.nct_id
                    LIMIT 10
                ''')
                
                other_trials = session.execute(query4, {
                    'company_id': company_id,
                    'current_trial_id': trial_id
                }).fetchall()
                
                if other_trials:
                    print(f'     - Other Phase 2/3 trials in portfolio:')
                    for ot in other_trials:
                        nct = ot[0] or 'N/A'
                        title = (ot[1] or 'N/A')[:50]
                        phase = ot[2] or 'N/A'
                        status = ot[3] or 'N/A'
                        start = ot[4] or 'N/A'
                        drug = ot[5] or 'N/A'
                        print(f'       • {nct}: {phase} {status} - {drug} (started: {start})')
                print()
            
            # Drug history analysis
            if drug_id:
                print('   DRUG HISTORY:')
                
                # All drug trials, ordered by start date
                query4 = text('''
                    SELECT 
                        t.nct_id,
                        t.phase,
                        t.status,
                        t.start_date,
                        t.primary_completion_date,
                        CASE 
                            WHEN t.start_date < :trial_start THEN 'BEFORE'
                            WHEN t.start_date = :trial_start THEN 'SAME'
                            ELSE 'AFTER'
                        END as timeline
                    FROM clinical_trials t
                    JOIN trial_drugs td ON t.trial_id = td.trial_id
                    WHERE td.drug_id = :drug_id
                      AND t.deleted_at IS NULL
                    ORDER BY t.start_date NULLS LAST, t.nct_id
                ''')
                
                drug_trials = session.execute(query4, {
                    'drug_id': drug_id,
                    'trial_start': start_date if start_date else datetime(1900, 1, 1)
                }).fetchall()
                
                if drug_trials:
                    print(f'     - Total trials for this drug: {len(drug_trials)}')
                    print(f'     - Trial timeline:')
                    
                    before_trials = [t for t in drug_trials if t[5] == 'BEFORE']
                    if before_trials:
                        print(f'       BEFORE this trial:')
                        for trial in before_trials[:5]:  # Show first 5
                            start_str = str(trial[3]) if trial[3] else 'N/A'
                            print(f'         • {trial[0]}: {trial[1]} {trial[2]} (started: {start_str})')
                    
                    same_trials = [t for t in drug_trials if t[5] == 'SAME']
                    if same_trials:
                        print(f'       SAME time as this trial:')
                        for trial in same_trials:
                            if trial[0] != nct_id:  # Don't show the current trial
                                print(f'         • {trial[0]}: {trial[1]} {trial[2]}')
                    
                    after_trials = [t for t in drug_trials if t[5] == 'AFTER']
                    if after_trials:
                        print(f'       AFTER this trial:')
                        for trial in after_trials[:5]:  # Show first 5
                            start_str = str(trial[3]) if trial[3] else 'N/A'
                            print(f'         • {trial[0]}: {trial[1]} {trial[2]} (started: {start_str})')
                else:
                    print(f'     - No other trials found for this drug')
                print()
            
            print('-' * 80)
            print()


if __name__ == '__main__':
    analyze_terminated_trials(limit=5, company_sponsored_only=True)


