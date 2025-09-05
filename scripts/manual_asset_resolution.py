#!/usr/bin/env python3
"""
Manual asset resolution tool.
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


def manual_asset_resolution():
    """Manually trigger asset resolution for existing trials."""
    print("🔧 Manual Asset Resolution for Existing Trials")
    print("=" * 60)
    
    resolver = AssetResolver()
    
    with get_session() as session:
        # Get Cassava trials
        cassava_trials = session.query(Trial).filter(
            Trial.sponsor_text.ilike('%cassava%')
        ).all()
        
        print(f"Found {len(cassava_trials)} Cassava trials")
        
        for trial in cassava_trials:
            print(f"\n🎯 Processing trial: {trial.nct_id}")
            
            # Get fresh trial data from CTGov API
            url = f"https://clinicaltrials.gov/api/v2/studies/{trial.nct_id}"
            response = requests.get(url, headers={"Accept": "application/json"})
            trial_data = response.json()
            
            # Extract drug names
            drug_names = resolver.extract_drug_names(trial_data)
            print(f"  Drug names found: {len(drug_names)}")
            
            for drug in drug_names:
                print(f"    - {drug.original} -> {drug.normalized} (confidence: {drug.confidence})")
            
            if drug_names:
                # Resolve assets
                asset_matches = resolver.resolve_assets(
                    session, drug_names, trial.sponsor_company_id
                )
                print(f"  Asset matches: {len(asset_matches)}")
                
                # Create new assets if needed
                for drug_name in drug_names:
                    if drug_name.confidence >= 0.8:
                        new_asset_id = resolver.create_asset_if_needed(session, drug_name)
                        if new_asset_id:
                            print(f"    Created new asset {new_asset_id} for '{drug_name.original}'")
                            
                            # Add to matches if not already matched
                            if not any(match.asset_id == new_asset_id for match in asset_matches):
                                from ncfd.pipeline.asset_resolver import AssetMatch
                                asset_matches.append(AssetMatch(
                                    asset_id=new_asset_id,
                                    confidence=drug_name.confidence * 0.9,
                                    match_type='new_asset',
                                    matched_alias=drug_name.normalized,
                                    heuristics={'method': 'new_asset_creation'}
                                ))
                
                # Link trial to assets
                if asset_matches:
                    resolver.link_trial_to_assets(
                        session, trial.trial_id, trial.nct_id, asset_matches
                    )
                    print(f"  Linked to {len(asset_matches)} assets")
                else:
                    print(f"  No assets to link")
            
            session.commit()
        
        # Check results
        print(f"\n📊 Results Summary:")
        
        # Check for Simufilam/PTI-125 assets
        simufilam_aliases = session.query(AssetAlias).filter(
            AssetAlias.alias.ilike('%simufilam%')
        ).all()
        
        pti125_aliases = session.query(AssetAlias).filter(
            AssetAlias.alias.ilike('%pti-125%')
        ).all()
        
        print(f"  Simufilam aliases: {len(simufilam_aliases)}")
        for alias in simufilam_aliases:
            print(f"    - Asset {alias.asset_id}: {alias.alias}")
        
        print(f"  PTI-125 aliases: {len(pti125_aliases)}")
        for alias in pti125_aliases:
            print(f"    - Asset {alias.asset_id}: {alias.alias}")
        
        # Check trial-asset links
        for trial in cassava_trials:
            asset_links = session.query(DocumentLink).filter(
                DocumentLink.trial_id == trial.trial_id,
                DocumentLink.asset_id.isnot(None)
            ).all()
            
            print(f"  Trial {trial.nct_id} asset links: {len(asset_links)}")
            for link in asset_links:
                asset = session.query(Asset).filter(Asset.asset_id == link.asset_id).first()
                if asset:
                    canonical_name = asset.names_jsonb.get('inn', 'Unknown')
                    print(f"    - Asset {link.asset_id}: {canonical_name}")

if __name__ == "__main__":
    manual_asset_resolution()
