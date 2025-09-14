"""
Examples of using the new structured logging system.

This module demonstrates how to use the comprehensive logging system
for different types of operations in the NCFD pipeline.
"""

from __future__ import annotations

import time
from typing import Dict, Any, List
from .structured_logger import get_logger
from .context import LogContext, set_context
from .event_taxonomy import EventTaxonomy
from .io_trace import llm_trace, parse_trace, validate_trace, api_trace


# Example 1: Basic structured logging
def example_basic_logging():
    """Example of basic structured logging."""
    logger = get_logger("ncfd.examples")
    
    # Simple info log
    logger.info(
        EventTaxonomy.CTGOV_FETCH_START,
        "Starting CT.gov fetch",
        nct_id="NCT05515666",
        query="cassava therapeutics"
    )
    
    # Performance logging
    start_time = time.time()
    # ... do work ...
    duration_ms = int((time.time() - start_time) * 1000)
    
    logger.log_performance(
        EventTaxonomy.CTGOV_FETCH_DONE,
        duration_ms=duration_ms,
        processed_n=150,
        success_n=148,
        fail_n=2,
        nct_id="NCT05515666"
    )


# Example 2: LLM call logging
def example_llm_logging():
    """Example of LLM call logging with cost tracking."""
    logger = get_logger("ncfd.examples.llm")
    
    # Log LLM call
    logger.log_llm_call(
        EventTaxonomy.LLM_CALL_DONE,
        model="gpt-4",
        input_tokens=1250,
        output_tokens=320,
        usd_cost=0.024,
        duration_ms=2100,
        prompt_id="study_card_generation_v2",
        prompt_hash="abc123def456",
        temperature=0.7,
        truncated=False,
        nct_id="NCT05515666",
        study_card_id="sc_789"
    )


# Example 3: Decision transparency logging
def example_decision_logging():
    """Example of decision transparency logging."""
    logger = get_logger("ncfd.examples.gates")
    
    # Log gate evaluation with full transparency
    logger.log_decision(
        EventTaxonomy.GATE_EVALUATE_DONE,
        decision="fail",
        confidence=0.86,
        why="Dropout>20% and ≥4 amendments in pivotal phase.",
        features={
            "arm_dropout_pct": 27.3,
            "amendments_n": 5,
            "sites_n": 85,
            "countries_n": 12
        },
        thresholds={
            "arm_dropout_pct": 20,
            "amendments_n": 4,
            "sites_n": 50
        },
        evidence_refs=[
            ["doc_812", "PMID:38900123", [14235, 14512]],
            ["doc_901", "NCT PDF", [2210, 2444]]
        ],
        gate_id="G2_protocol_integrity",
        nct_id="NCT05515666",
        rule_id="rule_dropout_amendments_v1",
        rule_version="1.2"
    )


