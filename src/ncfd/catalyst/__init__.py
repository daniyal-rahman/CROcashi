"""Phase 10 Catalyst System for trial failure prediction and ranking."""

from .models import (
    StudyCardRanking,
    LLMResolutionScore,
    CatalystWindow,
    StudyHint,
    SlipStats,
    RankedTrial
)

from .quality import (
    StudyCardQuality,
    StudyCardQualityAnalyzer,
    FieldScore,
    FieldCategory,
    QualityMetric
)

from .service import StudyCardQualityService

from .extractor import (
    StudyCardFieldExtractor,
    ExtractedField,
    FieldExtractionResult,
    ExtractionStatus,
    FieldType,
    EvidenceSpanExtractor,
    ToneAnalyzer
)

from .validation import (
    StudyCardFieldValidator,
    FieldValidationResult,
    ValidationIssue,
    ValidationLevel,
    ValidationRule
)

from .evaluator import (
    AutomaticStudyCardEvaluator,
    AutomaticEvaluation,
    RiskAssessment,
    RiskFactor
)

from .enhanced_service import EnhancedStudyCardService

# Enhanced study card analysis components (Phase 2)
from .enhanced_extractor import (
    EnhancedStudyCardExtractor, ToneAnalysisResult, ConflictsFundingResult,
    PublicationDetailsResult, DataLocationResult, ToneCategory, ClaimStrength,
    ConflictType, FundingType, JournalType, FigureType
)
from .reviewer_analyzer import (
    ReviewerNotesAnalyzer, ReviewerNotesResult, Limitation, Oddity,
    GeographicOutlier, Discrepancy, QualityAssessment, LimitationType,
    LimitationSeverity, OddityType, GeographicImpact, DiscrepancyType,
    OverallQuality, EvidenceStrength
)
from .comprehensive_service import ComprehensiveStudyCardService, ComprehensiveAnalysisResult

# LLM Integration components (Phase 3)
from .llm_resolution import (
    LLMResolutionService, StudyCardForResolution, LLMResolutionRequest,
    LLMResolutionResult, BatchResolutionResult, resolve_study_card_rankings_sync
)
from .automated_evaluation import (
    AutomatedEvaluationSystem, AutomatedEvaluationRequest,
    AutomatedEvaluationResult, BatchEvaluationResult,
    evaluate_study_cards_automated_sync
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
    'StudyCardQuality',
    'StudyCardQualityAnalyzer',
    'FieldScore',
    'FieldCategory',
    'QualityMetric',
    'StudyCardQualityService',
    'StudyCardFieldExtractor',
    'ExtractedField',
    'FieldExtractionResult',
    'ExtractionStatus',
    'FieldType',
    'EvidenceSpanExtractor',
    'ToneAnalyzer',
    'StudyCardFieldValidator',
    'FieldValidationResult',
    'ValidationIssue',
    'ValidationLevel',
    'ValidationRule',
    'AutomaticStudyCardEvaluator',
    'AutomaticEvaluation',
    'RiskAssessment',
    'RiskFactor',
    'EnhancedStudyCardService',
    # Enhanced study card analysis components (Phase 2)
    'EnhancedStudyCardExtractor', 'ToneAnalysisResult', 'ConflictsFundingResult',
    'PublicationDetailsResult', 'DataLocationResult', 'ToneCategory', 'ClaimStrength',
    'ConflictType', 'FundingType', 'JournalType', 'FigureType',
    'ReviewerNotesAnalyzer', 'ReviewerNotesResult', 'Limitation', 'Oddity',
    'GeographicOutlier', 'Discrepancy', 'QualityAssessment', 'LimitationType',
    'LimitationSeverity', 'OddityType', 'GeographicImpact', 'DiscrepancyType',
    'OverallQuality', 'EvidenceStrength',
    'ComprehensiveStudyCardService', 'ComprehensiveAnalysisResult',
    # LLM Integration components (Phase 3)
    'LLMResolutionService', 'StudyCardForResolution', 'LLMResolutionRequest',
    'LLMResolutionResult', 'BatchResolutionResult', 'resolve_study_card_rankings_sync',
    'AutomatedEvaluationSystem', 'AutomatedEvaluationRequest',
    'AutomatedEvaluationResult', 'BatchEvaluationResult',
    'evaluate_study_cards_automated_sync',
    'infer_catalyst_window',
    'sort_ranked_trials',
    'BacktestFramework',
    'get_session'
]
