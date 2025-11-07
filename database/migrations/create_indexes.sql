-- Comprehensive indexes for biotech knowledge graph database
-- These indexes are created automatically via Alembic, but can be run manually if needed

-- Company indexes
CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(status);
CREATE INDEX IF NOT EXISTS idx_companies_ticker ON companies(ticker);
CREATE INDEX IF NOT EXISTS idx_companies_parent ON companies(current_parent_id);
CREATE INDEX IF NOT EXISTS idx_companies_ultimate_parent ON companies(ultimate_parent_id);
CREATE INDEX IF NOT EXISTS idx_companies_is_public ON companies(is_public);
CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_name_unique ON companies(LOWER(name));

-- Drug indexes
CREATE INDEX IF NOT EXISTS idx_drugs_chembl ON drugs(chembl_id);
CREATE INDEX IF NOT EXISTS idx_drugs_drugbank ON drugs(drugbank_id);
CREATE INDEX IF NOT EXISTS idx_drugs_pubchem ON drugs(pubchem_cid);
CREATE INDEX IF NOT EXISTS idx_drugs_inchi_key ON drugs(inchi_key);
CREATE INDEX IF NOT EXISTS idx_drugs_cas_number ON drugs(cas_number);
CREATE INDEX IF NOT EXISTS idx_drugs_unii_code ON drugs(unii_code);
CREATE INDEX IF NOT EXISTS idx_drugs_generic_name ON drugs(generic_name);
CREATE INDEX IF NOT EXISTS idx_drugs_code_name ON drugs(code_name);
CREATE INDEX IF NOT EXISTS idx_drugs_drug_type ON drugs(drug_type);

-- Drug names indexes
CREATE INDEX IF NOT EXISTS idx_drug_names_drug_id ON drug_names(drug_id);
CREATE INDEX IF NOT EXISTS idx_drug_names_text ON drug_names(name_text);
CREATE INDEX IF NOT EXISTS idx_drug_names_type ON drug_names(name_type);
CREATE INDEX IF NOT EXISTS idx_drug_names_company ON drug_names(used_by_company_id);
CREATE INDEX IF NOT EXISTS idx_drug_names_valid_dates ON drug_names(valid_from, valid_until);

-- Drug chemical identity indexes
CREATE INDEX IF NOT EXISTS idx_drug_chemical_inchi_key ON drug_chemical_identity(inchi_key);
CREATE INDEX IF NOT EXISTS idx_drug_chemical_sequence_hash ON drug_chemical_identity(sequence_hash);

-- Clinical trial indexes
CREATE INDEX IF NOT EXISTS idx_trials_nct ON clinical_trials(nct_id);
CREATE INDEX IF NOT EXISTS idx_trials_status ON clinical_trials(status);
CREATE INDEX IF NOT EXISTS idx_trials_phase ON clinical_trials(phase_numeric);
CREATE INDEX IF NOT EXISTS idx_trials_study_type ON clinical_trials(study_type);
CREATE INDEX IF NOT EXISTS idx_trials_sponsor_type ON clinical_trials(sponsor_type);
CREATE INDEX IF NOT EXISTS idx_trials_start_date ON clinical_trials(start_date);
CREATE INDEX IF NOT EXISTS idx_trials_completion_date ON clinical_trials(completion_date);
CREATE INDEX IF NOT EXISTS idx_trials_results_posted ON clinical_trials(results_posted);

-- Publication indexes
CREATE INDEX IF NOT EXISTS idx_publications_pmid ON publications(pmid);
CREATE INDEX IF NOT EXISTS idx_publications_pmcid ON publications(pmcid);
CREATE INDEX IF NOT EXISTS idx_publications_doi ON publications(doi);
CREATE INDEX IF NOT EXISTS idx_publications_date ON publications(publication_date);
CREATE INDEX IF NOT EXISTS idx_publications_journal ON publications(journal);
CREATE INDEX IF NOT EXISTS idx_publications_type ON publications(publication_type);
CREATE INDEX IF NOT EXISTS idx_publications_trial_result ON publications(is_clinical_trial_result);

-- Patent indexes
CREATE INDEX IF NOT EXISTS idx_patents_number ON patents(patent_number);
CREATE INDEX IF NOT EXISTS idx_patents_office ON patents(patent_office);
CREATE INDEX IF NOT EXISTS idx_patents_status ON patents(status);
CREATE INDEX IF NOT EXISTS idx_patents_filing_date ON patents(filing_date);
CREATE INDEX IF NOT EXISTS idx_patents_grant_date ON patents(grant_date);
CREATE INDEX IF NOT EXISTS idx_patents_expiration_date ON patents(expiration_date);

-- Disease indexes
CREATE INDEX IF NOT EXISTS idx_diseases_parent ON diseases(parent_disease_id);
CREATE INDEX IF NOT EXISTS idx_diseases_icd10 ON diseases(icd10_code);
CREATE INDEX IF NOT EXISTS idx_diseases_mesh ON diseases(mesh_id);
CREATE INDEX IF NOT EXISTS idx_diseases_snomed ON diseases(snomed_code);
CREATE INDEX IF NOT EXISTS idx_diseases_rare ON diseases(is_rare_disease);
CREATE INDEX IF NOT EXISTS idx_diseases_orphan ON diseases(is_orphan_designation_eligible);

