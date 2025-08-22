"""Service layer for integrating study card quality analysis with database operations."""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json
import logging

from sqlalchemy.orm import Session
from sqlalchemy import text

from .quality import StudyCardQualityAnalyzer, StudyCardQuality
from .models import StudyCardRanking
from ..db.session import get_session

logger = logging.getLogger(__name__)


class StudyCardQualityService:
    """Service for managing study card quality analysis and database operations."""
    
    def __init__(self, db_session: Optional[Session] = None):
        """Initialize the service with database session."""
        self.analyzer = StudyCardQualityAnalyzer()
        self.db_session = db_session
    
    def analyze_study_card_quality(self, study_id: int, trial_id: int, extracted_jsonb: Dict[str, Any]) -> StudyCardQuality:
        """Analyze quality for a single study card."""
        try:
            quality = self.analyzer.analyze_study_card(study_id, trial_id, extracted_jsonb)
            logger.info(f"Quality analysis completed for study {study_id}, trial {trial_id}: rank {quality.quality_rank}")
            return quality
        except Exception as e:
            logger.error(f"Error analyzing quality for study {study_id}, trial {trial_id}: {e}")
            # Return empty quality on error
            return self.analyzer._create_empty_quality(study_id, trial_id)
    
    def bulk_analyze_study_cards(self, limit: Optional[int] = None) -> List[StudyCardQuality]:
        """Analyze quality for all study cards in the database."""
        session = self.db_session or next(get_session())
        try:
            # Query studies with extracted data
            query = """
                SELECT s.study_id, s.trial_id, s.extracted_jsonb, s.coverage_level
                FROM studies s
                WHERE s.extracted_jsonb IS NOT NULL
                AND s.extracted_jsonb != '{}'
                ORDER BY s.study_id
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            result = session.execute(text(query))
            studies = result.fetchall()
            
            logger.info(f"Analyzing quality for {len(studies)} study cards")
            
            qualities = []
            for study in studies:
                study_id = study.study_id
                trial_id = study.trial_id
                extracted_jsonb = study.extracted_jsonb
                
                # Convert extracted_jsonb to dict if it's a string
                if isinstance(extracted_jsonb, str):
                    try:
                        extracted_jsonb = json.loads(extracted_jsonb)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON for study {study_id}, skipping")
                        continue
                
                quality = self.analyze_study_card_quality(study_id, trial_id, extracted_jsonb)
                qualities.append(quality)
            
            logger.info(f"Quality analysis completed for {len(qualities)} study cards")
            return qualities
            
        except Exception as e:
            logger.error(f"Error in bulk quality analysis: {e}")
            return []
        finally:
            if not self.db_session:
                session.close()
    
    def save_quality_rankings(self, qualities: List[StudyCardQuality], evaluator_id: str = "auto_quality") -> int:
        """Save quality rankings to the database."""
        session = self.db_session or next(get_session())
        try:
            saved_count = 0
            
            for quality in qualities:
                # Check if ranking already exists
                existing = session.execute(
                    text("""
                        SELECT ranking_id FROM study_card_rankings 
                        WHERE trial_id = :trial_id AND evaluator_id = :evaluator_id
                    """),
                    {"trial_id": quality.trial_id, "evaluator_id": evaluator_id}
                ).fetchone()
                
                if existing:
                    # Update existing ranking
                    session.execute(
                        text("""
                            UPDATE study_card_rankings 
                            SET score_1_10 = :score, confidence_level = :confidence,
                                reasoning_text = :reasoning, updated_at = NOW()
                            WHERE trial_id = :trial_id AND evaluator_id = :evaluator_id
                        """),
                        {
                            "score": quality.quality_rank,
                            "confidence": int(quality.confidence * 5),  # Convert 0-1 to 1-5 scale
                            "reasoning": "\n".join(quality.quality_notes),
                            "trial_id": quality.trial_id,
                            "evaluator_id": evaluator_id
                        }
                    )
                else:
                    # Insert new ranking
                    session.execute(
                        text("""
                            INSERT INTO study_card_rankings 
                            (trial_id, evaluator_id, score_1_10, confidence_level, reasoning_text, created_at, updated_at)
                            VALUES (:trial_id, :evaluator_id, :score, :confidence, :reasoning, NOW(), NOW())
                        """),
                        {
                            "trial_id": quality.trial_id,
                            "evaluator_id": evaluator_id,
                            "score": quality.quality_rank,
                            "confidence": int(quality.confidence * 5),  # Convert 0-1 to 1-5 scale
                            "reasoning": "\n".join(quality.quality_notes)
                        }
                    )
                
                saved_count += 1
            
            session.commit()
            logger.info(f"Saved {saved_count} quality rankings to database")
            return saved_count
            
        except Exception as e:
            logger.error(f"Error saving quality rankings: {e}")
            session.rollback()
            return 0
        finally:
            if not self.db_session:
                session.close()
    
    def get_quality_summary(self) -> Dict[str, Any]:
        """Get summary statistics for study card quality."""
        session = self.db_session or next(get_session())
        try:
            # Get quality distribution
            result = session.execute(text("""
                SELECT 
                    score_1_10,
                    COUNT(*) as count,
                    AVG(confidence_level) as avg_confidence
                FROM study_card_rankings 
                WHERE evaluator_id = 'auto_quality'
                GROUP BY score_1_10
                ORDER BY score_1_10
            """))
            
            quality_distribution = {}
            total_studies = 0
            total_confidence = 0
            
            for row in result:
                score = row.score_1_10
                count = row.count
                avg_confidence = row.avg_confidence
                
                quality_distribution[score] = {
                    "count": count,
                    "avg_confidence": float(avg_confidence) if avg_confidence else 0.0
                }
                total_studies += count
                total_confidence += count * avg_confidence if avg_confidence else 0
            
            # Calculate overall statistics
            overall_stats = {
                "total_studies": total_studies,
                "avg_quality_score": sum(score * data["count"] for score, data in quality_distribution.items()) / total_studies if total_studies > 0 else 0,
                "avg_confidence": total_confidence / total_studies if total_studies > 0 else 0,
                "quality_distribution": quality_distribution
            }
            
            return overall_stats
            
        except Exception as e:
            logger.error(f"Error getting quality summary: {e}")
            return {}
        finally:
            if not self.db_session:
                session.close()
    
    def get_study_quality_details(self, trial_id: int) -> Optional[StudyCardQuality]:
        """Get detailed quality information for a specific trial."""
        session = self.db_session or next(get_session())
        try:
            # Get study card data
            result = session.execute(text("""
                SELECT s.study_id, s.trial_id, s.extracted_jsonb
                FROM studies s
                WHERE s.trial_id = :trial_id
            """), {"trial_id": trial_id})
            
            study = result.fetchone()
            if not study:
                return None
            
            # Get existing ranking
            ranking_result = session.execute(text("""
                SELECT score_1_10, confidence_level, reasoning_text
                FROM study_card_rankings 
                WHERE trial_id = :trial_id AND evaluator_id = 'auto_quality'
            """), {"trial_id": trial_id})
            
            ranking = ranking_result.fetchone()
            
            # Analyze quality
            extracted_jsonb = study.extracted_jsonb
            if isinstance(extracted_jsonb, str):
                try:
                    extracted_jsonb = json.loads(extracted_jsonb)
                except json.JSONDecodeError:
                    extracted_jsonb = {}
            
            quality = self.analyze_study_card_quality(study.study_id, study.trial_id, extracted_jsonb)
            
            # If ranking exists, update quality with database values
            if ranking:
                quality.quality_rank = ranking.score_1_10
                quality.confidence = ranking.confidence_level / 5.0  # Convert 1-5 to 0-1
                if ranking.reasoning_text:
                    quality.quality_notes = ranking.reasoning_text.split('\n')
            
            return quality
            
        except Exception as e:
            logger.error(f"Error getting study quality details for trial {trial_id}: {e}")
            return None
        finally:
            if not self.db_session:
                session.close()
    
    def update_study_card_quality(self, trial_id: int) -> Optional[StudyCardQuality]:
        """Update quality analysis for a specific trial."""
        quality = self.get_study_quality_details(trial_id)
        if quality:
            # Save updated quality
            self.save_quality_rankings([quality])
            return quality
        return None
    
    def get_low_quality_studies(self, threshold: int = 5, limit: int = 100) -> List[StudyCardQuality]:
        """Get studies with quality scores below threshold."""
        session = self.db_session or next(get_session())
        try:
            result = session.execute(text("""
                SELECT s.study_id, s.trial_id, s.extracted_jsonb
                FROM studies s
                JOIN study_card_rankings scr ON s.trial_id = scr.trial_id
                WHERE scr.evaluator_id = 'auto_quality'
                AND scr.score_1_10 <= :threshold
                ORDER BY scr.score_1_10 ASC, scr.confidence_level ASC
                LIMIT :limit
            """), {"threshold": threshold, "limit": limit})
            
            studies = result.fetchall()
            qualities = []
            
            for study in studies:
                extracted_jsonb = study.extracted_jsonb
                if isinstance(extracted_jsonb, str):
                    try:
                        extracted_jsonb = json.loads(extracted_jsonb)
                    except json.JSONDecodeError:
                        extracted_jsonb = {}
                
                quality = self.analyze_study_card_quality(study.study_id, study.trial_id, extracted_jsonb)
                qualities.append(quality)
            
            return qualities
            
        except Exception as e:
            logger.error(f"Error getting low quality studies: {e}")
            return []
        finally:
            if not self.db_session:
                session.close()
