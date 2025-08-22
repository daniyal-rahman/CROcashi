# tests/test_mapping_deterministic_companies.py
import pytest
from ncfd.mapping.deterministic import resolve_company
from ncfd.db.models import Company, CompanyAlias

@pytest.fixture
def seed_companies(session):
    alpha = Company(
        company_id=1001, cik=1000001,
        name="Alpha Therapeutics, Inc.",
        website_domain="alpha-thera.com",
    )
    beta = Company(
        company_id=1002, cik=1000002,
        name="Beta Pharma PLC",
        website_domain="betapharma.com",
    )
    session.add_all([alpha, beta]); session.commit()
    return {"alpha": alpha.company_id, "beta": beta.company_id}

@pytest.fixture
def seed_aliases(session, seed_companies):
    c1 = seed_companies["alpha"]; c2 = seed_companies["beta"]
    rows = [
        CompanyAlias(company_id=c1, alias="AlphaTx", alias_type="short",  source="unit_test"),
        CompanyAlias(company_id=c1, alias="Alpha Bio", alias_type="aka",  source="unit_test"),
        CompanyAlias(company_id=c1, alias="alphathera.com", alias_type="domain", source="unit_test"),
        CompanyAlias(company_id=c1, alias="Alpha Sub LLC", alias_type="subsidiary", source="10-K_ex21"),
        CompanyAlias(company_id=c2, alias="Beta Pharma Ltd.", alias_type="former_name", source="sec_submissions"),
    ]
    session.add_all(rows); session.commit()

def test_exact_company_name_match(session, seed_companies):
    r = resolve_company(session, "Alpha Therapeutics Inc")
    assert r and r.company_id == seed_companies["alpha"]
    assert r.method == "company_name_exact"

def test_alias_short_match(session, seed_companies, seed_aliases):
    r = resolve_company(session, "AlphaTx")
    assert r and r.company_id == seed_companies["alpha"]
    assert r.method == "alias_exact"

def test_alias_former_name_match(session, seed_companies, seed_aliases):
    r = resolve_company(session, "Beta Pharma Ltd")
    assert r and r.company_id == seed_companies["beta"]
    assert r.method == "alias_exact"

def test_subsidiary_maps_to_parent(session, seed_companies, seed_aliases):
    r = resolve_company(session, "Alpha Sub LLC")
    assert r and r.company_id == seed_companies["alpha"]

def test_domain_alias_match(session, seed_companies, seed_aliases):
    r = resolve_company(session, "Visit us at https://alphathera.com/contact")
    assert r and r.company_id == seed_companies["alpha"]
    assert r.method in ("domain_exact","website_domain")

def test_company_website_domain_match(session, seed_companies):
    r = resolve_company(session, "betapharma.com")
    assert r and r.company_id == seed_companies["beta"]
    assert r.method == "website_domain"

def test_ambiguous_alias_returns_none(session, seed_companies):
    from ncfd.db.models import CompanyAlias
    c1 = seed_companies["alpha"]; c2 = seed_companies["beta"]
    session.add_all([
        CompanyAlias(company_id=c1, alias="ALPHA", alias_type="short", source="unit_test"),
        CompanyAlias(company_id=c2, alias="ALPHA", alias_type="short", source="unit_test"),
    ])
    session.commit()
    r = resolve_company(session, "Alpha")
    assert r is None

def test_no_match_returns_none(session):
    assert resolve_company(session, "Regents of the University of X") is None
