"""
Independent LLM Analysis Implementation

Two-agent system:
1. Literature Review Agent: Finds relevant trials and literature
2. Independent Analysis Agent: Analyzes evidence and makes predictions
"""

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import aiohttp
from pydantic import BaseModel
from dotenv import load_dotenv

from ..llm.json_parser import parse_llm_json_response, validate_confidence_score
from ..llm.schema_validator import validate_literature_review, validate_independent_analysis
from ..utils.config_manager import get_config_manager
from ..utils.error_handler import get_error_handler, safe_execute

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class LiteratureResult:
    """Result from literature review agent."""
    trial_id: str
    nct_id: str
    relevant_trials: List[Dict[str, Any]]  # List of relevant trial summaries
    relevant_papers: List[Dict[str, Any]]   # List of relevant paper summaries
    search_queries: List[str]              # Queries used for search
    confidence_score: float               # Confidence in literature review
    timestamp: datetime


@dataclass
class IndependentAnalysis:
    """Result from independent analysis agent."""
    trial_id: str
    nct_id: str
    gpt5_p_fail: float                    # GPT-5's independent P_fail prediction
    mechanistic_analysis: str             # Biological plausibility analysis
    class_prior_analysis: str             # Historical context analysis
    independent_risk_factors: List[str]   # GPT-5's identified risks
    agreement_with_deterministic: float   # Agreement level (0-1)
    additional_insights: List[str]        # Novel insights from GPT-5
    research_sources: List[str]           # Sources GPT-5 consulted
    confidence_level: str                 # High/Medium/Low confidence
    strong_red_flags: List[str]           # Only very strong red flags
    recommendation: str                   # Final recommendation
    timestamp: datetime


class LiteratureReviewAgent:
    """Agent responsible for finding relevant literature and trials."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        self.model = model
        self.base_url = "https://api.openai.com/v1/chat/completions"
    
    async def _make_api_call(self, messages: List[Dict[str, str]]) -> str:
        """Make API call to OpenAI."""
        # Validate messages to prevent null content errors
        for msg in messages:
            if not msg.get("content") or msg.get("content").strip() == "":
                raise ValueError(f"Empty or null content in message: {msg}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4000
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.base_url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    error_text = await response.text()
                    raise Exception(f"API call failed: {response.status} - {error_text}")
    
    async def review_literature(
        self, 
        trial_id: str,
        nct_id: str,
        indication: str,
        phase: str,
        primary_endpoint: Optional[str] = None,
        mechanism: Optional[str] = None
    ) -> LiteratureResult:
        """
        Conduct comprehensive literature review for a trial.
        
        Args:
            trial_id: Internal trial ID
            nct_id: ClinicalTrials.gov ID
            indication: Disease indication
            phase: Trial phase
            primary_endpoint: Primary endpoint (if known)
            mechanism: Mechanism of action (if known)
            
        Returns:
            LiteratureResult with relevant trials and papers
        """
        
        # Build search queries
        search_queries = self._build_search_queries(indication, phase, primary_endpoint, mechanism)
        
        # Ensure required parameters are not empty
        indication = indication or "Unknown indication"
        phase = phase or "Unknown phase"
        nct_id = nct_id or "Unknown NCT ID"
        
        # Literature review prompt with fallback
        prompt = f"""
You are a clinical research expert conducting a comprehensive literature review for trial {nct_id} in {indication}.

TRIAL CONTEXT:
- NCT ID: {nct_id}
- Phase: {phase}
- Indication: {indication}
- Primary Endpoint: {primary_endpoint or "Not specified"}
- Mechanism: {mechanism or "Not specified"}

SEARCH QUERIES TO USE:
{chr(10).join(f"- {query}" for query in search_queries)}

TASK:
1. Search for the most relevant clinical trials in the same indication and phase
2. Find key papers that establish class priors and historical context
3. Identify trials with similar endpoints or mechanisms
4. Focus on trials from the last 10 years

