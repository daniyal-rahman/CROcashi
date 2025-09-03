"""
Tests for GPT-5 thinking hook implementation.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import json

from ncfd.synthesis.gpt5_thinking_hook import (
    GPT5ThinkingHook,
    LiteratureReviewAgent,
    IndependentAnalysisAgent,
    LiteratureResult,
    IndependentAnalysis,
    trigger_gpt5_analysis_sync
)


@pytest.fixture
def mock_api_key():
    """Mock API key for testing."""
    return "test-api-key-12345"


@pytest.fixture
def mock_literature_response():
    """Mock literature review API response."""
    return json.dumps({
        "relevant_trials": [
            {
                "nct_id": "NCT01234567",
                "title": "Test Trial in NSCLC",
                "phase": "3",
                "indication": "Non-Small Cell Lung Cancer",
                "primary_endpoint": "Overall Survival",
                "results": "Success",
                "key_findings": "Positive results with HR 0.75",
                "relevance_score": 0.85,
                "url": "https://clinicaltrials.gov/ct2/show/NCT01234567"
            }
        ],
        "relevant_papers": [
            {
                "title": "Systematic Review of NSCLC Trials",
                "authors": "Smith et al.",
                "journal": "NEJM",
                "year": "2023",
                "doi": "10.1000/123456",
                "key_findings": "Meta-analysis shows consistent benefit",
                "relevance_score": 0.90,
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
            }
        ],
        "confidence_score": 0.85,
        "search_notes": "Comprehensive search completed"
    })


@pytest.fixture
def mock_analysis_response():
    """Mock independent analysis API response."""
    return json.dumps({
        "gpt5_p_fail": 0.75,
        "mechanistic_analysis": "Biological plausibility is moderate based on target expression patterns",
        "class_prior_analysis": "Historical success rate in this indication is 35%",
        "independent_risk_factors": ["sample_size_concern", "endpoint_choice"],
        "agreement_with_deterministic": 0.80,
        "additional_insights": ["Consider biomarker stratification"],
        "research_sources": ["NCT01234567", "Smith et al. 2023"],
        "confidence_level": "Medium",
        "strong_red_flags": ["Sample size may be insufficient for primary endpoint"],
        "recommendation": "Proceed with caution due to sample size concerns"
    })


class TestLiteratureReviewAgent:
    """Test the literature review agent."""
    
    @pytest.mark.asyncio
    async def test_review_literature_success(self, mock_api_key, mock_literature_response):
        """Test successful literature review."""
        agent = LiteratureReviewAgent(mock_api_key)
        
        with patch.object(agent, '_make_api_call', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_literature_response
            
            result = await agent.review_literature(
                trial_id="test_001",
                nct_id="NCT01234567",
                indication="Non-Small Cell Lung Cancer",
                phase="3",
                primary_endpoint="Overall Survival",
                mechanism="PD-1 inhibitor"
            )
            
            assert isinstance(result, LiteratureResult)
            assert result.trial_id == "test_001"
            assert result.nct_id == "NCT01234567"
            assert len(result.relevant_trials) == 1
            assert len(result.relevant_papers) == 1
            assert result.confidence_score == 0.85
            assert len(result.search_queries) > 0
    
    @pytest.mark.asyncio
    async def test_review_literature_failure(self, mock_api_key):
        """Test literature review failure handling."""
        agent = LiteratureReviewAgent(mock_api_key)
        
        with patch.object(agent, '_make_api_call', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("API call failed")
            
            result = await agent.review_literature(
                trial_id="test_001",
                nct_id="NCT01234567",
                indication="Non-Small Cell Lung Cancer",
                phase="3"
            )
            
            assert isinstance(result, LiteratureResult)
            assert result.confidence_score == 0.0
            assert len(result.relevant_trials) == 0
            assert len(result.relevant_papers) == 0
    
    def test_build_search_queries(self, mock_api_key):
        """Test search query building."""
        agent = LiteratureReviewAgent(mock_api_key)
        
        queries = agent._build_search_queries(
            indication="Non-Small Cell Lung Cancer",
            phase="3",
            primary_endpoint="Overall Survival",
            mechanism="PD-1 inhibitor"
        )
        
        assert len(queries) >= 4
        assert any("Phase 3" in query for query in queries)
        assert any("Overall Survival" in query for query in queries)
        assert any("PD-1 inhibitor" in query for query in queries)


class TestIndependentAnalysisAgent:
    """Test the independent analysis agent."""
    
    @pytest.mark.asyncio
    async def test_analyze_independently_success(self, mock_api_key, mock_analysis_response):
        """Test successful independent analysis."""
        agent = IndependentAnalysisAgent(mock_api_key)
        
        # Create mock literature result
        literature_result = LiteratureResult(
            trial_id="test_001",
            nct_id="NCT01234567",
            relevant_trials=[{"nct_id": "NCT01234567", "title": "Test Trial"}],
            relevant_papers=[{"title": "Test Paper", "year": "2023"}],
            search_queries=["test query"],
            confidence_score=0.85,
            timestamp=None
        )
        
        with patch.object(agent, '_make_api_call', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_analysis_response
            
            result = await agent.analyze_independently(
                trial_id="test_001",
                nct_id="NCT01234567",
                indication="Non-Small Cell Lung Cancer",
                phase="3",
                primary_endpoint="Overall Survival",
                p_fail=0.85,
                literature_result=literature_result
            )
            
            assert isinstance(result, IndependentAnalysis)
            assert result.trial_id == "test_001"
            assert result.nct_id == "NCT01234567"
            assert result.gpt5_p_fail == 0.75
            assert result.confidence_level == "Medium"
            assert len(result.strong_red_flags) == 1
            assert result.agreement_with_deterministic == 0.80
    
    @pytest.mark.asyncio
    async def test_analyze_independently_failure(self, mock_api_key):
        """Test independent analysis failure handling."""
        agent = IndependentAnalysisAgent(mock_api_key)
        
        literature_result = LiteratureResult(
            trial_id="test_001",
            nct_id="NCT01234567",
            relevant_trials=[],
            relevant_papers=[],
            search_queries=[],
            confidence_score=0.0,
            timestamp=None
        )
        
        with patch.object(agent, '_make_api_call', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("API call failed")
            
            result = await agent.analyze_independently(
                trial_id="test_001",
                nct_id="NCT01234567",
                indication="Non-Small Cell Lung Cancer",
                phase="3",
                primary_endpoint="Overall Survival",
                p_fail=0.85,
                literature_result=literature_result
            )
            
            assert isinstance(result, IndependentAnalysis)
            assert result.gpt5_p_fail == 0.5
            assert result.confidence_level == "Low"
            assert result.mechanistic_analysis == "Analysis failed"
    
    def test_prepare_literature_summary(self, mock_api_key):
        """Test literature summary preparation."""
        agent = IndependentAnalysisAgent(mock_api_key)
        
        literature_result = LiteratureResult(
            trial_id="test_001",
            nct_id="NCT01234567",
            relevant_trials=[
                {"nct_id": "NCT01234567", "title": "Test Trial", "results": "Success", "relevance_score": 0.85, "key_findings": "Positive results"}
            ],
            relevant_papers=[
                {"title": "Test Paper", "year": "2023", "relevance_score": 0.90, "key_findings": "Meta-analysis"}
            ],
            search_queries=["test query"],
            confidence_score=0.85,
            timestamp=None
        )
        
        summary = agent._prepare_literature_summary(literature_result)
        
        assert "Literature Review Confidence: 0.85" in summary
        assert "RELEVANT TRIALS:" in summary
        assert "RELEVANT PAPERS:" in summary
        assert "NCT01234567" in summary
        assert "Test Paper" in summary


class TestGPT5ThinkingHook:
    """Test the complete GPT-5 thinking hook."""
    
    def test_init(self, mock_api_key):
        """Test GPT-5 thinking hook initialization."""
        hook = GPT5ThinkingHook(mock_api_key)
        
        assert hook.api_key == mock_api_key
        assert isinstance(hook.literature_agent, LiteratureReviewAgent)
        assert isinstance(hook.analysis_agent, IndependentAnalysisAgent)
    
    @pytest.mark.asyncio
    async def test_trigger_thinking_analysis_success(self, mock_api_key, mock_literature_response, mock_analysis_response):
        """Test successful complete analysis."""
        hook = GPT5ThinkingHook(mock_api_key)
        
        with patch.object(hook.literature_agent, '_make_api_call', new_callable=AsyncMock) as mock_lit_call:
            mock_lit_call.return_value = mock_literature_response
            
            with patch.object(hook.analysis_agent, '_make_api_call', new_callable=AsyncMock) as mock_analysis_call:
                mock_analysis_call.return_value = mock_analysis_response
                
                result = await hook.trigger_thinking_analysis(
                    trial_id="test_001",
                    nct_id="NCT01234567",
                    indication="Non-Small Cell Lung Cancer",
                    phase="3",
                    primary_endpoint="Overall Survival",
                    mechanism="PD-1 inhibitor",
                    p_fail=0.85
                )
                
                assert isinstance(result, dict)
                assert result["trial_id"] == "test_001"
                assert result["nct_id"] == "NCT01234567"
                assert result["gpt5_p_fail"] == 0.75
                assert result["confidence_level"] == "Medium"
                assert result["literature_confidence"] == 0.85
                assert result["relevant_trials_count"] == 1
                assert result["relevant_papers_count"] == 1
                assert "timestamp" in result
                assert "analysis_quality" in result
                assert "disagreement_level" in result
                assert "recommendation_strength" in result
    
    @pytest.mark.asyncio
    async def test_trigger_thinking_analysis_failure(self, mock_api_key):
        """Test complete analysis failure handling."""
        hook = GPT5ThinkingHook(mock_api_key)
        
        with patch.object(hook.literature_agent, '_make_api_call', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("API call failed")
            
            result = await hook.trigger_thinking_analysis(
                trial_id="test_001",
                nct_id="NCT01234567",
                indication="Non-Small Cell Lung Cancer",
                phase="3",
                p_fail=0.85
            )
            
            assert isinstance(result, dict)
            assert result["trial_id"] == "test_001"
            assert result["nct_id"] == "NCT01234567"
            assert "error" in result
            assert result["gpt5_p_fail"] is None
            assert result["confidence_level"] == "Low"
    
    def test_calculate_analysis_quality(self, mock_api_key):
        """Test analysis quality calculation."""
        hook = GPT5ThinkingHook(mock_api_key)
        
        # High quality
        lit_result = LiteratureResult(
            trial_id="test_001",
            nct_id="NCT01234567",
            relevant_trials=[],
            relevant_papers=[],
            search_queries=[],
            confidence_score=0.85,
            timestamp=None
        )
        
        analysis_result = IndependentAnalysis(
            trial_id="test_001",
            nct_id="NCT01234567",
            gpt5_p_fail=0.75,
            mechanistic_analysis="",
            class_prior_analysis="",
            independent_risk_factors=[],
            agreement_with_deterministic=0.8,
            additional_insights=[],
            research_sources=[],
            confidence_level="High",
            strong_red_flags=[],
            recommendation="",
            timestamp=None
        )
        
        quality = hook._calculate_analysis_quality(lit_result, analysis_result)
        assert quality == "High"
        
        # Medium quality
        analysis_result.confidence_level = "Medium"
        quality = hook._calculate_analysis_quality(lit_result, analysis_result)
        assert quality == "Medium"
        
        # Low quality
        lit_result.confidence_score = 0.5
        analysis_result.confidence_level = "Low"
        quality = hook._calculate_analysis_quality(lit_result, analysis_result)
        assert quality == "Low"


def test_trigger_gpt5_analysis_sync(mock_api_key, mock_literature_response, mock_analysis_response):
    """Test synchronous wrapper function."""
    with patch('ncfd.synthesis.gpt5_thinking_hook.asyncio.run') as mock_run:
        mock_run.return_value = {
            "trial_id": "test_001",
            "nct_id": "NCT01234567",
            "gpt5_p_fail": 0.75,
            "confidence_level": "Medium"
        }
        
        result = trigger_gpt5_analysis_sync(
            api_key=mock_api_key,
            trial_id="test_001",
            nct_id="NCT01234567",
            indication="Non-Small Cell Lung Cancer",
            phase="3",
            primary_endpoint="Overall Survival",
            p_fail=0.85
        )
        
        assert isinstance(result, dict)
        assert result["trial_id"] == "test_001"
        assert result["nct_id"] == "NCT01234567"
        assert result["gpt5_p_fail"] == 0.75


class TestDataClasses:
    """Test the data classes."""
    
    def test_literature_result(self):
        """Test LiteratureResult dataclass."""
        result = LiteratureResult(
            trial_id="test_001",
            nct_id="NCT01234567",
            relevant_trials=[{"nct_id": "NCT01234567"}],
            relevant_papers=[{"title": "Test Paper"}],
            search_queries=["test query"],
            confidence_score=0.85,
            timestamp=None
        )
        
        assert result.trial_id == "test_001"
        assert result.nct_id == "NCT01234567"
        assert len(result.relevant_trials) == 1
        assert len(result.relevant_papers) == 1
        assert result.confidence_score == 0.85
    
    def test_independent_analysis(self):
        """Test IndependentAnalysis dataclass."""
        analysis = IndependentAnalysis(
            trial_id="test_001",
            nct_id="NCT01234567",
            gpt5_p_fail=0.75,
            mechanistic_analysis="Test analysis",
            class_prior_analysis="Test priors",
            independent_risk_factors=["risk1"],
            agreement_with_deterministic=0.8,
            additional_insights=["insight1"],
            research_sources=["source1"],
            confidence_level="High",
            strong_red_flags=["flag1"],
            recommendation="Test recommendation",
            timestamp=None
        )
        
        assert analysis.trial_id == "test_001"
        assert analysis.nct_id == "NCT01234567"
        assert analysis.gpt5_p_fail == 0.75
        assert analysis.confidence_level == "High"
        assert len(analysis.strong_red_flags) == 1
        assert analysis.agreement_with_deterministic == 0.8
