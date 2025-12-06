"""Cache TTL configuration with documented rationale."""

class CacheTTL:
    # Fast-changing data - updated frequently
    METRICS = 1800  # 30 minutes - company metrics change as trials update
    TIMELINE = 900  # 15 minutes - event timeline frequently updated
    
    # More stable data - changes less frequently
    RISK_SCORE = 3600  # 1 hour - risk scores are computed aggregates

