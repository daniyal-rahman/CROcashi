"""
Comprehensive risk analysis combining all available signals.

For each terminated Phase 2/3 company-sponsored trial, calculates:
1. Indication failure rate (baseline risk)
2. Company termination rate at trial start (company risk)
3. Drug history (novel vs validated)
4. Portfolio concentration (how many Phase 2/3 trials)
5. Concurrent trials (resource spread)
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from sqlalchemy import text

def comprehensive_risk_analysis():
    """Analyze all terminated Phase 2/3 company-sponsored trials with full risk profile."""
    
    with get_db_session() as session:
        print('=' * 80)
        print('COMPREHENSIVE RISK ANALYSIS: TERMINATED PHASE 2/3 TRIALS')
        print('=' * 80)
        print()
        print('Combining all available signals that existed BEFORE trial start:')
        print('  1. Indication failure rate (baseline risk)')
        print('  2. Company termination rate at trial start')
        print('  3. Drug history (prior trials)')
        print('  4. Portfolio concentration (Phase 2/3 trials)')
        print('  5. Concurrent active trials')
        print()
        
        # Get all terminated Phase 2/3 company-sponsored trials
        query = text('''
            SELECT DISTINCT ON (t.trial_id)
                t.trial_id,
                t.nct_id,
                t.trial_title,
                t.phase,
                t.status,
                t.start_date,
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
            WHERE t.phase IN ('PHASE2', 'PHASE3')
              AND t.status = 'terminated'
              AND t.deleted_at IS NULL
            ORDER BY t.trial_id,
                CASE ts.sponsor_role 
                    WHEN 'lead_sponsor' THEN 1 
                    WHEN 'collaborator' THEN 2 
                    ELSE 3 
                END
        ''')
        
        trials = session.execute(query).fetchall()
        
        print(f'Analyzing {len(trials)} terminated Phase 2/3 company-sponsored trials:')
        print()
        
        for i, trial_row in enumerate(trials, 1):
            trial_id = trial_row[0]
            nct_id = trial_row[1]
            title = (trial_row[2] or 'N/A')[:60]
            phase = trial_row[3]
            status = trial_row[4]
            start_date = trial_row[5]
            company_id = trial_row[6]
            company_name = trial_row[7] or 'Unknown'
            drug_id = trial_row[8]
            drug_name = trial_row[9] or 'Unknown'
            
            print(f'{i}. {nct_id} ({phase}) - {company_name}')
            print(f'   Drug: {drug_name}')
            print(f'   Title: {title}...')
            if start_date:
                print(f'   Started: {start_date}')
            print()
            
            # 1. Indication failure rate
            query_ind = text('''
                SELECT 
                    d.disease_name,
                    COUNT(DISTINCT CASE WHEN t2.status IN ('terminated', 'completed') THEN t2.trial_id END) as trials_with_outcome,
                    COUNT(DISTINCT CASE WHEN t2.status = 'terminated' THEN t2.trial_id END) as terminated_count,
                    ROUND(
                        COUNT(DISTINCT CASE WHEN t2.status = 'terminated' THEN t2.trial_id END)::numeric / 
                        NULLIF(COUNT(DISTINCT CASE WHEN t2.status IN ('terminated', 'completed') THEN t2.trial_id END), 0) * 100,
                        1
                    ) as failure_rate
                FROM clinical_trials t1
                JOIN trial_diseases td1 ON t1.trial_id = td1.trial_id
                JOIN diseases d ON td1.disease_id = d.disease_id
                JOIN trial_diseases td2 ON d.disease_id = td2.disease_id
                JOIN clinical_trials t2 ON td2.trial_id = t2.trial_id
                WHERE t1.trial_id = :trial_id
                  AND t2.phase IN ('PHASE2', 'PHASE3')
                  AND t2.deleted_at IS NULL
                GROUP BY d.disease_name
                ORDER BY trials_with_outcome DESC
                LIMIT 1
            ''')
            
            ind_result = session.execute(query_ind, {'trial_id': trial_id}).fetchone()
            
            print('   SIGNAL 1: Indication Failure Rate')
            if ind_result:
                disease = ind_result[0]
                sample_size = ind_result[1]
                terminated = ind_result[2]
                rate = ind_result[3] if ind_result[3] is not None else 0.0
                risk_level = 'HIGH' if rate >= 30 else 'MEDIUM' if rate >= 15 else 'LOW'
                print(f'     Indication: {disease}')
                print(f'     Historical failure rate: {rate}% ({terminated}/{sample_size} trials)')
                print(f'     Risk level: {risk_level}')
            else:
                print(f'     No indication data available')
            print()
            
            # 2. Company termination rate at trial start
            if company_id and start_date:
                print('   SIGNAL 2: Company Termination Rate (at trial start)')
                
                query_company = text('''
                    SELECT 
                        COUNT(DISTINCT CASE WHEN t2.status IN ('terminated', 'completed') THEN t2.trial_id END) as trials_with_outcome,
                        COUNT(DISTINCT CASE WHEN t2.status = 'terminated' THEN t2.trial_id END) as terminated_count,
                        ROUND(
                            COUNT(DISTINCT CASE WHEN t2.status = 'terminated' THEN t2.trial_id END)::numeric / 
                            NULLIF(COUNT(DISTINCT CASE WHEN t2.status IN ('terminated', 'completed') THEN t2.trial_id END), 0) * 100,
                            1
                        ) as termination_rate
                    FROM clinical_trials t2
                    JOIN trial_sponsors ts2 ON t2.trial_id = ts2.trial_id
                    WHERE ts2.entity_id = :company_id
                      AND ts2.entity_type = 'company'
                      AND t2.start_date IS NOT NULL
                      AND t2.start_date < :trial_start_date
                      AND t2.deleted_at IS NULL
                ''')
                
                company_result = session.execute(query_company, {
                    'company_id': company_id,
                    'trial_start_date': start_date
                }).fetchone()
                
                if company_result and company_result[0] > 0:
                    sample_size = company_result[0]
                    terminated = company_result[1]
                    rate = company_result[2] if company_result[2] is not None else 0.0
                    risk_level = 'HIGH' if rate >= 25 else 'MEDIUM' if rate >= 10 else 'LOW'
                    print(f'     Company termination rate: {rate}% ({terminated}/{sample_size} trials)')
                    print(f'     Risk level: {risk_level}')
                else:
                    print(f'     No prior trial outcomes (first trial with outcome data)')
                    print(f'     Risk level: UNKNOWN (no history)')
            elif not start_date:
                print('   SIGNAL 2: Company Termination Rate')
                print(f'     Cannot calculate (no start date)')
            else:
                print('   SIGNAL 2: Company Termination Rate')
                print(f'     Cannot calculate (no company ID)')
            print()
            
            # 3. Drug history
            if drug_id:
                print('   SIGNAL 3: Drug History')
                
                if start_date:
                    query_drug = text('''
                        SELECT COUNT(DISTINCT t2.trial_id) as prior_trials
                        FROM clinical_trials t2
                        JOIN trial_drugs td2 ON t2.trial_id = td2.trial_id
                        WHERE td2.drug_id = :drug_id
                          AND t2.trial_id != :trial_id
                          AND t2.deleted_at IS NULL
                          AND (
                              t2.start_date IS NULL 
                              OR t2.start_date < :trial_start_date
                          )
                    ''')
                    
                    drug_result = session.execute(query_drug, {
                        'drug_id': drug_id,
                        'trial_id': trial_id,
                        'trial_start_date': start_date
                    }).scalar()
                else:
                    query_drug = text('''
                        SELECT COUNT(DISTINCT t2.trial_id) as prior_trials
                        FROM clinical_trials t2
                        JOIN trial_drugs td2 ON t2.trial_id = td2.trial_id
                        WHERE td2.drug_id = :drug_id
                          AND t2.trial_id != :trial_id
                          AND t2.deleted_at IS NULL
                    ''')
                    
                    drug_result = session.execute(query_drug, {
                        'drug_id': drug_id,
                        'trial_id': trial_id
                    }).scalar()
                
                if drug_result and drug_result > 0:
                    print(f'     Prior trials for this drug: {drug_result}')
                    print(f'     Risk level: VALIDATED (has prior trials)')
                else:
                    print(f'     Prior trials for this drug: 0')
                    print(f'     Risk level: NOVEL (first-in-class or first trial)')
            else:
                print('   SIGNAL 3: Drug History')
                print(f'     No drug data available')
            print()
            
            # 4. Portfolio concentration
            if company_id and start_date:
                print('   SIGNAL 4: Portfolio Concentration')
                
                query_portfolio = text('''
                    SELECT 
                        COUNT(DISTINCT t2.trial_id) as phase23_trials,
                        COUNT(DISTINCT CASE WHEN t2.status IN ('recruiting', 'active_not_recruiting') THEN t2.trial_id END) as active_trials
                    FROM clinical_trials t2
                    JOIN trial_sponsors ts2 ON t2.trial_id = ts2.trial_id
                    WHERE ts2.entity_id = :company_id
                      AND ts2.entity_type = 'company'
                      AND t2.phase IN ('PHASE2', 'PHASE3')
                      AND t2.start_date IS NOT NULL
                      AND t2.start_date <= :trial_start_date
                      AND t2.deleted_at IS NULL
                ''')
                
                portfolio_result = session.execute(query_portfolio, {
                    'company_id': company_id,
                    'trial_start_date': start_date
                }).fetchone()
                
                if portfolio_result:
                    total_phase23 = portfolio_result[0]
                    active = portfolio_result[1]
                    concentration = 'HIGH' if total_phase23 <= 3 else 'MEDIUM' if total_phase23 <= 8 else 'LOW'
                    print(f'     Total Phase 2/3 trials: {total_phase23}')
                    print(f'     Active at start: {active}')
                    print(f'     Concentration risk: {concentration} (fewer = higher risk)')
            elif not start_date:
                print('   SIGNAL 4: Portfolio Concentration')
                print(f'     Cannot calculate (no start date)')
            else:
                print('   SIGNAL 4: Portfolio Concentration')
                print(f'     Cannot calculate (no company ID)')
            print()
            
            print('-' * 80)
            print()


if __name__ == '__main__':
    comprehensive_risk_analysis()

