"""
Calculate indication-level failure rates.

These are signals that exist BEFORE any specific trial starts - you can know
the historical failure rate for an indication regardless of company.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from sqlalchemy import text

def calculate_indication_failure_rates():
    """Calculate failure rates by indication/disease area."""
    
    with get_db_session() as session:
        print('=' * 80)
        print('INDICATION-LEVEL FAILURE RATES')
        print('=' * 80)
        print()
        print('These rates exist BEFORE any trial starts - predictive signals.')
        print()
        
        # Calculate failure rates by disease
        query = text('''
            SELECT 
                d.disease_name,
                COUNT(DISTINCT t.trial_id) as total_trials,
                COUNT(DISTINCT CASE WHEN t.status = 'terminated' THEN t.trial_id END) as terminated,
                COUNT(DISTINCT CASE WHEN t.status = 'completed' THEN t.trial_id END) as completed,
                COUNT(DISTINCT CASE WHEN t.status IN ('recruiting', 'active_not_recruiting') THEN t.trial_id END) as active,
                ROUND(
                    COUNT(DISTINCT CASE WHEN t.status = 'terminated' THEN t.trial_id END)::numeric / 
                    NULLIF(COUNT(DISTINCT CASE WHEN t.status IN ('terminated', 'completed') THEN t.trial_id END), 0) * 100,
                    1
                ) as failure_rate_pct
            FROM clinical_trials t
            JOIN trial_diseases td ON t.trial_id = td.trial_id
            JOIN diseases d ON td.disease_id = d.disease_id
            WHERE t.phase IN ('PHASE2', 'PHASE3')
              AND t.deleted_at IS NULL
            GROUP BY d.disease_name
            HAVING COUNT(DISTINCT CASE WHEN t.status IN ('terminated', 'completed') THEN t.trial_id END) >= 3
            ORDER BY failure_rate_pct DESC NULLS LAST, total_trials DESC
            LIMIT 30
        ''')
        
        results = session.execute(query).fetchall()
        
        print('Top indications by failure rate (Phase 2/3, ≥3 completed/terminated):')
        print()
        print(f'{"Indication":<50} {"Total":>6} {"Term":>5} {"Comp":>5} {"Active":>6} {"Rate":>6}')
        print('-' * 80)
        
        for row in results:
            disease = row[0][:48]
            total = row[1]
            terminated = row[2]
            completed = row[3]
            active = row[4]
            rate = row[5] if row[5] is not None else 0.0
            
            # Highlight high-risk indications
            risk_marker = '⚠️ ' if rate >= 30 else '   '
            
            print(f'{risk_marker}{disease:<48} {total:>6} {terminated:>5} {completed:>5} {active:>6} {rate:>5.1f}%')
        
        print()
        print('=' * 80)
        print('APPLYING TO TERMINATED TRIALS')
        print('=' * 80)
        print()
        
        # Show what indication failure rates were for our terminated trials
        query2 = text('''
            WITH indication_rates AS (
                SELECT 
                    d.disease_id,
                    d.disease_name,
                    COUNT(DISTINCT CASE WHEN t.status IN ('terminated', 'completed') THEN t.trial_id END) as trials_with_outcome,
                    COUNT(DISTINCT CASE WHEN t.status = 'terminated' THEN t.trial_id END) as terminated_count,
                    ROUND(
                        COUNT(DISTINCT CASE WHEN t.status = 'terminated' THEN t.trial_id END)::numeric / 
                        NULLIF(COUNT(DISTINCT CASE WHEN t.status IN ('terminated', 'completed') THEN t.trial_id END), 0) * 100,
                        1
                    ) as failure_rate
                FROM clinical_trials t
                JOIN trial_diseases td ON t.trial_id = td.trial_id
                JOIN diseases d ON td.disease_id = d.disease_id
                WHERE t.phase IN ('PHASE2', 'PHASE3')
                  AND t.deleted_at IS NULL
                GROUP BY d.disease_id, d.disease_name
            )
            SELECT 
                t.nct_id,
                t.trial_title,
                t.phase,
                c.name as company,
                d.disease_name,
                ir.failure_rate,
                ir.trials_with_outcome
            FROM clinical_trials t
            JOIN trial_sponsors ts ON t.trial_id = ts.trial_id AND ts.entity_type = 'company'
            JOIN companies c ON ts.entity_id = c.company_id
            JOIN trial_diseases td ON t.trial_id = td.trial_id
            JOIN diseases d ON td.disease_id = d.disease_id
            LEFT JOIN indication_rates ir ON d.disease_id = ir.disease_id
            WHERE t.phase IN ('PHASE2', 'PHASE3')
              AND t.status = 'terminated'
              AND t.deleted_at IS NULL
            ORDER BY ir.failure_rate DESC NULLS LAST
            LIMIT 10
        ''')
        
        results2 = session.execute(query2).fetchall()
        
        if results2:
            print('Terminated company-sponsored trials and their indication failure rates:')
            print()
            for row in results2:
                nct = row[0]
                title = (row[1] or 'N/A')[:45]
                phase = row[2]
                company = row[3] or 'Unknown'
                disease = row[4] or 'Unknown'
                rate = row[5] if row[5] is not None else 'N/A'
                sample_size = row[6] or 0
                
                print(f'  {nct} ({phase}): {company}')
                print(f'    Disease: {disease}')
                print(f'    Indication failure rate: {rate}% (based on {sample_size} trials)')
                print(f'    Title: {title}...')
                print()


if __name__ == '__main__':
    calculate_indication_failure_rates()


