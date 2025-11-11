"""
Integration tests for Company Risk Service.
"""
import pytest
from datetime import date, timedelta
from uuid import uuid4

from database.config import get_db_session
from src.services.company_risk_service import CompanyRiskService
from database.models.entities import Company
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialSponsor


@pytest.fixture
def db_session():
    """Get database session."""
    with get_db_session() as session:
        yield session


@pytest.fixture
def risk_service(db_session):
    """Get company risk service."""
    return CompanyRiskService(db_session)


@pytest.fixture
def test_company(db_session):
    """Create a test company."""
    company = Company(
        name=f"Test Company {uuid4().hex[:8]}",
        status='active'
    )
    db_session.add(company)
    db_session.flush()
    return company


def test_get_company_metrics(risk_service, test_company):
    """Test getting company metrics."""
    metrics = risk_service.get_company_metrics(test_company.company_id)
    
    assert 'company_id' in metrics
    assert metrics['company_id'] == str(test_company.company_id)
    assert 'total_trials' in metrics
    assert metrics['total_trials'] >= 0


def test_calculate_risk_score(risk_service, test_company):
    """Test calculating risk score."""
    result = risk_service.calculate_company_risk_score(test_company.company_id)
    
    assert 'risk_score' in result
    assert 0 <= result['risk_score'] <= 100
    assert 'risk_category' in result
    assert result['risk_category'] in ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']
    assert 'components' in result


def test_get_company_timeline(risk_service, test_company):
    """Test getting company timeline."""
    events = risk_service.get_company_timeline(test_company.company_id)
    
    assert isinstance(events, list)
    # Events should be ordered by date (most recent first)
    if len(events) > 1:
        assert events[0].event_date >= events[1].event_date


def test_get_company_trials(risk_service, test_company):
    """Test getting company trials."""
    trials = risk_service.get_company_trials(test_company.company_id)
    
    assert isinstance(trials, list)


def test_risk_score_components(risk_service, test_company):
    """Test that risk score components sum correctly."""
    result = risk_service.calculate_company_risk_score(test_company.company_id)
    
    components = result['components']
    total_score = (
        components['failure_rate']['score'] +
        components['recent_failures']['score'] +
        components['pipeline_stagnation']['score'] +
        components['warning_signals']['score']
    )
    
    # Allow small floating point differences
    assert abs(total_score - result['risk_score']) < 0.01


def test_risk_category_assignment(risk_service, test_company):
    """Test that risk categories are assigned correctly."""
    result = risk_service.calculate_company_risk_score(test_company.company_id)
    
    score = result['risk_score']
    category = result['risk_category']
    
    if score < 25:
        assert category == 'LOW'
    elif score < 50:
        assert category == 'MODERATE'
    elif score < 75:
        assert category == 'HIGH'
    else:
        assert category == 'CRITICAL'