REQUIRED OUTPUT FORMAT (JSON):
{{
    "relevant_trials": [
        {{
            "nct_id": "NCT...",
            "title": "Trial title",
            "phase": "Phase",
            "indication": "Disease",
            "primary_endpoint": "Endpoint",
            "results": "Success/Failure/Unknown",
            "key_findings": "Brief summary",
            "relevance_score": 0.85,
            "url": "Link to trial"
        }}
    ],
    "relevant_papers": [
        {{
            "title": "Paper title",
            "authors": "Authors",
            "journal": "Journal",
            "year": "Year",
            "doi": "DOI",
            "key_findings": "Brief summary",
            "relevance_score": 0.75,
            "url": "Link to paper"
        }}
    ],
    "confidence_score": 0.8,
    "search_notes": "Brief notes on search strategy"
}}

CRITICAL: All numeric values MUST be strict JSON numbers (e.g., 0.85, not "eighty-five" or "85%"). 
Use decimal format for scores (0.0-1.0 range).

IMPORTANT:
- Only include trials/papers with relevance_score >= 0.7
- Focus on pivotal trials and high-impact papers
- Include both positive and negative results
- Prioritize recent evidence
- Be specific about endpoints and mechanisms
"""

        try:
            response = await self._make_api_call([
                {"role": "system", "content": "You are a clinical research expert specializing in literature review and trial analysis."},
                {"role": "user", "content": prompt}
            ])
            
            # Parse JSON response with robust error handling
            data = parse_llm_json_response(response, expected_fields=["relevant_trials", "relevant_papers", "confidence_score"])
            if not data:
                raise Exception("Could not parse JSON response")
            
            # Validate against schema
            try:
                data = validate_literature_review(data)
            except Exception as e:
                logger.warning(f"Schema validation failed, using raw data: {e}")
                # Continue with raw data if validation fails
            
            return LiteratureResult(
                trial_id=trial_id,
                nct_id=nct_id,
                relevant_trials=data.get("relevant_trials", []),
                relevant_papers=data.get("relevant_papers", []),
                search_queries=search_queries,
                confidence_score=validate_confidence_score(data.get("confidence_score", 0.5), "confidence_score"),
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            logger.error(f"Literature review failed for {nct_id}: {e}")
            # Return minimal result
            return LiteratureResult(
                trial_id=trial_id,
                nct_id=nct_id,
                relevant_trials=[],
                relevant_papers=[],
                search_queries=search_queries,
                confidence_score=0.0,
                timestamp=datetime.now(timezone.utc)
            )
    
    def _build_search_queries(
        self, 
        indication: str, 
        phase: str, 
        primary_endpoint: Optional[str],
        mechanism: Optional[str]
    ) -> List[str]:
        """Build search queries for literature review."""
        queries = []
        
        # Basic indication + phase query
        queries.append(f'"{indication}" AND "Phase {phase}" AND "clinical trial"')
        
        # Add endpoint-specific query if available
        if primary_endpoint:
            queries.append(f'"{indication}" AND "{primary_endpoint}" AND "clinical trial"')
        
        # Add mechanism-specific query if available
        if mechanism:
            queries.append(f'"{indication}" AND "{mechanism}" AND "clinical trial"')
        
        # Class prior query
        queries.append(f'"{indication}" AND "systematic review" AND "meta-analysis"')
        
        # Historical context query
        queries.append(f'"{indication}" AND "pivotal trial" AND "FDA approval"')
        
        return queries


class IndependentAnalysisAgent:
    """Agent responsible for independent analysis and prediction."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        self.model = model
        self.base_url = "https://api.openai.com/v1/chat/completions"
    
    async def _make_api_call(self, messages: List[Dict[str, str]]) -> str:
        """Make API call to OpenAI."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4000
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.base_url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    error_text = await response.text()
                    raise Exception(f"API call failed: {response.status} - {error_text}")
    
    async def analyze_independently(
        self,
        trial_id: str,
        nct_id: str,
        indication: str,
        phase: str,
        primary_endpoint: Optional[str],
        p_fail: float,
        literature_result: LiteratureResult
    ) -> IndependentAnalysis:
        """
        Conduct independent analysis based on literature review.
        
        Args:
            trial_id: Internal trial ID
            nct_id: ClinicalTrials.gov ID
            indication: Disease indication
            phase: Trial phase
            primary_endpoint: Primary endpoint
            p_fail: Deterministic P_fail score
            literature_result: Results from literature review
            
        Returns:
            IndependentAnalysis with GPT-5's independent assessment
        """
        
        # Prepare literature summary
        literature_summary = self._prepare_literature_summary(literature_result)
        
        # Independent analysis prompt
        prompt = f"""
