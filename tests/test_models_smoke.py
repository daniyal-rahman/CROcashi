"""
Smoke tests for database models.

These tests verify that the database models can be imported and instantiated
without requiring a database connection.
"""

import pytest
from datetime import datetime
from ncfd.db.models import (
    Asset, AssetAlias, Document, DocumentTextPage, DocumentTable,
    DocumentLink, DocumentEntity, DocumentCitation, DocumentNote
)


class TestModelsSmoke:
    """Test that models can be instantiated correctly."""
    
    def test_asset_model(self):
        """Test Asset model instantiation."""
        asset = Asset(
            names_jsonb={"inn": "test_drug"},
            modality="small_molecule",
            target="receptor",
            moa="inhibitor"
        )
        
        assert asset.names_jsonb == {"inn": "test_drug"}
        assert asset.modality == "small_molecule"
        assert asset.target == "receptor"
        assert asset.moa == "inhibitor"
        assert asset.asset_id is None  # Not yet persisted
    
    def test_asset_alias_model(self):
        """Test AssetAlias model instantiation."""
        alias = AssetAlias(
            asset_id=1,  # Mock ID
            alias="AB-123",
            alias_norm="AB-123",
            alias_type="code",
            source="test"
        )
        
        assert alias.alias == "AB-123"
        assert alias.alias_norm == "AB-123"
        assert alias.alias_type == "code"
        assert alias.source == "test"
        assert alias.asset_alias_id is None  # Not yet persisted
    
    def test_document_model(self):
        """Test Document model instantiation."""
        doc = Document(
            source_type="PR",
            source_url="https://example.com/news",
            publisher="Test Company",
            storage_uri="file:///tmp/test",
            sha256="a" * 64,
            status="discovered"
        )
        
        assert doc.source_type == "PR"
        assert doc.source_url == "https://example.com/news"
        assert doc.publisher == "Test Company"
        assert doc.storage_uri == "file:///tmp/test"
        assert doc.sha256 == "a" * 64
        assert doc.status == "discovered"
        assert doc.doc_id is None  # Not yet persisted
    
    def test_document_text_page_model(self):
        """Test DocumentTextPage model instantiation."""
        text_page = DocumentTextPage(
            doc_id=1,  # Mock ID
            page_no=1,
            char_count=1000,
            text="This is test content for page 1."
        )
        
        assert text_page.doc_id == 1
        assert text_page.page_no == 1
        assert text_page.char_count == 1000
        assert text_page.text == "This is test content for page 1."
    
    def test_document_table_model(self):
        """Test DocumentTable model instantiation."""
        table_data = {
            "rows": [["Header 1", "Header 2"], ["Data 1", "Data 2"]],
            "row_count": 2,
            "col_count": 2
        }
        
        table = DocumentTable(
            doc_id=1,  # Mock ID
            page_no=1,
            table_idx=0,
            table_jsonb=table_data,
            detector="beautifulsoup"
        )
        
        assert table.doc_id == 1
        assert table.page_no == 1
        assert table.table_idx == 0
        assert table.table_jsonb == table_data
        assert table.detector == "beautifulsoup"
    
    def test_document_link_model(self):
        """Test DocumentLink model instantiation."""
        link = DocumentLink(
            doc_id=1,  # Mock ID
            nct_id="NCT12345678",
            asset_id=1,  # Mock ID
            company_id=1,  # Mock ID
            link_type="nct_near_asset",
            confidence=1.0
        )
        
        assert link.doc_id == 1
        assert link.nct_id == "NCT12345678"
        assert link.asset_id == 1
        assert link.company_id == 1
        assert link.link_type == "nct_near_asset"
        assert link.confidence == 1.0
    
    def test_document_entity_model(self):
        """Test DocumentEntity model instantiation."""
        entity = DocumentEntity(
            doc_id=1,  # Mock ID
            ent_type="code",
            value_text="AB-123",
            value_norm="AB-123",
            page_no=1,
            char_start=100,
            char_end=106,
            detector="regex"
        )
        
        assert entity.doc_id == 1
        assert entity.ent_type == "code"
        assert entity.value_text == "AB-123"
        assert entity.value_norm == "AB-123"
        assert entity.page_no == 1
        assert entity.char_start == 100
        assert entity.char_end == 106
        assert entity.detector == "regex"
    
    def test_document_citation_model(self):
        """Test DocumentCitation model instantiation."""
        citation = DocumentCitation(
            doc_id=1,  # Mock ID
            doi="10.1000/12345",
            pmid="12345678",
            pmcid="PMC12345"
        )
        
        assert citation.doc_id == 1
        assert citation.doi == "10.1000/12345"
        assert citation.pmid == "12345678"
        assert citation.pmcid == "PMC12345"
    
    def test_document_note_model(self):
        """Test DocumentNote model instantiation."""
        note = DocumentNote(
            doc_id=1,  # Mock ID
            notes_md="# Test Note\nThis is a test note.",
            author="Test User"
        )
        
        assert note.doc_id == 1
        assert note.notes_md == "# Test Note\nThis is a test note."
        assert note.author == "Test User"
    
    def test_model_relationships(self):
        """Test that model relationships are properly defined."""
        # This test just verifies that the models can be imported
        # and that their relationship attributes exist
        
        # Asset relationships
        assert hasattr(Asset, 'aliases')
        assert hasattr(Asset, 'document_links')
        
        # Document relationships
        assert hasattr(Document, 'text_pages')
        assert hasattr(Document, 'tables')
        assert hasattr(Document, 'links')
        assert hasattr(Document, 'entities')
        assert hasattr(Document, 'citations')
        assert hasattr(Document, 'notes')
        
        # AssetAlias relationships
        assert hasattr(AssetAlias, 'asset')
        
        # DocumentLink relationships
        assert hasattr(DocumentLink, 'document')
        assert hasattr(DocumentLink, 'asset')
        assert hasattr(DocumentLink, 'company')
        
        # DocumentEntity relationships
        assert hasattr(DocumentEntity, 'document')
        
        # DocumentCitation relationships
        assert hasattr(DocumentCitation, 'document')
        
        # DocumentNote relationships
        assert hasattr(DocumentNote, 'document')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
