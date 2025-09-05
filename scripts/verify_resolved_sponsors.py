#!/usr/bin/env python3
"""
Verify resolved sponsors in the database.
"""

import json
import sys
from pathlib import Path

from ncfd.mapping.resolve_service import ResolveService
from ncfd.config import get_config


def load_wiring_results() -> Dict[str, Any]:
    """Load the wiring test results."""
    report_path = Path("backtest/ctgov_sec_wiring_report.json")
    if not report_path.exists():
        raise FileNotFoundError("Wiring report not found. Run the wiring test first.")
    
    with open(report_path, 'r') as f:
        return json.load(f)


def get_company_details(company_id: int) -> Dict[str, Any]:
    """Get company details from database using raw SQL."""
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    
    with session_scope(db_url) as session:
        # Get company details
        company_result = session.execute(
            text("SELECT company_id, name, cik, lei, country_incorp, state_incorp, sic, website_domain FROM companies WHERE company_id = :company_id"),
            {"company_id": company_id}
        ).fetchone()
        
        if not company_result:
            return None
        
        # Get primary security (ticker) information
        security_result = session.execute(
            text("""
            SELECT s.ticker, e.name as exchange_name, s.is_adr, s.currency 
            FROM securities s 
            LEFT JOIN exchanges e ON s.exchange_id = e.exchange_id 
            WHERE s.company_id = :company_id AND s.is_primary_listing = true AND s.active = true
            """),
            {"company_id": company_id}
        ).fetchone()
        
        ticker_info = {}
        if security_result:
            ticker_info = {
                "ticker": security_result[0],
                "exchange": security_result[1],
                "is_adr": security_result[2],
                "currency": security_result[3]
            }
        
        return {
            "company_id": company_result[0],
            "name": company_result[1],
            "cik": company_result[2],
            "lei": company_result[3],
            "country_incorp": company_result[4],
            "state_incorp": company_result[5],
            "sic": company_result[6],
            "website_domain": company_result[7],
            **ticker_info
        }


def verify_sec_cik(cik: str) -> Dict[str, Any]:
    """Verify CIK against SEC EDGAR."""
    if not cik:
        return {"valid": False, "error": "No CIK provided"}
    
    try:
        # SEC EDGAR API endpoint for company facts
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "valid": True,
                "company_name": data.get("entityName", "Unknown"),
                "cik": cik,
                "status": "Active"
            }
        elif response.status_code == 404:
            return {"valid": False, "error": "CIK not found in SEC database"}
        else:
            return {"valid": False, "error": f"SEC API error: {response.status_code}"}
            
    except Exception as e:
        return {"valid": False, "error": f"Request failed: {str(e)}"}


def analyze_resolved_sponsors() -> Dict[str, Any]:
    """Analyze resolved sponsors and verify them."""
    logger = get_logger(__name__)
    logger.info("Analyzing resolved sponsors...")
    
    # Load wiring results
    report = load_wiring_results()
    detailed_results = report.get("detailed_results", [])
    
    # Filter resolved sponsors
    resolved_results = [r for r in detailed_results if r.get("resolved", False)]
    
    logger.info(f"Found {len(resolved_results)} resolved sponsors to verify")
    
    # Group by company
    company_trials = {}
    for result in resolved_results:
        company_id = result.get("company_id")
        if company_id:
            if company_id not in company_trials:
                company_trials[company_id] = []
            company_trials[company_id].append(result)
    
    # Verify each company
    verification_results = {}
    
    for company_id, trials in company_trials.items():
        logger.info(f"Verifying company {company_id} ({len(trials)} trials)")
        
        # Get company details
        company_details = get_company_details(company_id)
        if not company_details:
            verification_results[company_id] = {
                "error": "Company not found in database",
                "trials": len(trials)
            }
            continue
        
        # Verify CIK
        sec_verification = verify_sec_cik(company_details.get("cik"))
        
        # Compile results
        verification_results[company_id] = {
            "company_details": company_details,
            "sec_verification": sec_verification,
            "trials": len(trials),
            "sponsors": [t.get("sponsor_name") for t in trials],
            "confidence_scores": [t.get("confidence", 0) for t in trials],
            "methods": [t.get("method", "") for t in trials]
        }
    
    return verification_results