# Example 4: IO tracing decorators
@llm_trace(name="llm.synthesize.study_card", capture_args=("prompt", "settings"))
def synthesize_study_card(prompt: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
    """Example LLM function with IO tracing."""
    # Simulate LLM call
    time.sleep(0.1)
    return {
        "study_card": "Generated study card content",
        "confidence": 0.85,
        "tokens_used": 450
    }


@parse_trace(name="pubmed.parse_xml", capture_args=("xml_text",))
def parse_pubmed_xml(xml_text: str) -> Dict[str, Any]:
    """Example parsing function with IO tracing."""
    # Simulate parsing
    time.sleep(0.05)
    return {
        "title": "Sample Title",
        "abstract": "Sample abstract text",
        "authors": ["Author 1", "Author 2"],
        "pmid": "12345678"
    }


@validate_trace(name="study_card.validate", capture_args=("card",))
def validate_study_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Example validation function with IO tracing."""
    # Simulate validation
    time.sleep(0.02)
    return {
        "schema_ok": True,
        "errors": [],
        "warnings": ["Missing secondary endpoint"]
    }


# Example 5: Context management
def example_context_management():
    """Example of using context management."""
    # Set up execution context
    with set_context(
        run_id="r_abc123",
        flow_id="cassava_analysis",
        task_id="task_001",
        attempt=0,
        env="prod"
    ) as ctx:
        logger = get_logger("ncfd.examples.context")
        
        # All logs will automatically include context
        logger.info(
            EventTaxonomy.TASK_STARTED,
            "Starting task execution",
            task_type="pubmed_ingestion"
        )
        
        # Update task context
        ctx.update_task("task_002", attempt=1)
        
        logger.info(
            EventTaxonomy.TASK_RETRY_SCHEDULED,
            "Retrying task after failure",
            err_type="RateLimitError",
            retry_in_s=300
        )


# Example 6: Error logging with context
def example_error_logging():
    """Example of comprehensive error logging."""
    logger = get_logger("ncfd.examples.errors")
    
    try:
        # Simulate an error
        raise ValueError("Invalid trial data format")
    except Exception as e:
        logger.log_error_with_context(
            EventTaxonomy.CTGOV_FETCH_ERROR,
            error=e,
            context={
                "nct_id": "NCT05515666",
                "query_params": {"term": "cassava", "limit": 100},
                "retry_count": 2,
                "last_success": "2024-01-15T10:30:00Z"
            },
            suggested_action="Check trial data format and retry with validation"
        )


# Example 7: Database operation logging
def example_database_logging():
    """Example of database operation logging."""
    logger = get_logger("ncfd.examples.database")
    
    # Log bulk write operation
    logger.info(
        EventTaxonomy.DB_WRITE_BULK_DONE,
        "Bulk write completed",
        table="trials",
        upserts_n=150,
        conflicts_n=3,
        duration_ms=1250
    )
    
    # Log slow query
    logger.warn(
        EventTaxonomy.DB_QUERY_SLOW,
        "Slow query detected",
        sql_id="trial_search_complex",
        duration_ms=5000,
        rows=10000,
        suggested_action="Consider adding index on sponsor_id"
    )


# Example 8: Cache operation logging
def example_cache_logging():
    """Example of cache operation logging."""
    logger = get_logger("ncfd.examples.cache")
    
    # Log cache hit
    logger.info(
        EventTaxonomy.CACHE_GET_HIT,
        "Cache hit for trial data",
        cache_key="trial_NCT05515666",
        ttl_s=3600,
        nct_id="NCT05515666"
    )
    
    # Log cache miss
    logger.info(
        EventTaxonomy.CACHE_GET_MISS,
        "Cache miss for trial data",
        cache_key="trial_NCT05515667",
        nct_id="NCT05515667"
    )


# Example 9: Pipeline summary logging
def example_pipeline_summary():
    """Example of pipeline summary logging."""
    logger = get_logger("ncfd.examples.pipeline")
    
    # Log run summary
    logger.info(
        EventTaxonomy.RUN_SUMMARY,
        "Pipeline run completed",
        wall_ms=45000,
        stages={
            "ctgov_ingestion": {"duration_ms": 15000, "success_n": 148, "fail_n": 2},
            "pubmed_ingestion": {"duration_ms": 20000, "success_n": 95, "fail_n": 5},
            "study_card_generation": {"duration_ms": 10000, "success_n": 143, "fail_n": 0}
        },
        totals={
            "total_trials": 150,
            "total_documents": 243,
            "total_study_cards": 143,
            "total_cost_usd": 12.50
        },
        failures_topk=[
            {"event": "pubmed.efetch.error", "n": 3, "sample_ids": ["PMID:123", "PMID:456"]},
            {"event": "ctgov.fetch.error", "n": 2, "sample_ids": ["NCT05515666", "NCT05515667"]}
        ]
    )


# Example 10: Complete workflow
def example_complete_workflow():
    """Example of a complete workflow with all logging types."""
    logger = get_logger("ncfd.examples.workflow")
    
    # Set up context
    with set_context(
        run_id="r_workflow_001",
        flow_id="cassava_comprehensive_analysis",
        env="prod"
    ) as ctx:
        
        # Start workflow
        logger.info(
            EventTaxonomy.FLOW_STATE_TRANSITION,
            "Workflow started",
            from_state="initialized",
            to_state="running",
            reason="user_initiated"
        )
        
        # Process trial
        nct_id = "NCT05515666"
        
        # Fetch from CT.gov
        logger.info(
            EventTaxonomy.CTGOV_FETCH_START,
            "Fetching trial from CT.gov",
            nct_id=nct_id
        )
        
        # Simulate work
        time.sleep(0.1)
        
        logger.info(
            EventTaxonomy.CTGOV_FETCH_DONE,
            "CT.gov fetch completed",
            nct_id=nct_id,
            processed_n=1,
            success_n=1,
            fail_n=0,
            duration_ms=100
        )
        
        # Generate study card
        study_card = synthesize_study_card(
            prompt={"trial_data": "sample data"},
            settings={"model": "gpt-4", "temperature": 0.7}
        )
        
        # Validate study card
        validation_result = validate_study_card(study_card)
        
        # Log decision
        logger.log_decision(
            EventTaxonomy.GATE_EVALUATE_DONE,
            decision="pass",
            confidence=0.92,
            why="Trial meets all feasibility criteria",
            features={
                "sample_size": 200,
                "duration_months": 24,
                "sites_n": 15
            },
            thresholds={
                "sample_size": 100,
                "duration_months": 12,
                "sites_n": 5
            },
            gate_id="G1_feasibility",
            nct_id=nct_id,
            study_card_id="sc_001"
        )
        
        # Complete workflow
        logger.info(
            EventTaxonomy.FLOW_STATE_TRANSITION,
            "Workflow completed",
            from_state="running",
            to_state="completed",
            reason="successful_execution",
            nct_id=nct_id
        )


if __name__ == "__main__":
    """Run all examples."""
    print("Running structured logging examples...")
    
    example_basic_logging()
    example_llm_logging()
    example_decision_logging()
    example_context_management()
    example_error_logging()
    example_database_logging()
    example_cache_logging()
    example_pipeline_summary()
    example_complete_workflow()
    
    print("All examples completed!")
