"""
Temporal analysis: Reconstruct company portfolio state at time of trial start.

This makes analysis predictive rather than descriptive by showing what signals
existed BEFORE the trial failed, not after.
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from sqlalchemy import text

def analyze_trial_at_start_time(nct_id: str):
    """
    Analyze a trial by reconstructing the company's portfolio state
    at the time the trial started.
    """
    
    with get_db_session() as session:
        print('=' * 80)
        print(f'TEMPORAL ANALYSIS: {nct_id}')
        print('=' * 80)
        print()
        
        # Get the trial details
        query = text('''
            SELECT 
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
                d.drug_id,
                d.primary_name as drug_name
            FROM clinical_trials t
            JOIN trial_sponsors ts ON t.trial_id = ts.trial_id
                AND ts.entity_type = 'company'
            JOIN companies c ON ts.entity_id = c.company_id
            LEFT JOIN trial_drugs td ON t.trial_id = td.trial_id
            LEFT JOIN drugs d ON td.drug_id = d.drug_id
            WHERE t.nct_id = :nct_id
              AND t.deleted_at IS NULL
            ORDER BY ts.sponsor_role
            LIMIT 1
        ''')
        
        result = session.execute(query, {'nct_id': nct_id}).fetchone()
        
        if not result:
            print(f'Trial {nct_id} not found')
            return
        
        trial_id = result[0]
        nct = result[1]
        title = result[2]
        phase = result[3]
        status = result[4]
        start_date = result[5]
        primary_completion = result[6]
        completion = result[7]
        company_id = result[8]
        company_name = result[9]
        drug_id = result[10]
        drug_name = result[11]
        
        print(f'Trial: {nct}')
        print(f'Title: {title[:70]}...')
        print(f'Phase: {phase}, Status: {status}')
        print(f'Company: {company_name}')
        print(f'Drug: {drug_name}')
        print(f'Start date: {start_date}')
        print()
        
        if not start_date:
            print('⚠️  No start date available - cannot do temporal analysis')
            return
        
        print('=' * 80)
        print(f'COMPANY PORTFOLIO STATE AT {start_date}')
        print('=' * 80)
        print()
        
        # Get all company trials that started BEFORE this trial
        query2 = text('''
            SELECT 
                t.trial_id,
                t.nct_id,
                t.trial_title,
                t.phase,
                t.status,
                t.start_date,
                t.primary_completion_date,
                t.completion_date
            FROM clinical_trials t
            JOIN trial_sponsors ts ON t.trial_id = ts.trial_id
            WHERE ts.entity_id = :company_id
              AND ts.entity_type = 'company'
              AND t.start_date IS NOT NULL
              AND t.start_date < :trial_start_date
              AND t.deleted_at IS NULL
            ORDER BY t.start_date DESC
        ''')
        
        prior_trials = session.execute(query2, {
            'company_id': company_id,
            'trial_start_date': start_date
        }).fetchall()
        
        print(f'Trials that started BEFORE {start_date}: {len(prior_trials)}')
        print()
        
        if prior_trials:
            # Calculate termination rate based on trials that had outcomes by start_date
            # Use status as primary indicator since completion dates are often NULL
            
            terminated_before = 0
            completed_before = 0
            active_at_start = 0
            unknown_status = 0
            
            print('Prior trials:')
            for pt in prior_trials[:10]:  # Show first 10
                pt_nct = pt[1]
                pt_title = (pt[2] or 'N/A')[:50]
                pt_phase = pt[3] or 'N/A'
                pt_status = pt[4] or 'N/A'
                pt_start = pt[5]
                pt_completion = pt[6]
                
                # Determine outcome status at time of trial start
                # If status is terminated/completed, assume it happened before start_date
                # (since we're looking at trials that started before)
                if pt_status == 'terminated':
                    # Check if completion date suggests it was before start
                    if pt_completion and pt_completion < start_date:
                        terminated_before += 1
                        outcome = 'TERMINATED (before start)'
                    elif pt_completion and pt_completion >= start_date:
                        # Terminated after our trial started - was active at start
                        active_at_start += 1
                        outcome = 'TERMINATED (was active at start)'
                    else:
                        # No completion date - assume terminated before (conservative)
                        terminated_before += 1
                        outcome = 'TERMINATED (assumed before)'
                elif pt_status == 'completed':
                    if pt_completion and pt_completion < start_date:
                        completed_before += 1
                        outcome = 'COMPLETED (before start)'
                    elif pt_completion and pt_completion >= start_date:
                        active_at_start += 1
                        outcome = 'COMPLETED (was active at start)'
                    else:
                        # No completion date - assume completed before
                        completed_before += 1
                        outcome = 'COMPLETED (assumed before)'
                elif pt_status in ('recruiting', 'active_not_recruiting', 'enrolling_by_invitation'):
                    active_at_start += 1
                    outcome = 'ACTIVE at start'
                elif pt_status in ('withdrawn', 'suspended'):
                    terminated_before += 1
                    outcome = f'{pt_status.upper()} (counted as terminated)'
                else:
                    unknown_status += 1
                    outcome = f'{pt_status} (unknown)'
                
                print(f'  • {pt_nct}: {pt_phase} {pt_status} - {outcome}')
                print(f'    Started: {pt_start}, Completion: {pt_completion or "N/A"}')
            
            if len(prior_trials) > 10:
                print(f'  ... and {len(prior_trials) - 10} more')
            
            print()
            print('Portfolio metrics at trial start:')
            total_with_outcome = terminated_before + completed_before
            if total_with_outcome > 0:
                termination_rate = (terminated_before / total_with_outcome) * 100
                print(f'  - Trials with outcomes: {total_with_outcome}')
                print(f'  - Terminated: {terminated_before} ({termination_rate:.1f}%)')
                print(f'  - Completed: {completed_before}')
                print(f'  - Active at start: {active_at_start}')
                print(f'  - Unknown status: {unknown_status}')
            else:
                print(f'  - No trials with outcomes before this trial started')
                print(f'  - This was their first trial with outcome data')
        else:
            print('This appears to be one of the company\'s earliest trials')
        
        print()
        print('=' * 80)
        print('CONCURRENT TRIALS (Started before, still active at trial start)')
        print('=' * 80)
        print()
        
        # Get trials that started before but were still active
        query3 = text('''
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
              AND t.start_date IS NOT NULL
              AND t.start_date < :trial_start_date
              AND t.trial_id != :trial_id
              AND t.deleted_at IS NULL
              AND (
                  t.status IN ('recruiting', 'active_not_recruiting', 'enrolling_by_invitation')
                  OR (t.status = 'completed' AND (t.completion_date IS NULL OR t.completion_date >= :trial_start_date))
                  OR (t.status = 'terminated' AND (t.completion_date IS NULL OR t.completion_date >= :trial_start_date))
              )
            ORDER BY t.start_date DESC
            LIMIT 10
        ''')
        
        concurrent = session.execute(query3, {
            'company_id': company_id,
            'trial_start_date': start_date,
            'trial_id': trial_id
        }).fetchall()
        
        if concurrent:
            print(f'Trials likely active when {nct} started: {len(concurrent)}')
            for ct in concurrent:
                print(f'  • {ct[0]}: {ct[2]} {ct[3]} - {ct[5] or "N/A"} (started: {ct[4]})')
        else:
            print('No concurrent trials found')
        
        print()
        print('=' * 80)
        print('DRUG HISTORY BEFORE THIS TRIAL')
        print('=' * 80)
        print()
        
        if drug_id:
            query4 = text('''
                SELECT 
                    t.nct_id,
                    t.phase,
                    t.status,
                    t.start_date,
                    t.primary_completion_date,
                    t.completion_date
                FROM clinical_trials t
                JOIN trial_drugs td ON t.trial_id = td.trial_id
                WHERE td.drug_id = :drug_id
                  AND t.trial_id != :trial_id
                  AND t.deleted_at IS NULL
                  AND (
                      t.start_date IS NULL 
                      OR t.start_date < :trial_start_date
                  )
                ORDER BY t.start_date NULLS LAST, t.nct_id
            ''')
            
            prior_drug_trials = session.execute(query4, {
                'drug_id': drug_id,
                'trial_id': trial_id,
                'trial_start_date': start_date
            }).fetchall()
            
            if prior_drug_trials:
                print(f'Trials for {drug_name} before this trial: {len(prior_drug_trials)}')
                for pdt in prior_drug_trials:
                    print(f'  • {pdt[0]}: {pdt[1]} {pdt[2]} (started: {pdt[3] or "N/A"})')
            else:
                print(f'This appears to be the first trial for {drug_name}')
        else:
            print('Drug information not available')


if __name__ == '__main__':
    # Try a trial with a start date
    # NCT04152863 (Merck) has start_date: 2020-06-05
    analyze_trial_at_start_time('NCT04152863')


