#!/usr/bin/env python3
"""
Debug script to trace the cost calculation flow and identify where the issue is.
This will help us understand why execution_cost is returning 0.0 instead of 0.1
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from ncfd.db.session import get_session
from ncfd.pipeline.literature_orchestrator import create_literature_orchestrator
from sqlalchemy import text

def debug_cost_calculation():
    """Debug the cost calculation flow step by step."""
    print("🔍 DEBUGGING COST CALCULATION FLOW")
    print("=" * 50)
    
    with get_session() as db_session:
        # Step 1: Check what's in the database
        print("\n1. 📊 DATABASE STATE:")
        try:
            # Check cost_records
            result = db_session.execute(text(
                "SELECT run_id, operation_type, cost_amount FROM cost_records WHERE run_id LIKE 'lit_pipeline_%' ORDER BY recorded_at DESC LIMIT 3"
            ))
            cost_records = result.fetchall()
            print(f"   Cost records found: {len(cost_records)}")
            for record in cost_records:
                print(f"     {record[0]}: {record[1]} = ${record[2]:.4f}")
            
            # Check pipeline executions
            result = db_session.execute(text(
                "SELECT execution_id, run_id, total_cost FROM literature_pipeline_executions ORDER BY start_time DESC LIMIT 3"
            ))
            executions = result.fetchall()
            print(f"   Pipeline executions found: {len(executions)}")
            for record in executions:
                print(f"     {record[0]}: {record[1]} = ${record[2]:.4f}")
                
        except Exception as e:
            print(f"   ERROR querying database: {e}")
            return
        
        # Step 2: Create orchestrator and check execution_id
        print("\n2. 🏗️  ORCHESTRATOR CREATION:")
        try:
            orchestrator = create_literature_orchestrator(db_session)
            print(f"   Orchestrator execution_id: {orchestrator.execution_id}")
            print(f"   Orchestrator run_id: {orchestrator.run_id}")
            
            # Check if budget monitor has the method
            print(f"   Budget monitor has get_execution_cost: {hasattr(orchestrator.budget_monitor, 'get_execution_cost')}")
            
        except Exception as e:
            print(f"   ERROR creating orchestrator: {e}")
            return
        
        # Step 3: Test get_execution_cost directly
        print("\n3. 🧪 TESTING get_execution_cost DIRECTLY:")
        try:
            # Test with the latest execution_id from database
            latest_execution_id = executions[0][0] if executions else None
            if latest_execution_id:
                print(f"   Testing with execution_id: {latest_execution_id}")
                
                # Test the method directly
                execution_cost = orchestrator.budget_monitor.get_execution_cost(latest_execution_id)
                print(f"   get_execution_cost result: ${execution_cost:.4f}")
                
                # Test the database query manually
                result = db_session.execute(text(
                    "SELECT COALESCE(SUM(cost_amount), 0) FROM cost_records WHERE run_id = :execution_id"
                ), {'execution_id': latest_execution_id})
                db_cost = float(result.scalar() or 0.0)
                print(f"   Manual DB query result: ${db_cost:.4f}")
                
                # Check if they match
                if abs(execution_cost - db_cost) < 0.0001:
                    print("   ✅ get_execution_cost matches database query")
                else:
                    print(f"   ❌ MISMATCH! get_execution_cost: ${execution_cost:.4f}, DB: ${db_cost:.4f}")
                    
            else:
                print("   No execution_id found in database")
                
        except Exception as e:
            print(f"   ERROR testing get_execution_cost: {e}")
            import traceback
            traceback.print_exc()
        
        # Step 4: Check budget monitor state
        print("\n4. 💰 BUDGET MONITOR STATE:")
        try:
            budget_summary = orchestrator.budget_monitor.get_budget_summary()
            print(f"   Budget summary total_cost: ${budget_summary.total_cost:.4f}")
            print(f"   Budget summary period: {budget_summary.period}")
            
            # Check in-memory cost records
            in_memory_costs = orchestrator.budget_monitor.cost_records
            print(f"   In-memory cost records: {len(in_memory_costs)}")
            for record in in_memory_costs[:3]:  # Show first 3
                print(f"     {record.operation_type}: ${record.cost:.4f} (exec_id: {record.execution_id})")
                
        except Exception as e:
            print(f"   ERROR checking budget monitor: {e}")
            import traceback
            traceback.print_exc()
        
        # Step 5: Check if there's a circular import issue
        print("\n5. 🔗 IMPORT CHECK:")
        try:
            from ncfd.db.models import CostRecord
            print(f"   CostRecord imported successfully: {CostRecord}")
            
            # Check if it's the same as DBCostRecord in budget monitor
            from ncfd.ingest.budget_monitor import DBCostRecord
            print(f"   DBCostRecord in budget monitor: {DBCostRecord}")
            
        except Exception as e:
            print(f"   ERROR checking imports: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    try:
        debug_cost_calculation()
    except Exception as e:
        print(f"\n💥 DEBUG SCRIPT ERROR: {e}")
        import traceback
        traceback.print_exc()
