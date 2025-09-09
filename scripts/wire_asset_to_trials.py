#!/usr/bin/env python3
import argparse
import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Dict

from ncfd.db.session import get_session
from ncfd.db.models import Asset, Document, DocumentLink, Trial
from ncfd.mapping.normalize import norm_name


def get_or_create_asset(session, asset_name: str, synonyms: Optional[List[str]] = None) -> Asset:
    synonyms = synonyms or []
    # naive lookup in names_jsonb by inn or synonyms match
    existing = (
        session.query(Asset)
        .filter(Asset.names_jsonb["inn"].astext == asset_name)
        .one_or_none()
    )
    if existing:
        return existing
    names_jsonb: Dict[str, object] = {
        "inn": asset_name,
        "synonyms": synonyms,
        "internal_codes": [],
    }
    asset = Asset(names_jsonb=names_jsonb)
    session.add(asset)
    session.flush()
    return asset


def get_or_create_registry_document(session, nct_id: str, title: Optional[str]) -> Document:
    doc = (
        session.query(Document)
        .filter(Document.nct_id == nct_id, Document.source_type == "Registry")
        .one_or_none()
    )
    if doc:
        return doc
    doc = Document(
        source_type="Registry",
        source_url=f"https://clinicaltrials.gov/study/{nct_id}",
        url_hash=hashlib.sha256(f"ctgov:{nct_id}".encode("utf-8")).hexdigest(),
        discovered_at=datetime.now(UTC),
        content_type="registry",
        title=title,
        nct_id=nct_id,
        status="discovered",
        publisher="ClinicalTrials.gov",
    )
    session.add(doc)
    session.flush()
    return doc


def ensure_link(session, doc_id: int, nct_id: str, trial_id: Optional[int], asset_id: int):
    # Upsert-like: check if a link already exists
    exists = (
        session.query(DocumentLink)
        .filter(
            DocumentLink.doc_id == doc_id,
            DocumentLink.nct_id == nct_id,
            DocumentLink.trial_id == trial_id,
            DocumentLink.asset_id == asset_id,
        )
        .one_or_none()
    )
    if exists:
        return exists
    link = DocumentLink(
        doc_id=doc_id,
        nct_id=nct_id,
        trial_id=trial_id,
        asset_id=asset_id,
        company_id=None,
        link_type="asset_mapping",
        confidence=None,
        heuristics=None,
        evidence_json=None,
    )
    session.add(link)
    session.flush()
    return link


def main():
    parser = argparse.ArgumentParser(description="Wire an asset to trials by NCT IDs")
    parser.add_argument("--asset", required=True, help="Asset/Drug name (e.g., simufilam)")
    parser.add_argument("--synonym", action="append", default=[], help="Add synonym (e.g., PTI-125)")
    parser.add_argument("--nct", nargs="+", required=True, help="One or more NCT IDs")

    args = parser.parse_args()

    with get_session() as session:
        asset = get_or_create_asset(session, args.asset, args.synonym)
        wired = 0
        for nct_id in args.nct:
            trial = session.query(Trial).filter(Trial.nct_id == nct_id).one_or_none()
            doc = get_or_create_registry_document(session, nct_id, title=trial.brief_title if trial else None)
            ensure_link(session, doc_id=doc.doc_id, nct_id=nct_id, trial_id=trial.trial_id if trial else None, asset_id=asset.asset_id)
            wired += 1
        session.commit()
        print(f"Wired asset '{args.asset}' to {wired} trial(s)")


if __name__ == "__main__":
    main()
