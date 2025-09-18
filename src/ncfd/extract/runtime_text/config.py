"""
Runtime Text Generation Configuration
"""

RUNTIME_TEXT_CONFIG = {
    "cache": {
        "memory_limit_mb": 500,
        "max_documents": 1000,
        "ttl_hours": 24,
        "cleanup_interval_minutes": 60
    },
    "apis": {
        "pubmed": {
            "rate_limit_per_minute": 60,
            "timeout_seconds": 30,
            "max_retries": 3,
            "backoff_base": 2.0
        },
        "pmc": {
            "rate_limit_per_minute": 30,
            "timeout_seconds": 45,
            "max_retries": 2,
            "backoff_base": 2.0
        },
        "unpaywall": {
            "rate_limit_per_minute": 100,
            "timeout_seconds": 20,
            "max_retries": 2,
            "backoff_base": 1.5
        }
    },
    "quality": {
        "min_fulltext_length": 500,
        "min_abstract_length": 100,
        "prefer_fulltext": True,
        "quality_threshold": 0.8
    },
    "fallback_order": ["pmc", "pubmed", "unpaywall"],
    "enable_caching": True,
    "enable_runtime_generation": True
}
