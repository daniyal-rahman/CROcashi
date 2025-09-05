#!/usr/bin/env python3
"""
Load company aliases into the database.
"""

import json
import sys
from pathlib import Path

from ncfd.mapping.persist import CompanyAliasPersister
from ncfd.config import get_config


def load_aliases_file(file_path: str) -> Dict[str, Any]:
    """Load aliases from JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def find_company_by_name(session, company_name: str) -> int:
    """Find company ID by name (case-insensitive)."""
    result = session.execute(
        text("SELECT company_id FROM companies WHERE UPPER(name) = UPPER(:name)"),
        {"name": company_name}
    ).fetchone()
    
    if result:
        return result[0]
    
    # Try partial match
    result = session.execute(
        text("SELECT company_id FROM companies WHERE UPPER(name) LIKE UPPER(:name)"),
        {"name": f"%{company_name}%"}
    ).fetchone()
    
    return result[0] if result else None


def normalize_alias(alias: str) -> str:
    """Normalize alias for database storage."""
    # Convert to lowercase and remove extra spaces
    normalized = " ".join(alias.lower().split())
    return normalized


def load_aliases_to_database(aliases_data: Dict[str, Any]) -> Dict[str, Any]:
    """Load aliases into the database."""
    logger = get_logger(__name__)
    logger.info("Loading company aliases to database...")
    
    reset_engine()
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    
    stats = {
        "total_companies": 0,
        "companies_found": 0,
        "companies_not_found": 0,
        "total_aliases": 0,
        "aliases_loaded": 0,
        "aliases_skipped": 0,
        "errors": []
    }
    
    with session_scope(db_url) as session:
        for company_data in aliases_data.get("company_aliases", []):
            company_name = company_data["company_name"]
            aliases = company_data["aliases"]
            
            stats["total_companies"] += 1
            logger.info(f"Processing company: {company_name}")
            
            # Find company in database
            company_id = find_company_by_name(session, company_name)
            
            if not company_id:
                logger.warning(f"Company not found: {company_name}")
                stats["companies_not_found"] += 1
                stats["errors"].append(f"Company not found: {company_name}")
                continue
            
            stats["companies_found"] += 1
            logger.info(f"Found company ID: {company_id}")
            
            # Load aliases
            for alias in aliases:
                stats["total_aliases"] += 1
                
                try:
                    # Check if alias already exists
                    existing = session.execute(
                        text("SELECT alias_id FROM company_aliases WHERE company_id = :company_id AND alias_norm = :alias_norm"),
                        {
                            "company_id": company_id,
                            "alias_norm": normalize_alias(alias)
                        }
                    ).fetchone()
                    
                    if existing:
                        logger.debug(f"Alias already exists: {alias}")
                        stats["aliases_skipped"] += 1
                        continue
                    
                    # Insert new alias
                    session.execute(
                        text("""
                            INSERT INTO company_aliases (company_id, alias, alias_norm, alias_type, source)
                            VALUES (:company_id, :alias, :alias_norm, :alias_type, :source)
                        """),
                        {
                            "company_id": company_id,
                            "alias": alias,
                            "alias_norm": normalize_alias(alias),
                            "alias_type": "legal",
                            "source": "manual_seed"
                        }
                    )
                    
                    stats["aliases_loaded"] += 1
                    logger.debug(f"Loaded alias: {alias}")
                    
                except Exception as e:
                    logger.error(f"Error loading alias '{alias}' for company {company_name}: {e}")
                    stats["errors"].append(f"Error loading alias '{alias}' for company {company_name}: {e}")
        
        # Commit all changes
        session.commit()
    
    return stats


def main():
    """Main entry point."""
    setup_logging()
    logger = get_logger(__name__)
    
    # File path
    aliases_file = Path("data/company_aliases_seed.json")
    
    if not aliases_file.exists():
        logger.error(f"Aliases file not found: {aliases_file}")
        print(f"❌ Aliases file not found: {aliases_file}")
        return 1
    
    try:
        # Load aliases from file
        logger.info(f"Loading aliases from: {aliases_file}")
        aliases_data = load_aliases_file(str(aliases_file))
        
        # Load to database
        stats = load_aliases_to_database(aliases_data)
        
        # Print results
        print(f"\n📊 Company Aliases Loading Results:")
        print(f"  Total companies in file: {stats['total_companies']}")
        print(f"  Companies found in DB: {stats['companies_found']}")
        print(f"  Companies not found: {stats['companies_not_found']}")
        print(f"  Total aliases in file: {stats['total_aliases']}")
        print(f"  Aliases loaded: {stats['aliases_loaded']}")
        print(f"  Aliases skipped (existing): {stats['aliases_skipped']}")
        
        if stats["errors"]:
            print(f"\n❌ Errors ({len(stats['errors'])}):")
            for error in stats["errors"][:5]:  # Show first 5 errors
                print(f"  - {error}")
            if len(stats["errors"]) > 5:
                print(f"  ... and {len(stats['errors']) - 5} more errors")
        
        # Show metadata
        metadata = aliases_data.get("metadata", {})
        print(f"\n📋 File Metadata:")
        print(f"  Description: {metadata.get('description', 'N/A')}")
        print(f"  Created: {metadata.get('created_date', 'N/A')}")
        print(f"  Source: {metadata.get('source', 'N/A')}")
        
        if stats["companies_found"] > 0:
            print(f"\n✅ Successfully loaded {stats['aliases_loaded']} aliases for {stats['companies_found']} companies")
        else:
            print(f"\n❌ No companies found in database")
        
    except Exception as e:
        logger.error(f"Failed to load aliases: {e}")
        print(f"❌ Failed to load aliases: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