You are a senior clinical research analyst conducting an independent assessment of trial {nct_id}.

TRIAL CONTEXT:
- NCT ID: {nct_id}
- Phase: {phase}
- Indication: {indication}
- Primary Endpoint: {primary_endpoint or "Not specified"}
- Deterministic P_fail: {p_fail:.3f}

LITERATURE CONTEXT:
{literature_summary}

TASK:
Based on the literature review and your clinical expertise, provide an independent assessment.

IMPORTANT CONSTRAINTS:
1. ONLY recommend with VERY STRONG red flags and issues
2. Be conservative - if evidence is unclear, don't make strong predictions
3. Focus on mechanistic plausibility and class priors
4. Consider historical context and regulatory precedents
5. Only predict high P_fail if there are clear, strong signals

REQUIRED OUTPUT FORMAT (JSON):
{{
    "gpt5_p_fail": 0.75,
    "mechanistic_analysis": "Detailed biological plausibility analysis",
    "class_prior_analysis": "Historical context and class priors",
    "independent_risk_factors": ["risk1", "risk2"],
    "agreement_with_deterministic": 0.8,
    "additional_insights": ["insight1", "insight2"],
    "research_sources": ["source1", "source2"],
    "confidence_level": "High",
    "strong_red_flags": ["Only very strong red flags"],
    "recommendation": "Final recommendation with justification",
    "reasoning": "Detailed reasoning for P_fail prediction"
}}

CRITICAL: All numeric values MUST be strict JSON numbers (e.g., 0.75, not "seventy-five" or "75%"). 
Use decimal format for scores (0.0-1.0 range).

CONFIDENCE LEVELS:
- High: Clear mechanistic issues + strong class priors + multiple red flags
- Medium: Some concerns but unclear evidence
- Low: Limited evidence or unclear signals