def generate_verification_report(verification_results: Dict[str, Any]) -> str:
    """Generate a verification report."""
    report_lines = []
    report_lines.append("# Sponsor Resolution Verification Report")
    report_lines.append("")
    report_lines.append(f"Generated: {len(verification_results)} companies verified")
    report_lines.append("")
    
    # Summary statistics
    total_companies = len(verification_results)
    valid_ciks = sum(1 for r in verification_results.values() 
                    if r.get("sec_verification", {}).get("valid", False))
    invalid_ciks = total_companies - valid_ciks
    
    report_lines.append("## Summary")
    report_lines.append(f"- Total companies: {total_companies}")
    report_lines.append(f"- Valid CIKs: {valid_ciks}")
    report_lines.append(f"- Invalid CIKs: {invalid_ciks}")
    report_lines.append(f"- Success rate: {valid_ciks/total_companies*100:.1f}%")
    report_lines.append("")
    
    # Detailed results
    report_lines.append("## Detailed Results")
    report_lines.append("")
    
    for company_id, result in verification_results.items():
        company_details = result.get("company_details", {})
        sec_verification = result.get("sec_verification", {})
        
        report_lines.append(f"### Company ID: {company_id}")
        report_lines.append(f"- **Name:** {company_details.get('name', 'Unknown')}")
        report_lines.append(f"- **CIK:** {company_details.get('cik', 'None')}")
        report_lines.append(f"- **Ticker:** {company_details.get('ticker', 'None')}")
        report_lines.append(f"- **Exchange:** {company_details.get('exchange', 'None')}")
        report_lines.append(f"- **Country:** {company_details.get('country_incorp', 'None')}")
        report_lines.append(f"- **State:** {company_details.get('state_incorp', 'None')}")
        report_lines.append(f"- **Trials:** {result.get('trials', 0)}")
        
        if sec_verification.get("valid"):
            report_lines.append(f"- **SEC Status:** ✅ Valid - {sec_verification.get('company_name', 'Unknown')}")
        else:
            report_lines.append(f"- **SEC Status:** ❌ Invalid - {sec_verification.get('error', 'Unknown error')}")
        
        report_lines.append(f"- **Sponsors:** {', '.join(result.get('sponsors', []))}")
        report_lines.append(f"- **Methods:** {', '.join(set(result.get('methods', [])))}")
        report_lines.append(f"- **Avg Confidence:** {sum(result.get('confidence_scores', [0]))/len(result.get('confidence_scores', [1])):.3f}")
        report_lines.append("")
    
    return "\n".join(report_lines)


def main():
    """Main entry point."""
    setup_logging()
    logger = get_logger(__name__)
    
    try:
        # Analyze resolved sponsors
        verification_results = analyze_resolved_sponsors()
        
        # Generate report
        report = generate_verification_report(verification_results)
        
        # Save report
        report_path = Path("backtest/sponsor_verification_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, 'w') as f:
            f.write(report)
        
        logger.info(f"Verification report saved to {report_path}")
        
        # Print summary
        total_companies = len(verification_results)
        valid_ciks = sum(1 for r in verification_results.values() 
                        if r.get("sec_verification", {}).get("valid", False))
        
        print(f"\n🔍 Sponsor Verification Summary:")
        print(f"  Total companies: {total_companies}")
        print(f"  Valid CIKs: {valid_ciks}")
        print(f"  Invalid CIKs: {total_companies - valid_ciks}")
        print(f"  Success rate: {valid_ciks/total_companies*100:.1f}%")
        print(f"  Report saved to: {report_path}")
        
        # Show top companies
        print(f"\n📊 Top Companies by Trial Count:")
        sorted_companies = sorted(verification_results.items(), 
                                key=lambda x: x[1].get("trials", 0), reverse=True)
        
        for company_id, result in sorted_companies[:5]:
            company_details = result.get("company_details", {})
            trials = result.get("trials", 0)
            sec_valid = result.get("sec_verification", {}).get("valid", False)
            status = "✅" if sec_valid else "❌"
            print(f"  {status} {company_details.get('name', 'Unknown')}: {trials} trials")
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        print(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
    
    return 0


if __name__ == "__main__":
    exit(main())
