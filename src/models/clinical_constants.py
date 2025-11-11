"""Clinical trial status constants."""

class TrialStatus:
    """Standard clinical trial status values."""
    
    # Individual statuses
    ACTIVE = 'ACTIVE'
    RECRUITING = 'RECRUITING'
    ENROLLING_BY_INVITATION = 'ENROLLING_BY_INVITATION'
    TERMINATED = 'TERMINATED'
    WITHDRAWN = 'WITHDRAWN'
    SUSPENDED = 'SUSPENDED'
    COMPLETED = 'COMPLETED'
    
    # Status groups for common queries
    ACTIVE_STATUSES = [ACTIVE, RECRUITING, ENROLLING_BY_INVITATION]
    FAILED_STATUSES = [TERMINATED, WITHDRAWN, SUSPENDED]

