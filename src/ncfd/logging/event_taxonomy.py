"""
Canonical event taxonomy for NCFD pipeline.

Defines consistent event names across all pipeline stages
for easy dashboard creation and alerting.
"""

from enum import Enum
from typing import Dict, List, Set, Optional


class EventTaxonomy:
    """
    Canonical event taxonomy covering the whole E2E pipeline.
    
    Use short, consistent event strings so dashboards/alerts are easy.
    """
    
    # Ingestion & parsing events
    CTGOV_FETCH_START = "ctgov.fetch.start"
    CTGOV_FETCH_DONE = "ctgov.fetch.done"
    CTGOV_FETCH_ERROR = "ctgov.fetch.error"
    
    PUBMED_SEARCH_START = "pubmed.search.start"
    PUBMED_SEARCH_DONE = "pubmed.search.done"
    PUBMED_SEARCH_ERROR = "pubmed.search.error"
    
    PUBMED_EFETCH_START = "pubmed.efetch.start"
    PUBMED_EFETCH_DONE = "pubmed.efetch.done"
    PUBMED_EFETCH_ERROR = "pubmed.efetch.error"
    
    PMC_FULLTEXT_FETCH_START = "pmc.fulltext.fetch.start"
    PMC_FULLTEXT_FETCH_DONE = "pmc.fulltext.fetch.done"
    PMC_FULLTEXT_FETCH_MISS = "pmc.fulltext.fetch.miss"
    PMC_FULLTEXT_FETCH_ERROR = "pmc.fulltext.fetch.error"
    
    UNPAYWALL_LOOKUP_DONE = "unpaywall.lookup.done"
    UNPAYWALL_LOOKUP_MISS = "unpaywall.lookup.miss"
    
    DOCUMENT_PARSE_DONE = "document.parse.done"
    DOCUMENT_PARSE_ERROR = "document.parse.error"
    
    # Normalization & mapping events
    MAPPING_TRIAL_TO_TICKER_DONE = "mapping.trial_to_ticker.done"
    MAPPING_TRIAL_TO_TICKER_ERROR = "mapping.trial_to_ticker.error"
    
    ENTITY_RESOLVE_DONE = "entity.resolve.done"
    ENTITY_RESOLVE_ERROR = "entity.resolve.error"
    
    # R/S extraction & Study Cards events
    NLP_EXTRACT_ENTITIES_DONE = "nlp.extract.entities.done"
    NLP_EXTRACT_ENTITIES_ERROR = "nlp.extract.entities.error"
    
    STUDY_CARD_BUILD_DONE = "study_card.build.done"
    STUDY_CARD_BUILD_PARTIAL = "study_card.build.partial"
    STUDY_CARD_BUILD_ERROR = "study_card.build.error"
    
    EVIDENCE_LINKED_DONE = "evidence.linked.done"
    EVIDENCE_LINKED_ERROR = "evidence.linked.error"
    
    # Signals & Gates events
    SIGNAL_EVALUATE_START = "signal.evaluate.start"
    SIGNAL_EVALUATE_DONE = "signal.evaluate.done"
    SIGNAL_EVALUATE_ERROR = "signal.evaluate.error"
    
    GATE_EVALUATE_DONE = "gate.evaluate.done"
    GATE_EVALUATE_ERROR = "gate.evaluate.error"
    
    # LLM calls events
    LLM_CALL_START = "llm.call.start"
    LLM_CALL_DONE = "llm.call.done"
    LLM_CALL_ERROR = "llm.call.error"
    
    # Scheduler / Orchestrator events
    FLOW_STATE_TRANSITION = "flow.state.transition"
    TASK_RETRY_SCHEDULED = "task.retry.scheduled"
    TASK_SCHEDULED = "task.scheduled"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    
    # Database events
    DB_MIGRATION_APPLY_DONE = "db.migration.apply.done"
    DB_MIGRATION_APPLY_ERROR = "db.migration.apply.error"
    DB_WRITE_BULK_DONE = "db.write.bulk.done"
    DB_WRITE_BULK_ERROR = "db.write.bulk.error"
    DB_QUERY_SLOW = "db.query.slow"
    DB_QUERY_ERROR = "db.query.error"
    
    # IO & cache events
    CACHE_GET_HIT = "cache.get.hit"
    CACHE_GET_MISS = "cache.get.miss"
    CACHE_SET_DONE = "cache.set.done"
    CACHE_SET_ERROR = "cache.set.error"
    
    FS_WRITE_DONE = "fs.write.done"
    FS_WRITE_ERROR = "fs.write.error"
    FS_READ_DONE = "fs.read.done"
    FS_READ_ERROR = "fs.read.error"
    
    # IO tracing events
    IO_TRACE = "io.trace"
    
    # Summary events
    RUN_SUMMARY = "run.summary"
    STAGE_SUMMARY = "stage.summary"
    PIPELINE_SUMMARY = "pipeline.summary"
    
    # Error and monitoring events
    ERROR_RECOVERED = "error.recovered"
    ERROR_CRITICAL = "error.critical"
    MONITORING_ALERT = "monitoring.alert"
    HEALTH_CHECK = "health.check"
    
    # USPTO events
    USPTO_SEARCH_START = "uspto.search.start"
    USPTO_SEARCH_DONE = "uspto.search.done"
    USPTO_SEARCH_ERROR = "uspto.search.error"
    
    USPTO_ASSIGNMENT_FETCH_START = "uspto.assignment.fetch.start"
    USPTO_ASSIGNMENT_FETCH_DONE = "uspto.assignment.fetch.done"
    USPTO_ASSIGNMENT_FETCH_ERROR = "uspto.assignment.fetch.error"
    
    # SEC events
    SEC_FILING_FETCH_START = "sec.filing.fetch.start"
    SEC_FILING_FETCH_DONE = "sec.filing.fetch.done"
    SEC_FILING_FETCH_ERROR = "sec.filing.fetch.error"
    
    SEC_DOCUMENT_PARSE_START = "sec.document.parse.start"
    SEC_DOCUMENT_PARSE_DONE = "sec.document.parse.done"
    SEC_DOCUMENT_PARSE_ERROR = "sec.document.parse.error"
    
    # Asset resolution events
    ASSET_RESOLUTION_START = "asset.resolution.start"
    ASSET_RESOLUTION_DONE = "asset.resolution.done"
    ASSET_RESOLUTION_ERROR = "asset.resolution.error"
    
    # Synthesis events
    SYNTHESIS_START = "synthesis.start"
    SYNTHESIS_DONE = "synthesis.done"
    SYNTHESIS_ERROR = "synthesis.error"
    
    # Quality assurance events
    QA_VALIDATION_START = "qa.validation.start"
    QA_VALIDATION_DONE = "qa.validation.done"
    QA_VALIDATION_ERROR = "qa.validation.error"
    
    @classmethod
    def get_all_events(cls) -> List[str]:
        """Get all defined event names."""
        return [
            attr for attr in dir(cls) 
            if not attr.startswith('_') and isinstance(getattr(cls, attr), str)
        ]
    
    @classmethod
    def get_events_by_category(cls) -> Dict[str, List[str]]:
        """Get events grouped by category."""
        return {
            "ingestion": [
                cls.CTGOV_FETCH_START, cls.CTGOV_FETCH_DONE, cls.CTGOV_FETCH_ERROR,
                cls.PUBMED_SEARCH_START, cls.PUBMED_SEARCH_DONE, cls.PUBMED_SEARCH_ERROR,
                cls.PUBMED_EFETCH_START, cls.PUBMED_EFETCH_DONE, cls.PUBMED_EFETCH_ERROR,
                cls.PMC_FULLTEXT_FETCH_START, cls.PMC_FULLTEXT_FETCH_DONE, 
                cls.PMC_FULLTEXT_FETCH_MISS, cls.PMC_FULLTEXT_FETCH_ERROR,
                cls.UNPAYWALL_LOOKUP_DONE, cls.UNPAYWALL_LOOKUP_MISS,
                cls.DOCUMENT_PARSE_DONE, cls.DOCUMENT_PARSE_ERROR,
            ],
            "mapping": [
                cls.MAPPING_TRIAL_TO_TICKER_DONE, cls.MAPPING_TRIAL_TO_TICKER_ERROR,
                cls.ENTITY_RESOLVE_DONE, cls.ENTITY_RESOLVE_ERROR,
            ],
            "extraction": [
                cls.NLP_EXTRACT_ENTITIES_DONE, cls.NLP_EXTRACT_ENTITIES_ERROR,
                cls.STUDY_CARD_BUILD_DONE, cls.STUDY_CARD_BUILD_PARTIAL, cls.STUDY_CARD_BUILD_ERROR,
                cls.EVIDENCE_LINKED_DONE, cls.EVIDENCE_LINKED_ERROR,
            ],
            "signals_gates": [
                cls.SIGNAL_EVALUATE_START, cls.SIGNAL_EVALUATE_DONE, cls.SIGNAL_EVALUATE_ERROR,
                cls.GATE_EVALUATE_DONE, cls.GATE_EVALUATE_ERROR,
            ],
            "llm": [
                cls.LLM_CALL_START, cls.LLM_CALL_DONE, cls.LLM_CALL_ERROR,
            ],
            "orchestration": [
                cls.FLOW_STATE_TRANSITION, cls.TASK_RETRY_SCHEDULED, cls.TASK_SCHEDULED,
                cls.TASK_STARTED, cls.TASK_COMPLETED, cls.TASK_FAILED,
            ],
            "database": [
                cls.DB_MIGRATION_APPLY_DONE, cls.DB_MIGRATION_APPLY_ERROR,
                cls.DB_WRITE_BULK_DONE, cls.DB_WRITE_BULK_ERROR,
                cls.DB_QUERY_SLOW, cls.DB_QUERY_ERROR,
            ],
            "io_cache": [
                cls.CACHE_GET_HIT, cls.CACHE_GET_MISS, cls.CACHE_SET_DONE, cls.CACHE_SET_ERROR,
                cls.FS_WRITE_DONE, cls.FS_WRITE_ERROR, cls.FS_READ_DONE, cls.FS_READ_ERROR,
                cls.IO_TRACE,
            ],
            "summary": [
                cls.RUN_SUMMARY, cls.STAGE_SUMMARY, cls.PIPELINE_SUMMARY,
            ],
            "monitoring": [
                cls.ERROR_RECOVERED, cls.ERROR_CRITICAL, cls.MONITORING_ALERT, cls.HEALTH_CHECK,
            ],
            "uspto": [
                cls.USPTO_SEARCH_START, cls.USPTO_SEARCH_DONE, cls.USPTO_SEARCH_ERROR,
                cls.USPTO_ASSIGNMENT_FETCH_START, cls.USPTO_ASSIGNMENT_FETCH_DONE, cls.USPTO_ASSIGNMENT_FETCH_ERROR,
            ],
            "sec": [
                cls.SEC_FILING_FETCH_START, cls.SEC_FILING_FETCH_DONE, cls.SEC_FILING_FETCH_ERROR,
                cls.SEC_DOCUMENT_PARSE_START, cls.SEC_DOCUMENT_PARSE_DONE, cls.SEC_DOCUMENT_PARSE_ERROR,
            ],
            "asset_resolution": [
                cls.ASSET_RESOLUTION_START, cls.ASSET_RESOLUTION_DONE, cls.ASSET_RESOLUTION_ERROR,
            ],
            "synthesis": [
                cls.SYNTHESIS_START, cls.SYNTHESIS_DONE, cls.SYNTHESIS_ERROR,
            ],
            "qa": [
                cls.QA_VALIDATION_START, cls.QA_VALIDATION_DONE, cls.QA_VALIDATION_ERROR,
            ],
        }
    
    @classmethod
    def validate_event(cls, event: str) -> bool:
        """Validate that an event name is canonical."""
        all_events = cls.get_all_events()
        return event in [getattr(cls, attr) for attr in all_events]
    
    @classmethod
    def get_event_category(cls, event: str) -> Optional[str]:
        """Get the category for a given event."""
        categories = cls.get_events_by_category()
        for category, events in categories.items():
            if event in events:
                return category
        return None
