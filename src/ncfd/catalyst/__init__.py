"""Phase 10 Catalyst System for trial failure prediction and ranking."""

from .models import (
    StudyCardRanking,
    LLMResolutionScore,
    CatalystWindow,
    StudyHint,
    SlipStats,
    RankedTrial
)

# LLM Integration components (Phase 3)
from .llm_resolution import (
    LLMResolutionService, StudyCardForResolution, LLMResolutionRequest,
    LLMResolutionResult, BatchResolutionResult, resolve_study_card_rankings_sync
)

from .infer import infer_catalyst_window
from .rank import sort_ranked_trials
from .backtest import BacktestFramework

# Database utilities
from ..db.session import get_session

__all__ = [
    'StudyCardRanking',
    'LLMResolutionScore', 
    'CatalystWindow',
    'StudyHint',
    'SlipStats',
    'RankedTrial',
    # LLM Integration components (Phase 3)
    'LLMResolutionService', 'StudyCardForResolution', 'LLMResolutionRequest',
    'LLMResolutionResult', 'BatchResolutionResult', 'resolve_study_card_rankings_sync',
    'infer_catalyst_window',
    'sort_ranked_trials',
    'BacktestFramework',
    'get_session'
]
