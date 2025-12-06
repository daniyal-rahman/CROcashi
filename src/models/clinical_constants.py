"""Clinical trial status constants."""

class TrialStatus:
    """Standard clinical trial status values (lowercase to match ClinicalTrials.gov data)."""

    # Individual statuses
    ACTIVE = 'active_not_recruiting'
    RECRUITING = 'recruiting'
    ENROLLING_BY_INVITATION = 'enrolling_by_invitation'
    NOT_YET_RECRUITING = 'not_yet_recruiting'
    TERMINATED = 'terminated'
    WITHDRAWN = 'withdrawn'
    SUSPENDED = 'suspended'
    COMPLETED = 'completed'
    UNKNOWN = 'unknown'

    # Status groups for common queries
    ACTIVE_STATUSES = [ACTIVE, RECRUITING, ENROLLING_BY_INVITATION, NOT_YET_RECRUITING]
    FAILED_STATUSES = [TERMINATED, WITHDRAWN, SUSPENDED]