STRONG RED FLAGS (only include if VERY strong):
- Clear mechanistic implausibility
- Multiple failed trials in same class
- Endpoint issues (surrogate vs clinical)
- Sample size concerns with clear evidence
- Regulatory precedents against approval
"""

        try:
            response = await self._make_api_call([
                {"role": "system", "content": "You are a senior clinical research analyst with expertise in trial prediction and risk assessment."},
                {"role": "user", "content": prompt}
            ])
            
            # Parse JSON response with robust error handling
            data = parse_llm_json_response(response, expected_fields=["gpt5_p_fail", "confidence_level", "agreement_with_deterministic"])
            if not data:
                raise Exception("Could not parse JSON response")
            
            # Validate against schema
            try:
                data = validate_independent_analysis(data)
            except Exception as e:
                logger.warning(f"Schema validation failed, using raw data: {e}")
                # Continue with raw data if validation fails
            
            return IndependentAnalysis(
                trial_id=trial_id,
                nct_id=nct_id,
                gpt5_p_fail=validate_confidence_score(data.get("gpt5_p_fail", 0.5), "gpt5_p_fail"),
                mechanistic_analysis=data.get("mechanistic_analysis", ""),
                class_prior_analysis=data.get("class_prior_analysis", ""),
                independent_risk_factors=data.get("independent_risk_factors", []),
                agreement_with_deterministic=validate_confidence_score(data.get("agreement_with_deterministic", 0.5), "agreement_with_deterministic"),
                additional_insights=data.get("additional_insights", []),
                research_sources=data.get("research_sources", []),
                confidence_level=data.get("confidence_level", "Low"),
                strong_red_flags=data.get("strong_red_flags", []),
                recommendation=data.get("recommendation", ""),
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            logger.error(f"Independent analysis failed for {nct_id}: {e}")
            # Return minimal result
            return IndependentAnalysis(
                trial_id=trial_id,
                nct_id=nct_id,
                gpt5_p_fail=0.5,
                mechanistic_analysis="Analysis failed",
                class_prior_analysis="Analysis failed",
                independent_risk_factors=[],
                agreement_with_deterministic=0.5,
                additional_insights=[],
                research_sources=[],
                confidence_level="Low",
                strong_red_flags=[],
                recommendation="Analysis failed",
                timestamp=datetime.now(timezone.utc)
            )
    
    def _prepare_literature_summary(self, literature_result: LiteratureResult) -> str:
        """Prepare literature summary for analysis."""
        summary = f"Literature Review Confidence: {literature_result.confidence_score:.2f}\n\n"
        
        if literature_result.relevant_trials:
            summary += "RELEVANT TRIALS:\n"
            for trial in literature_result.relevant_trials[:5]:  # Top 5
                summary += f"- {trial.get('nct_id', 'N/A')}: {trial.get('title', 'N/A')}\n"
                summary += f"  Results: {trial.get('results', 'N/A')}, Relevance: {trial.get('relevance_score', 0):.2f}\n"
                summary += f"  Key: {trial.get('key_findings', 'N/A')}\n\n"
        
        if literature_result.relevant_papers:
            summary += "RELEVANT PAPERS:\n"
            for paper in literature_result.relevant_papers[:3]:  # Top 3
                summary += f"- {paper.get('title', 'N/A')} ({paper.get('year', 'N/A')})\n"
                summary += f"  Relevance: {paper.get('relevance_score', 0):.2f}\n"
                summary += f"  Key: {paper.get('key_findings', 'N/A')}\n\n"
        
        return summary


class IndependentLLMAnalysis:
    """Complete independent LLM analysis with two-agent system."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        self.literature_agent = LiteratureReviewAgent(api_key, model)
        self.analysis_agent = IndependentAnalysisAgent(api_key, model)
    
    async def trigger_thinking_analysis(
        self,
        trial_id: str,
        nct_id: str,
        indication: str,
        phase: str,
        primary_endpoint: Optional[str] = None,
        mechanism: Optional[str] = None,
        p_fail: float = 0.0
    ) -> Dict[str, Any]:
        """
        Trigger complete GPT-5 thinking analysis.
        
        Args:
            trial_id: Internal trial ID
            nct_id: ClinicalTrials.gov ID
            indication: Disease indication
            phase: Trial phase
            primary_endpoint: Primary endpoint (if known)
            mechanism: Mechanism of action (if known)
            p_fail: Deterministic P_fail score
            
        Returns:
            Dict containing complete analysis results
        """
        
        logger.info(f"Starting GPT-5 thinking analysis for {nct_id}")
        
        try:
            # Step 1: Literature Review
            logger.info(f"Step 1: Literature review for {nct_id}")
            literature_result = await self.literature_agent.review_literature(
                trial_id=trial_id,
                nct_id=nct_id,
                indication=indication,
                phase=phase,
                primary_endpoint=primary_endpoint,
                mechanism=mechanism
            )
            
            # Check if we have any literature to analyze
            if not literature_result.relevant_trials and not literature_result.relevant_papers:
                logger.warning(f"No literature found for NCT {nct_id}; skipping LLM analysis")
                return self._create_empty_analysis_result(trial_id, nct_id, "No relevant literature found")
            
            # Step 2: Independent Analysis
            logger.info(f"Step 2: Independent analysis for {nct_id}")
            analysis_result = await self.analysis_agent.analyze_independently(
                trial_id=trial_id,
                nct_id=nct_id,
                indication=indication,
                phase=phase,
                primary_endpoint=primary_endpoint,
                p_fail=p_fail,
                literature_result=literature_result
            )
            
            # Combine results
            result = {
                "trial_id": trial_id,
                "nct_id": nct_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                
                # Literature review results
                "literature_confidence": literature_result.confidence_score,
                "relevant_trials_count": len(literature_result.relevant_trials),
                "relevant_papers_count": len(literature_result.relevant_papers),
                "search_queries": literature_result.search_queries,
                
                # Independent analysis results
                "gpt5_p_fail": analysis_result.gpt5_p_fail,
                "mechanistic_analysis": analysis_result.mechanistic_analysis,
                "class_prior_analysis": analysis_result.class_prior_analysis,
                "independent_risk_factors": analysis_result.independent_risk_factors,
                "agreement_with_deterministic": analysis_result.agreement_with_deterministic,
                "additional_insights": analysis_result.additional_insights,
                "research_sources": analysis_result.research_sources,
                "confidence_level": analysis_result.confidence_level,
                "strong_red_flags": analysis_result.strong_red_flags,
                "recommendation": analysis_result.recommendation,
                
                # Summary metrics
                "analysis_quality": self._calculate_analysis_quality(literature_result, analysis_result),
                "disagreement_level": abs(p_fail - analysis_result.gpt5_p_fail),
                "recommendation_strength": len(analysis_result.strong_red_flags)
            }
            
            logger.info(f"GPT-5 thinking analysis completed for {nct_id}")
            return result
            
        except Exception as e:
            logger.error(f"GPT-5 thinking analysis failed for {nct_id}: {e}")
            return {
                "trial_id": trial_id,
                "nct_id": nct_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "gpt5_p_fail": None,
                "confidence_level": "Low",
                "recommendation": "Analysis failed"
            }
    
    def _create_empty_analysis_result(self, trial_id: str, nct_id: str, reason: str) -> Dict[str, Any]:
        """Create empty analysis result when no literature is available."""
        return {
            "trial_id": trial_id,
            "nct_id": nct_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": reason,
            "gpt5_p_fail": None,
            "confidence_level": "Low",
            "recommendation": "Insufficient data for analysis",
            "literature_confidence": 0.0,
            "relevant_trials_count": 0,
            "relevant_papers_count": 0,
            "analysis_quality": "Low"
        }
    
    def _calculate_analysis_quality(
        self, 
        literature_result: LiteratureResult, 
        analysis_result: IndependentAnalysis
    ) -> str:
        """Calculate overall analysis quality."""
        if literature_result.confidence_score >= 0.8 and analysis_result.confidence_level == "High":
            return "High"
        elif literature_result.confidence_score >= 0.6 and analysis_result.confidence_level in ["High", "Medium"]:
            return "Medium"
        else:
            return "Low"


# Convenience function for synchronous usage
def trigger_independent_llm_analysis_sync(
    trial_id: str,
    nct_id: str,
    indication: str,
    phase: str,
    api_key: Optional[str] = None,
    primary_endpoint: Optional[str] = None,
    mechanism: Optional[str] = None,
    p_fail: float = 0.0
) -> Dict[str, Any]:
    """Synchronous wrapper for independent LLM analysis."""
    hook = IndependentLLMAnalysis(api_key)
    return asyncio.run(hook.trigger_thinking_analysis(
        trial_id=trial_id,
        nct_id=nct_id,
        indication=indication,
        phase=phase,
        primary_endpoint=primary_endpoint,
        mechanism=mechanism,
        p_fail=p_fail
    ))
