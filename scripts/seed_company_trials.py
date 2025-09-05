#!/usr/bin/env python3
import argparse
import hashlib
from datetime import datetime, UTC
from typing import List, Optional

from ncfd.db.session import get_session
from ncfd.db.models import Company, Trial, Document, DocumentCitation, DocumentLink
from ncfd.mapping.normalize import norm_name


def compute_trial_hash(nct_id: str, sponsor_text: Optional[str], brief_title: Optional[str]) -> str:
    payload = f"{nct_id}\n{sponsor_text or ''}\n{brief_title or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_or_create_company(session, company_name: str) -> Company:
    name_norm = norm_name(company_name)
    company = (
        session.query(Company)
        .filter(Company.name_norm == name_norm)
        .one_or_none()
    )
    if company:
        return company
    company = Company(name=company_name, name_norm=name_norm)
    session.add(company)
    session.flush()
    return company


def get_or_create_trial(
    session,
    nct_id: str,
    sponsor_text: str,
    company_id: Optional[int],
    brief_title: Optional[str] = None,
    phase: Optional[str] = None,
    indication: Optional[str] = None,
) -> Trial:
    trial = (
        session.query(Trial)
        .filter(Trial.nct_id == nct_id)
        .one_or_none()
    )
    if trial:
        return trial
    trial_hash = compute_trial_hash(nct_id, sponsor_text, brief_title)
    trial = Trial(
        nct_id=nct_id,
        brief_title=brief_title,
        official_title=brief_title,
        sponsor_text=sponsor_text,
        sponsor_company_id=company_id,
        phase=phase,
        indication=indication,
        has_results=False,
        last_seen_at=datetime.now(UTC),
        current_sha256=trial_hash,
    )
    session.add(trial)
    session.flush()
    return trial


def get_or_create_registry_document(
    session,
    nct_id: str,
    title: Optional[str],
    sponsor_text: Optional[str],
) -> Document:
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
        published_at=None,
        content_type="registry",
        title=title,
        doi=None,
        pmid=None,
        pmcid=None,
        nct_id=nct_id,
        sponsor_text=sponsor_text,
        status="discovered",
        sha256=None,
        publisher="ClinicalTrials.gov",
    )
    session.add(doc)
    session.flush()

    # Citation row (optional, holds nct_id)
    citation = DocumentCitation(
        doc_id=doc.doc_id,
        doi=None,
        pmid=None,
        pmcid=None,
        nct_id=nct_id,
    )
    session.add(citation)
    session.flush()

    return doc


def link_document_to_entities(
    session,
    doc_id: int,
    nct_id: str,
    trial_id: Optional[int],
    company_id: Optional[int],
):
    link = DocumentLink(
        doc_id=doc_id,
        nct_id=nct_id,
        trial_id=trial_id,
        asset_id=None,
        company_id=company_id,
        link_type="registry_entry",
        confidence=None,
        heuristics=None,
        evidence_json=None,
    )
    session.add(link)
    session.flush()


def main():
    parser = argparse.ArgumentParser(description="Seed a few trials for a company into the DB")
    parser.add_argument("--company", required=True, help="Company name (e.g., Cassava Sciences)")
    parser.add_argument("--sponsor-text", required=False, help="Sponsor text to store on trials; defaults to company name")
    parser.add_argument("--nct", nargs="+", required=True, help="One or more NCT IDs")
    parser.add_argument("--title", nargs="+", required=False, help="Optional titles matching NCT order")
    parser.add_argument("--phase", default=None, help="Optional shared phase string (e.g., P2, P3)")
    parser.add_argument("--indication", default=None, help="Optional shared indication")

    args = parser.parse_args()

    titles: List[Optional[str]] = []
    if args.title and len(args.title) == len(args.nct):
        titles = args.title
    else:
        titles = [None] * len(args.nct)

    sponsor_text = args.sponsor_text or args.company

    with get_session() as session:
        company = get_or_create_company(session, args.company)
        for idx, nct_id in enumerate(args.nct):
            title = titles[idx]
            trial = get_or_create_trial(
                session,
                nct_id=nct_id,
                sponsor_text=sponsor_text,
                company_id=company.company_id,
                brief_title=title,
                phase=args.phase,
                indication=args.indication,
            )
            doc = get_or_create_registry_document(
                session,
                nct_id=nct_id,
                title=title,
                sponsor_text=sponsor_text,
            )
            link_document_to_entities(
                session,
                doc_id=doc.doc_id,
                nct_id=nct_id,
                trial_id=trial.trial_id,
                company_id=company.company_id,
            )
        session.commit()
        print(f"Seeded {len(args.nct)} trial(s) for company '{args.company}'")


if __name__ == "__main__":
    main()
