"""
Generate comprehensive test report.

Combines basic and detailed verification, exports to markdown.
"""
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.verify_system_basic import get_basic_stats
from scripts.verify_system_detailed import get_detailed_stats

logger = logging.getLogger(__name__)


def generate_markdown_report(
    test_run_id: Optional[str] = None,
    phase: str = 'small_sample',
    ingestion_summary: Optional[Dict[str, Any]] = None,
    processing_summary: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate markdown test report.
    
    Args:
        test_run_id: Test run ID
        phase: Test phase ('small_sample' or 'scale_test')
        ingestion_summary: Optional ingestion summary from test_all_sources_ingestion
        processing_summary: Optional processing summary from process_test_sources
    
    Returns:
        Markdown report as string
    """
    # Get statistics
    basic_stats = get_basic_stats(test_run_id=test_run_id)
    detailed_stats = get_detailed_stats(test_run_id=test_run_id)
    
    # Build report
    report_lines = []
    
    # Header
    report_lines.append("# System Test Report")
    report_lines.append("")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"**Test Phase:** {phase}")
    if test_run_id:
        report_lines.append(f"**Test Run ID:** {test_run_id}")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    # Test Metadata
    report_lines.append("## Test Metadata")
    report_lines.append("")
    if ingestion_summary:
        report_lines.append(f"- **Ingestion Start:** {ingestion_summary.get('start_time', 'N/A')}")
        report_lines.append(f"- **Ingestion End:** {ingestion_summary.get('end_time', 'N/A')}")
        report_lines.append(f"- **Ingestion Duration:** {ingestion_summary.get('duration_seconds', 0):.1f} seconds")
        report_lines.append(f"- **Sample Size:** {ingestion_summary.get('sample_size', 'N/A')}")
        report_lines.append(f"- **Sources Attempted:** {ingestion_summary.get('sources_attempted', 0)}")
        report_lines.append(f"- **Sources Successful:** {ingestion_summary.get('sources_successful', 0)}")
        report_lines.append(f"- **Sources Failed:** {ingestion_summary.get('sources_failed', 0)}")
        report_lines.append("")
    
    if processing_summary:
        report_lines.append(f"- **Processing Start:** {processing_summary.get('start_time', 'N/A')}")
        report_lines.append(f"- **Processing End:** {processing_summary.get('end_time', 'N/A')}")
        report_lines.append(f"- **Processing Duration:** {processing_summary.get('duration_seconds', 0):.1f} seconds")
        report_lines.append(f"- **Reprocessing Strategy:** {processing_summary.get('reprocess_strategy', 'N/A')}")
        report_lines.append(f"- **Sources Processed:** {processing_summary.get('sources_processed', 0)}")
        report_lines.append(f"- **Sources Failed:** {processing_summary.get('sources_failed', 0)}")
        report_lines.append("")
    
    # Summary Statistics
    report_lines.append("## Summary Statistics")
    report_lines.append("")
    report_lines.append("### Staging Records")
    report_lines.append("")
    report_lines.append(f"- **Total:** {basic_stats['staging']['total']:,}")
    report_lines.append(f"- **Processed:** {basic_stats['staging']['processed']:,}")
    report_lines.append(f"- **Unprocessed:** {basic_stats['staging']['unprocessed']:,}")
    report_lines.append("")
    
    report_lines.append("### Entities")
    report_lines.append("")
    for entity_type, count in basic_stats['entities'].items():
        report_lines.append(f"- **{entity_type.title()}:** {count:,}")
    report_lines.append("")
    
    report_lines.append("### Relationships")
    report_lines.append("")
    for rel_type, count in basic_stats['relationships'].items():
        report_lines.append(f"- **{rel_type.replace('_', ' ').title()}:** {count:,}")
    report_lines.append("")
    
    report_lines.append("### Processing")
    report_lines.append("")
    report_lines.append(f"- **Total Logs:** {basic_stats['processing']['total']:,}")
    report_lines.append(f"- **Successful:** {basic_stats['processing']['success']:,}")
    report_lines.append(f"- **Failed:** {basic_stats['processing']['failed']:,}")
    report_lines.append(f"- **Success Rate:** {basic_stats['processing']['success_rate']:.1f}%")
    report_lines.append("")
    
    # Ingestion Results
    if ingestion_summary:
        report_lines.append("## Ingestion Results")
        report_lines.append("")
        report_lines.append(f"- **Records Inserted:** {ingestion_summary.get('total_records_inserted', 0):,}")
        report_lines.append(f"- **Records Skipped:** {ingestion_summary.get('total_records_skipped', 0):,}")
        report_lines.append(f"- **Errors:** {ingestion_summary.get('total_errors', 0):,}")
        report_lines.append("")
        
        if ingestion_summary.get('results'):
            report_lines.append("### Per-Source Ingestion")
            report_lines.append("")
            report_lines.append("| Source | Status | Inserted | Skipped | Errors |")
            report_lines.append("|--------|--------|----------|---------|--------|")
            for result in ingestion_summary['results']:
                status = result.get('status', 'unknown')
                inserted = result.get('records_inserted', 0)
                skipped = result.get('records_skipped', 0)
                errors = result.get('errors', 0)
                report_lines.append(f"| {result['source_name']} | {status} | {inserted} | {skipped} | {errors} |")
            report_lines.append("")
    
    # Processing Results
    if processing_summary:
        report_lines.append("## Processing Results")
        report_lines.append("")
        report_lines.append(f"- **Records Processed:** {processing_summary.get('total_records_processed', 0):,}")
        report_lines.append(f"- **Records Failed:** {processing_summary.get('total_records_failed', 0):,}")
        report_lines.append(f"- **Entities Created:** {processing_summary.get('total_entities_created', 0):,}")
        report_lines.append(f"- **Entities Matched:** {processing_summary.get('total_entities_matched', 0):,}")
        report_lines.append(f"- **Relationships Created:** {processing_summary.get('total_relationships_created', 0):,}")
        report_lines.append(f"- **Needs Review:** {processing_summary.get('total_needs_review', 0):,}")
        report_lines.append("")
        
        if processing_summary.get('source_results'):
            report_lines.append("### Per-Source Processing")
            report_lines.append("")
            report_lines.append("| Source | Status | Processed | Entities | Relationships |")
            report_lines.append("|--------|--------|-----------|----------|---------------|")
            for result in processing_summary['source_results']:
                status = result.get('status', 'unknown')
                processed = result.get('records_processed', 0)
                entities = result.get('entities_created', 0)
                relationships = result.get('relationships_created', 0)
                report_lines.append(f"| {result['source_name']} | {status} | {processed} | {entities} | {relationships} |")
            report_lines.append("")
    
    # Detailed Per-Source Breakdown
    report_lines.append("## Per-Source Detailed Breakdown")
    report_lines.append("")
    for source_name, source_stats in sorted(detailed_stats['per_source'].items()):
        report_lines.append(f"### {source_name}")
        report_lines.append("")
        report_lines.append(f"- **Staging:** {source_stats['staging']['total']} total, "
                          f"{source_stats['staging']['processed']} processed, "
                          f"{source_stats['staging']['unprocessed']} unprocessed")
        report_lines.append(f"- **Processing:** {source_stats['processing']['successful']}/{source_stats['processing']['total_logs']} successful "
                          f"({source_stats['processing']['success_rate']:.1f}%)")
        report_lines.append(f"- **Entities:** {source_stats['entities']['created']} created, "
                          f"{source_stats['entities']['matched']} matched")
        report_lines.append(f"- **Relationships:** {source_stats['relationships']['created']} created")
        report_lines.append("")
    
    # Relationship Quality
    report_lines.append("## Relationship Quality")
    report_lines.append("")
    coverage = detailed_stats['relationship_quality']['coverage']
    report_lines.append("### Coverage")
    report_lines.append("")
    report_lines.append(f"- **Trials with Sponsors:** {coverage['trials_with_sponsors']['count']} "
                      f"({coverage['trials_with_sponsors']['percentage']:.1f}%)")
    report_lines.append(f"- **Trials with Drugs:** {coverage['trials_with_drugs']['count']} "
                      f"({coverage['trials_with_drugs']['percentage']:.1f}%)")
    report_lines.append(f"- **Trials with Diseases:** {coverage['trials_with_diseases']['count']} "
                      f"({coverage['trials_with_diseases']['percentage']:.1f}%)")
    report_lines.append(f"- **Companies with Drugs:** {coverage['companies_with_drugs']['count']} "
                      f"({coverage['companies_with_drugs']['percentage']:.1f}%)")
    report_lines.append("")
    
    # Entity Resolution Quality
    report_lines.append("## Entity Resolution Quality")
    report_lines.append("")
    match_candidates = detailed_stats['entity_resolution_quality']['match_candidates']
    report_lines.append("### Match Candidates")
    report_lines.append("")
    report_lines.append(f"- **Total:** {match_candidates['total']:,}")
    report_lines.append(f"- **Needs Review:** {match_candidates['needs_review']:,}")
    report_lines.append(f"- **High Confidence (>=0.8):** {match_candidates['high_confidence']:,}")
    report_lines.append(f"- **Low Confidence (<0.6):** {match_candidates['low_confidence']:,}")
    report_lines.append("")
    
    aliases = detailed_stats['entity_resolution_quality']['aliases']
    report_lines.append("### Aliases")
    report_lines.append("")
    report_lines.append(f"- **Total:** {aliases['total']:,}")
    report_lines.append(f"- **Entities with Only 1 Alias:** {aliases['entities_with_one_alias']:,}")
    report_lines.append(f"- **Average Aliases per Entity:** {aliases['average_aliases_per_entity']:.2f}")
    report_lines.append("")
    
    # Data Quality Issues
    if detailed_stats['data_quality_issues']:
        report_lines.append("## Data Quality Issues")
        report_lines.append("")
        for issue in detailed_stats['data_quality_issues']:
            report_lines.append(f"- ⚠️ {issue}")
        report_lines.append("")
    else:
        report_lines.append("## Data Quality Issues")
        report_lines.append("")
        report_lines.append("✓ No data quality issues detected")
        report_lines.append("")
    
    # Overlap Analysis
    report_lines.append("## Overlap Analysis")
    report_lines.append("")
    overlap = detailed_stats['overlap_analysis']
    if overlap.get('note'):
        report_lines.append(f"*{overlap['note']}*")
    else:
        report_lines.append(f"- **Records Skipped:** {overlap.get('records_skipped', 0):,}")
        report_lines.append(f"- **Records Reprocessed:** {overlap.get('records_reprocessed', 0):,}")
        report_lines.append(f"- **New Records:** {overlap.get('new_records', 0):,}")
    report_lines.append("")
    
    # Top Sources
    report_lines.append("## Top Sources")
    report_lines.append("")
    report_lines.append("### By Entities Created")
    report_lines.append("")
    for i, source in enumerate(basic_stats['top_sources']['by_entities'], 1):
        report_lines.append(f"{i}. **{source['source']}:** {source['entities_created']:,} entities, "
                          f"{source['relationships_created']:,} relationships")
    report_lines.append("")
    
    report_lines.append("### By Relationships Created")
    report_lines.append("")
    for i, source in enumerate(basic_stats['top_sources']['by_relationships'], 1):
        report_lines.append(f"{i}. **{source['source']}:** {source['relationships_created']:,} relationships, "
                          f"{source['entities_created']:,} entities")
    report_lines.append("")
    
    report_lines.append("---")
    report_lines.append("")
    report_lines.append(f"*Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    
    return "\n".join(report_lines)


def save_report(report: str, filename: str):
    """Save report to file."""
    output_path = Path(__file__).parent.parent / filename
    output_path.write_text(report)
    logger.info(f"Report saved to {output_path}")


if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Generate test report')
    parser.add_argument('--test-run-id', type=str, default=None,
                       help='Test run ID')
    parser.add_argument('--phase', choices=['small_sample', 'scale_test'], default='small_sample',
                       help='Test phase')
    parser.add_argument('--output', type=str, default=None,
                       help='Output filename (default: TEST_RESULTS_{phase}.md)')
    
    args = parser.parse_args()
    
    try:
        report = generate_markdown_report(
            test_run_id=args.test_run_id,
            phase=args.phase
        )
        
        filename = args.output or f"TEST_RESULTS_{args.phase.upper()}.md"
        save_report(report, filename)
        
        print(f"\n✓ Report generated: {filename}")
        
    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        sys.exit(1)