-- Regulatory event indexes
CREATE INDEX IF NOT EXISTS idx_regulatory_events_type ON regulatory_events(event_type);
CREATE INDEX IF NOT EXISTS idx_regulatory_events_date ON regulatory_events(event_date);
CREATE INDEX IF NOT EXISTS idx_regulatory_events_body ON regulatory_events(regulatory_body);
CREATE INDEX IF NOT EXISTS idx_regulatory_events_country ON regulatory_events(country);

-- Entity alias indexes (critical for entity resolution)
CREATE INDEX IF NOT EXISTS idx_entity_aliases_type_text ON entity_aliases(entity_type, alias_text);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_type ON entity_aliases(entity_type);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_text_gin ON entity_aliases USING gin(alias_text gin_trgm_ops);

-- Entity match indexes
CREATE INDEX IF NOT EXISTS idx_entity_matches_type ON entity_matches(entity_type);
CREATE INDEX IF NOT EXISTS idx_entity_matches_entity ON entity_matches(matched_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_matches_verified ON entity_matches(verified);
CREATE INDEX IF NOT EXISTS idx_entity_matches_method ON entity_matches(match_method);

-- Relationship table indexes
CREATE INDEX IF NOT EXISTS idx_company_drugs_company ON company_drugs(company_id);
CREATE INDEX IF NOT EXISTS idx_company_drugs_drug ON company_drugs(drug_id);
CREATE INDEX IF NOT EXISTS idx_company_drugs_stage ON company_drugs(development_stage);
CREATE INDEX IF NOT EXISTS idx_company_drugs_dates ON company_drugs(start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_trial_sponsors_trial ON trial_sponsors(trial_id);
CREATE INDEX IF NOT EXISTS idx_trial_sponsors_entity ON trial_sponsors(entity_id);
CREATE INDEX IF NOT EXISTS idx_trial_sponsors_type ON trial_sponsors(entity_type);
CREATE INDEX IF NOT EXISTS idx_trial_sponsors_role ON trial_sponsors(sponsor_role);

CREATE INDEX IF NOT EXISTS idx_trial_drugs_trial ON trial_drugs(trial_id);
CREATE INDEX IF NOT EXISTS idx_trial_drugs_drug ON trial_drugs(drug_id);

CREATE INDEX IF NOT EXISTS idx_trial_diseases_trial ON trial_diseases(trial_id);
CREATE INDEX IF NOT EXISTS idx_trial_diseases_disease ON trial_diseases(disease_id);

CREATE INDEX IF NOT EXISTS idx_publication_drugs_pub ON publication_drugs(pub_id);
CREATE INDEX IF NOT EXISTS idx_publication_drugs_drug ON publication_drugs(drug_id);

CREATE INDEX IF NOT EXISTS idx_publication_trials_pub ON publication_trials(pub_id);
CREATE INDEX IF NOT EXISTS idx_publication_trials_trial ON publication_trials(trial_id);

CREATE INDEX IF NOT EXISTS idx_drug_indications_drug ON drug_indications(drug_id);
CREATE INDEX IF NOT EXISTS idx_drug_indications_disease ON drug_indications(disease_id);
CREATE INDEX IF NOT EXISTS idx_drug_indications_approved ON drug_indications(approved);
CREATE INDEX IF NOT EXISTS idx_drug_indications_phase ON drug_indications(development_phase);

CREATE INDEX IF NOT EXISTS idx_drug_targets_drug ON drug_targets(drug_id);
CREATE INDEX IF NOT EXISTS idx_drug_targets_target ON drug_targets(target_id);

CREATE INDEX IF NOT EXISTS idx_company_ownership_company ON company_ownership_history(company_id);
CREATE INDEX IF NOT EXISTS idx_company_ownership_parent ON company_ownership_history(parent_company_id);
CREATE INDEX IF NOT EXISTS idx_company_ownership_dates ON company_ownership_history(effective_start_date, effective_end_date);

-- Staging table indexes
CREATE INDEX IF NOT EXISTS idx_staging_source ON staging_raw_data(source_system);
CREATE INDEX IF NOT EXISTS idx_staging_record_id ON staging_raw_data(source_record_id);
CREATE INDEX IF NOT EXISTS idx_staging_processed ON staging_raw_data(processed);
CREATE INDEX IF NOT EXISTS idx_staging_ingested ON staging_raw_data(ingested_at);

-- GIN indexes for JSONB fields (full-text search)
CREATE INDEX IF NOT EXISTS idx_companies_data_sources_gin ON companies USING gin(data_sources);
CREATE INDEX IF NOT EXISTS idx_drugs_data_sources_gin ON drugs USING gin(data_sources);
CREATE INDEX IF NOT EXISTS idx_trials_data_sources_gin ON clinical_trials USING gin(data_sources);
CREATE INDEX IF NOT EXISTS idx_publications_data_sources_gin ON publications USING gin(data_sources);
CREATE INDEX IF NOT EXISTS idx_staging_raw_data_gin ON staging_raw_data USING gin(raw_data);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_trials_status_phase ON clinical_trials(status, phase_numeric);
CREATE INDEX IF NOT EXISTS idx_company_drugs_company_stage ON company_drugs(company_id, development_stage);
CREATE INDEX IF NOT EXISTS idx_drug_indications_drug_approved ON drug_indications(drug_id, approved);

