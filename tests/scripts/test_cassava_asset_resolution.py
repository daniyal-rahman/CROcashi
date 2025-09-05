#!/usr/bin/env python3
"""
Test Cassava asset resolution.
"""

import json
import sys
from pathlib import Path

from ncfd.mapping.resolve_service import ResolveService
from ncfd.config import get_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_cassava_asset_resolution():
    """Test asset resolution on Cassava trials."""
    print("🔬 Testing Asset Resolution on Cassava Trials")
    print("=" * 60)
    
    # Configuration for the pipeline
    config = {
        'api_base_url': 'https://clinicaltrials.gov/api/v2',
        'rate_limit_requests_per_minute': 300,
        'timeout_seconds': 45,
        'max_retries': 3,
        'batch_size': 10,
        'max_studies_per_run': 50,  # Small batch for testing
        'default_since_days': 30,
        'save_cursor': False,  # Don't save state for testing
        'change_detection_enabled': True,
        'auto_trigger_signals': False,
        'min_quality_score': 0.7,
        'validation_enabled': True,
        'focus_phases': ['PHASE2', 'PHASE3', 'PHASE2_PHASE3'],
        'focus_intervention_types': ['DRUG', 'BIOLOGICAL'],
        'focus_study_types': ['INTERVENTIONAL'],
        'asset_resolution_enabled': True,
        'create_new_assets': True,
        'min_asset_confidence': 0.7
    }
    
    # Initialize pipeline
    pipeline = CtgovPipeline(config)
    
    # Run limited ingestion
    print("📊 Running CTGov pipeline with asset resolution...")
    since_date = datetime.now(UTC) - timedelta(days=30)
    
    result = pipeline.run_limited_ingestion(
        since_date=since_date.strftime('%Y-%m-%d'),
        max_studies=50,
        phases=['PHASE2', 'PHASE3', 'PHASE2_PHASE3']
    )
    
    print(f"\n📈 Pipeline Results:")
    print(f"   Trials processed: {result.trials_processed}")
    print(f"   New trials: {result.trials_new}")
    print(f"   Updated trials: {result.trials_updated}")
    print(f"   Assets resolved: {result.assets_resolved}")
    print(f"   Assets created: {result.assets_created}")
    print(f"   Trial-asset links: {result.trial_asset_links}")
    
    # Check for Cassava-specific results
    print(f"\n🎯 Checking for Cassava trials...")
    with get_session() as session:
        # Look for Cassava trials
        cassava_trials = session.query(Trial).filter(
            Trial.sponsor_text.ilike('%cassava%')
        ).all()
        
        print(f"   Found {len(cassava_trials)} trials with 'Cassava' in sponsor")
        
        for trial in cassava_trials:
            print(f"   - {trial.nct_id}: {trial.brief_title}")
            
            # Check asset links
            asset_links = session.query(DocumentLink).filter(
                DocumentLink.trial_id == trial.trial_id,
                DocumentLink.asset_id.isnot(None)
            ).all()
            
            if asset_links:
                print(f"     Linked to {len(asset_links)} assets:")
                for link in asset_links:
                    asset = session.query(Asset).filter(
                        Asset.asset_id == link.asset_id
                    ).first()
                    if asset:
                        canonical_name = asset.names_jsonb.get('inn', 'Unknown')
                        print(f"       - Asset {link.asset_id}: {canonical_name} (confidence: {link.confidence:.2f})")
            else:
                print(f"     No asset links found")
        
        # Check for Simufilam/PTI-125 assets
        print(f"\n🔍 Checking for Simufilam/PTI-125 assets...")
        simufilam_aliases = session.query(AssetAlias).filter(
            AssetAlias.alias.ilike('%simufilam%')
        ).all()
        
        pti125_aliases = session.query(AssetAlias).filter(
            AssetAlias.alias.ilike('%pti-125%')
        ).all()
        
        print(f"   Simufilam aliases found: {len(simufilam_aliases)}")
        for alias in simufilam_aliases:
            asset = session.query(Asset).filter(Asset.asset_id == alias.asset_id).first()
            print(f"     - Asset {alias.asset_id}: {alias.alias} (type: {alias.alias_type})")
        
        print(f"   PTI-125 aliases found: {len(pti125_aliases)}")
        for alias in pti125_aliases:
            asset = session.query(Asset).filter(Asset.asset_id == alias.asset_id).first()
            print(f"     - Asset {alias.asset_id}: {alias.alias} (type: {alias.alias_type})")
        
        # Check all assets (since we don't have created_at in the table)
        print(f"\n📋 All assets in database:")
        all_assets = session.query(Asset).all()
        
        for asset in all_assets:
            canonical_name = asset.names_jsonb.get('inn', 'Unknown')
            aliases = session.query(AssetAlias).filter(
                AssetAlias.asset_id == asset.asset_id
            ).all()
            print(f"   - Asset {asset.asset_id}: {canonical_name}")
            print(f"     Aliases: {[a.alias for a in aliases]}")
    
    print(f"\n✅ Asset resolution test completed!")


if __name__ == "__main__":
    test_cassava_asset_resolution()
