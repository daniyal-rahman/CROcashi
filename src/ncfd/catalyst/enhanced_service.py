"""Enhanced Study Card Service with Automatic Evaluation for Phase 10 Catalyst System."""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json
import logging

from sqlalchemy.orm import Session
from sqlalchemy import text

from .evaluator import AutomaticStudyCardEvaluator, AutomaticEvaluation, RiskFactor
from .service import StudyCardQualityService
from .quality import StudyCardQuality
from .models import StudyCardRanking
from ..db.session import get_session

logger = logging.getLogger(__name__)


class EnhancedStudyCardService:
    """Enhanced service for study card analysis with automatic evaluation."""
    
    def __init__(self, db_session: Optional[Session] = None):
        """Initialize the enhanced service."""
        self.quality_service = StudyCardQualityService(db_session)
        self.automatic_evaluator = AutomaticStudyCardEvaluator()
        self.db_session = db_session
    
    def automatic_evaluate_study_card(self, study_id: int, trial_id: int, extracted_jsonb: Dict[str, Any]) -> AutomaticEvaluation:
        """Perform automatic evaluation of a study card."""
        try:
            evaluation = self.automatic_evaluator.evaluate_study_card(
                study_id, trial_id, extracted_jsonb
            )
            
            # Save evaluation to database
            self._save_automatic_evaluation(evaluation)
            
            logger.info(f"Automatic evaluation completed for study {study_id}, trial {trial_id}: rank {evaluation.quality_rank}/10")
            return evaluation
            
        except Exception as e:
            logger.error(f"Error in automatic evaluation for study {study_id}, trial {trial_id}: {e}")
            raise
    
    def bulk_automatic_evaluate(self, limit: Optional[int] = None) -> List[AutomaticEvaluation]:
        """Perform automatic evaluation on all study cards in the database."""
        session = self.db_session or next(get_session())
        try:
            # Query studies with extracted data
            query = """
                SELECT s.study_id, s.trial_id, s.extracted_jsonb
                FROM studies s
                WHERE s.extracted_jsonb IS NOT NULL
                AND s.extracted_jsonb != '{}'
                ORDER BY s.study_id
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            result = session.execute(text(query))
            studies = result.fetchall()
            
            logger.info(f"Starting bulk automatic evaluation for {len(studies)} study cards")
            
            evaluations = []
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
                
                try:
                    evaluation = self.automatic_evaluate_study_card(study_id, trial_id, extracted_jsonb)
                    evaluations.append(evaluation)
                except Exception as e:
                    logger.error(f"Failed to evaluate study {study_id}: {e}")
                    continue
            
            logger.info(f"Bulk automatic evaluation completed: {len(evaluations)} evaluations successful")
            return evaluations
            
        except Exception as e:
            logger.error(f"Error in bulk automatic evaluation: {e}")
            return []
        finally:
            if not self.db_session:
                session.close()
    
    def get_automatic_rankings_summary(self) -> Dict[str, Any]:
        """Get summary statistics for automatic rankings."""
        session = self.db_session or next(get_session())
        try:
            # Get ranking distribution
            result = session.execute(text("""
                SELECT 
                    score_1_10,
                    COUNT(*) as count,
                    AVG(confidence_level) as avg_confidence
                FROM study_card_rankings 
                WHERE evaluator_id = 'auto_evaluator'
                GROUP BY score_1_10
                ORDER BY score_1_10
            """))
            
            ranking_distribution = {}
            total_studies = 0
            total_confidence = 0
            
            for row in result:
                score = row.score_1_10
                count = row.count
                avg_confidence = row.avg_confidence
                
                ranking_distribution[score] = {
                    "count": count,
                    "avg_confidence": float(avg_confidence) if avg_confidence else 0.0
                }
                total_studies += count
                total_confidence += count * avg_confidence if avg_confidence else 0
            
            # Calculate overall statistics
            overall_stats = {
                "total_studies": total_studies,
                "avg_ranking": sum(score * data["count"] for score, data in ranking_distribution.items()) / total_studies if total_studies > 0 else 0,
                "avg_confidence": total_confidence / total_studies if total_studies > 0 else 0,
                "ranking_distribution": ranking_distribution,
                "high_quality_studies": sum(data["count"] for score, data in ranking_distribution.items() if score >= 7),
                "medium_quality_studies": sum(data["count"] for score, data in ranking_distribution.items() if 4 <= score <= 6),
                "low_quality_studies": sum(data["count"] for score, data in ranking_distribution.items() if score <= 3)
            }
            
            return overall_stats
            
        except Exception as e:
            logger.error(f"Error getting automatic rankings summary: {e}")
            return {}
        finally:
            if not self.db_session:
                session.close()
    
    def get_risk_factor_summary(self) -> Dict[str, Any]:
        """Get summary of risk factors across all evaluated studies."""
        session = self.db_session or next(get_session())
        try:
            # Get risk factor counts from evaluation notes
            result = session.execute(text("""
                SELECT reasoning_text
                FROM study_card_rankings 
                WHERE evaluator_id = 'auto_evaluator'
                AND reasoning_text IS NOT NULL
            """))
            
            risk_factor_counts = {}
            total_high_risk = 0
            total_medium_risk = 0
            total_low_risk = 0
            
            for row in result:
                if row.reasoning_text:
                    notes = row.reasoning_text.split('\n')
                    for note in notes:
                        if "High-risk factors:" in note:
                            total_high_risk += 1
                        elif "Medium-risk factors:" in note:
                            total_medium_risk += 1
                        elif "Low-risk factors:" in note:
                            total_low_risk += 1
                        
                        # Count specific risk factors
                        for risk_factor in RiskFactor:
                            if risk_factor.value in note.lower():
                                risk_factor_counts[risk_factor.value] = risk_factor_counts.get(risk_factor.value, 0) + 1
            
            return {
                "total_high_risk_studies": total_high_risk,
                "total_medium_risk_studies": total_medium_risk,
                "total_low_risk_studies": total_low_risk,
                "risk_factor_breakdown": risk_factor_counts
            }
            
        except Exception as e:
            logger.error(f"Error getting risk factor summary: {e}")
            return {}
        finally:
            if not self.db_session:
                session.close()
    
    def get_study_evaluation_details(self, trial_id: int) -> Optional[AutomaticEvaluation]:
        """Get detailed evaluation information for a specific trial."""
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
            
            # Get existing automatic ranking
            ranking_result = session.execute(text("""
                SELECT score_1_10, confidence_level, reasoning_text
                FROM study_card_rankings 
                WHERE trial_id = :trial_id AND evaluator_id = 'auto_evaluator'
            """), {"trial_id": trial_id})
            
            ranking = ranking_result.fetchone()
            
            # Perform fresh evaluation
            extracted_jsonb = study.extracted_jsonb
            if isinstance(extracted_jsonb, str):
                try:
                    extracted_jsonb = json.loads(extracted_jsonb)
                except json.JSONDecodeError:
                    extracted_jsonb = {}
            
            evaluation = self.automatic_evaluator.evaluate_study_card(
                study.study_id, study.trial_id, extracted_jsonb
            )
            
            # If ranking exists, update evaluation with database values
            if ranking:
                evaluation.quality_rank = ranking.score_1_10
                evaluation.confidence_score = ranking.confidence_level / 5.0  # Convert 1-5 to 0-1
                if ranking.reasoning_text:
                    evaluation.evaluation_notes = ranking.reasoning_text.split('\n')
            
            return evaluation
            
        except Exception as e:
            logger.error(f"Error getting study evaluation details for trial {trial_id}: {e}")
            return None
        finally:
            if not self.db_session:
                session.close()
    
    def update_study_evaluation(self, trial_id: int) -> Optional[AutomaticEvaluation]:
        """Update automatic evaluation for a specific trial."""
        evaluation = self.get_study_evaluation_details(trial_id)
        if evaluation:
            # Save updated evaluation
            self._save_automatic_evaluation(evaluation)
            return evaluation
        return None
    
    def get_low_quality_studies(self, threshold: int = 5, limit: int = 100) -> List[AutomaticEvaluation]:
        """Get studies with automatic quality scores below threshold."""
        session = self.db_session or next(get_session())
        try:
            result = session.execute(text("""
                SELECT s.study_id, s.trial_id, s.extracted_jsonb
                FROM studies s
                JOIN study_card_rankings scr ON s.trial_id = scr.trial_id
                WHERE scr.evaluator_id = 'auto_evaluator'
                AND scr.score_1_10 <= :threshold
                ORDER BY scr.score_1_10 ASC, scr.confidence_level ASC
                LIMIT :limit
            """), {"threshold": threshold, "limit": limit})
            
            studies = result.fetchall()
            evaluations = []
            
            for study in studies:
                extracted_jsonb = study.extracted_jsonb
                if isinstance(extracted_jsonb, str):
                    try:
                        extracted_jsonb = json.loads(extracted_jsonb)
                    except json.JSONDecodeError:
                        extracted_jsonb = {}
                
                try:
                    evaluation = self.automatic_evaluator.evaluate_study_card(
                        study.study_id, study.trial_id, extracted_jsonb
                    )
                    evaluations.append(evaluation)
                except Exception as e:
                    logger.error(f"Failed to evaluate study {study.study_id}: {e}")
                    continue
            
            return evaluations
            
        except Exception as e:
            logger.error(f"Error getting low quality studies: {e}")
            return []
        finally:
            if not self.db_session:
                session.close()
    
    def _save_automatic_evaluation(self, evaluation: AutomaticEvaluation) -> bool:
        """Save automatic evaluation to the database."""
        session = self.db_session or next(get_session())
        try:
            # Check if ranking already exists
            existing = session.execute(
                text("""
                    SELECT ranking_id FROM study_card_rankings 
                    WHERE trial_id = :trial_id AND evaluator_id = 'auto_evaluator'
                """),
                {"trial_id": evaluation.trial_id, "evaluator_id": "auto_evaluator"}
            ).fetchone()
            
            reasoning_text = "\n".join(evaluation.evaluation_notes)
            
            if existing:
                # Update existing ranking
                session.execute(
                    text("""
                        UPDATE study_card_rankings 
                        SET score_1_10 = :score, confidence_level = :confidence,
                            reasoning_text = :reasoning, updated_at = NOW()
                        WHERE trial_id = :trial_id AND evaluator_id = 'auto_evaluator'
                    """),
                    {
                        "score": evaluation.quality_rank,
                        "confidence": int(evaluation.confidence_score * 5),  # Convert 0-1 to 1-5 scale
                        "reasoning": reasoning_text,
                        "trial_id": evaluation.trial_id,
                        "evaluator_id": "auto_evaluator"
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
                        "trial_id": evaluation.trial_id,
                        "evaluator_id": "auto_evaluator",
                        "score": evaluation.quality_rank,
                        "confidence": int(evaluation.confidence_score * 5),  # Convert 0-1 to 1-5 scale
                        "reasoning": reasoning_text
                    }
                )
            
            session.commit()
            logger.info(f"Saved automatic evaluation for trial {evaluation.trial_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving automatic evaluation: {e}")
            session.rollback()
            return False
        finally:
            if not self.db_session:
                session.close()
