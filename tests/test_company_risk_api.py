"""
Integration tests for Company Risk API.
"""
import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from src.api.main import app
from database.config import get_db_session
from database.models.entities import Company

client = TestClient(app)


@pytest.fixture
def test_company():
    """Create a test company."""
    with get_db_session() as session:
        company = Company(
            name=f"Test Company {uuid4().hex[:8]}",
            status='active'
        )
        session.add(company)
        session.commit()
        yield company
        # Cleanup
        session.delete(company)
        session.commit()


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_get_risk_profile(test_company):
    """Test getting company risk profile."""
    response = client.get(f"/api/companies/{test_company.company_id}/risk-profile")
    
    assert response.status_code == 200
    data = response.json()
    assert 'risk_score' in data
    assert 'risk_category' in data
    assert 'components' in data
    assert 0 <= data['risk_score'] <= 100


def test_get_metrics(test_company):
    """Test getting company metrics."""
    response = client.get(f"/api/companies/{test_company.company_id}/metrics")
    
    assert response.status_code == 200
    data = response.json()
    assert 'total_trials' in data
    assert 'active_trials' in data
    assert 'terminated_count' in data


def test_get_timeline(test_company):
    """Test getting company timeline."""
    response = client.get(f"/api/companies/{test_company.company_id}/timeline")
    
    assert response.status_code == 200
    data = response.json()
    assert 'events' in data
    assert 'total_events' in data
    assert isinstance(data['events'], list)


def test_search_companies():
    """Test searching companies."""
    response = client.get("/api/companies/search?limit=10")
    
    assert response.status_code == 200
    data = response.json()
    assert 'companies' in data
    assert 'total' in data
    assert isinstance(data['companies'], list)


def test_search_with_filters():
    """Test searching with filters."""
    response = client.get("/api/companies/search?risk_category=LOW&limit=5")
    
    assert response.status_code == 200
    data = response.json()
    assert 'companies' in data
    # All returned companies should have LOW risk category
    for company in data['companies']:
        assert company['risk_category'] == 'LOW'


def test_invalid_company_id():
    """Test with invalid company ID."""
    fake_id = uuid4()
    response = client.get(f"/api/companies/{fake_id}/risk-profile")
    
    # Should return 404 or 500 depending on implementation
    assert response.status_code in [404, 500]

