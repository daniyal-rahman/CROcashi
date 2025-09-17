"""
Clean Pattern Families Data Models

Elegant, simple models for the F1-F9 Pattern Families system.
No legacy code, no complexity - just clean, focused models.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class SeverityLevel(Enum):
    """Severity levels for pattern detection."""
    GREY = 0    # Not present/insufficient evidence
    YELLOW = 1  # Adds meaningful risk but unlikely decisive
    RED = 2     # Likely to materially invalidate result

@dataclass
class PatternDetection:
    """Pattern detection result from LLM."""
    family_id: str
    pattern_id: str
    severity: SeverityLevel
    confidence: float
    rationale: str
    evidence_spans: List[Dict[str, Any]]

@dataclass
class PatternScore:
    """Final blended score for a trial."""
    trial_id: str
    p_fail_llm: float
    score_0_100: int
    uncertainty: float
    family_contributions: Dict[str, float]
    over_index: float
    top_patterns: List[Dict[str, Any]]

# SQLAlchemy Models

class PatternFamily(Base):
    """Pattern Families configuration (F1-F9)."""
    __tablename__ = 'pattern_families'
    
    family_id = Column(String(2), primary_key=True)
    name = Column(Text, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default='now()')
    
    # Relationships
    detections = relationship("PatternDetection", back_populates="family")

class PatternDetection(Base):
    """Pattern detection results from LLM."""
    __tablename__ = 'pattern_detections'
    
    detection_id = Column(Integer, primary_key=True, autoincrement=True)
    trial_id = Column(Integer, ForeignKey('trials.trial_id', ondelete='CASCADE'), nullable=False)
    run_id = Column(String(50), nullable=False)
    family_id = Column(String(2), ForeignKey('pattern_families.family_id', ondelete='CASCADE'), nullable=False)
    pattern_id = Column(String(4), nullable=False)  # F1P1, F1P2, etc.
    severity = Column(Integer, nullable=False)  # 0-3 scale
    confidence = Column(Numeric(3, 2), nullable=False)  # 0-1 scale
    rationale = Column(Text)
    evidence_spans = Column(JSONB)  # Array of {doc_id, snippet_hash, char_start, char_end}
    detected_at = Column(DateTime(timezone=True), server_default='now()')
    created_at = Column(DateTime(timezone=True), server_default='now()')
    
    # Relationships
    family = relationship("PatternFamily", back_populates="detections")
    trial = relationship("Trial", back_populates="pattern_detections")
    
    # Constraints
    __table_args__ = (
        CheckConstraint('severity >= 0 AND severity <= 2', name='ck_severity_range'),
        CheckConstraint('confidence >= 0 AND confidence <= 1', name='ck_confidence_range'),
        Index('idx_pattern_detections_trial', 'trial_id'),
        Index('idx_pattern_detections_family', 'family_id'),
        Index('idx_pattern_detections_run', 'run_id'),
        Index('idx_pattern_detections_severity', 'severity'),
    )

class PatternScore(Base):
    """Final blended score for a trial."""
    __tablename__ = 'pattern_scores'
    
    score_id = Column(Integer, primary_key=True, autoincrement=True)
    trial_id = Column(Integer, ForeignKey('trials.trial_id', ondelete='CASCADE'), nullable=False)
    run_id = Column(String(50), nullable=False)
    
    # LLM scoring
    p_fail_llm = Column(Numeric(5, 4))  # LLM probability 0-1
    score_0_100 = Column(Integer, nullable=False)  # Final blended score 0-100
    uncertainty = Column(Numeric(3, 2))  # LLM uncertainty 0-1
    
    # Family contributions
    family_contributions = Column(JSONB)  # {F1: weight, F2: weight, ...}
    over_index = Column(Numeric(6, 3))  # Over-index vs peers
    
    # Top contributing patterns
    top_patterns = Column(JSONB)  # Array of {pattern_id, severity, confidence}
    
    # Version tracking
    model_version = Column(String(50))
    prompt_hash = Column(String(64))
    
    created_at = Column(DateTime(timezone=True), server_default='now()')
    
    # Relationships
    trial = relationship("Trial", back_populates="pattern_scores")
    
    # Constraints
    __table_args__ = (
        CheckConstraint('p_fail_llm IS NULL OR (p_fail_llm >= 0 AND p_fail_llm <= 1)', name='ck_p_fail_llm_range'),
        CheckConstraint('score_0_100 >= 0 AND score_0_100 <= 100', name='ck_score_0_100_range'),
        CheckConstraint('uncertainty IS NULL OR (uncertainty >= 0 AND uncertainty <= 1)', name='ck_uncertainty_range'),
        Index('idx_pattern_scores_trial', 'trial_id'),
        Index('idx_pattern_scores_run', 'run_id'),
        Index('idx_pattern_scores_score', 'score_0_100'),
        Index('idx_pattern_scores_created', 'created_at'),
    )

# Update Trial model to include new relationships
class Trial(Base):
    """Trial model with Pattern Families relationships."""
    __tablename__ = 'trials'
    
    trial_id = Column(Integer, primary_key=True)
    # ... existing fields ...
    
    # New relationships
    pattern_detections = relationship("PatternDetection", back_populates="trial", cascade="all, delete-orphan")
    pattern_scores = relationship("PatternScore", back_populates="trial", cascade="all, delete-orphan")
