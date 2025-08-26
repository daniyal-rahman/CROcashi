"""add_research_government_filtering_patterns

Revision ID: 81c4a47ab949
Revises: f5b03315b2de
Create Date: 2025-08-26 06:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '81c4a47ab949'
down_revision: Union[str, Sequence[str], None] = 'f5b03315b2de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add comprehensive research/government filtering patterns."""
    
    # Insert all the research/government organization filtering patterns
    # Use ON CONFLICT DO NOTHING to handle cases where patterns already exist
    op.execute("""
        INSERT INTO resolver_ignore_sponsor (pattern, note) VALUES
        -- NIH and its institutes (exact matches)
        ('^NIH$', 'National Institutes of Health'),
        ('^NCI$', 'National Cancer Institute'),
        ('^NIAID$', 'National Institute of Allergy and Infectious Diseases'),
        ('^NIMH$', 'National Institute of Mental Health'),
        ('^NINDS$', 'National Institute of Neurological Disorders and Stroke'),
        ('^NHLBI$', 'National Heart, Lung, and Blood Institute'),
        ('^NIDDK$', 'National Institute of Diabetes and Digestive and Kidney Diseases'),
        ('^NIEHS$', 'National Institute of Environmental Health Sciences'),
        ('^NIGMS$', 'National Institute of General Medical Sciences'),
        ('^NICHD$', 'National Institute of Child Health and Human Development'),
        ('^NIDA$', 'National Institute on Drug Abuse'),
        ('^NIAAA$', 'National Institute on Alcohol Abuse and Alcoholism'),
        ('^NIDCR$', 'National Institute of Dental and Craniofacial Research'),
        ('^NIBIB$', 'National Institute of Biomedical Imaging and Bioengineering'),
        ('^NCCIH$', 'National Center for Complementary and Integrative Health'),
        ('^NLM$', 'National Library of Medicine'),
        ('^FIC$', 'Fogarty International Center'),
        ('^NCATS$', 'National Center for Advancing Translational Sciences'),
        ('^OD$', 'Office of the Director'),
        ('^ORWH$', 'Office of Research on Women''s Health'),
        
        -- Other government agencies
        ('^CDC$', 'Centers for Disease Control and Prevention'),
        ('^FDA$', 'Food and Drug Administration'),
        ('^VA$', 'Department of Veterans Affairs'),
        ('^DOD$', 'Department of Defense'),
        ('^NSF$', 'National Science Foundation'),
        ('^NASA$', 'National Aeronautics and Space Administration'),
        ('^DOE$', 'Department of Energy'),
        ('^USDA$', 'United States Department of Agriculture'),
        ('^EPA$', 'Environmental Protection Agency'),
        
        -- Pattern-based matches for research organizations
        ('Center', 'Contains Center'),
        ('Hospital', 'Contains Hospital'),
        ('Institute', 'Contains Institute'),
        ('University', 'Contains University'),
        ('Foundation', 'Contains Foundation'),
        ('Clinic', 'Contains Clinic'),
        ('Medical', 'Contains Medical'),
        ('Research', 'Contains Research'),
        ('Cancer', 'Contains Cancer'),
        ('National', 'Contains National'),
        
        -- Academic and educational patterns
        ('College', 'Contains College'),
        ('Academy', 'Contains Academy'),
        ('School', 'Contains School'),
        ('Laboratory', 'Contains Laboratory'),
        ('Lab', 'Contains Lab'),
        ('Department', 'Contains Department'),
        ('Division', 'Contains Division'),
        ('Program', 'Contains Program'),
        
        -- Government and administrative patterns
        ('Government', 'Contains Government'),
        ('Public', 'Contains Public'),
        ('State', 'Contains State'),
        ('Federal', 'Contains Federal'),
        ('Ministry', 'Contains Ministry'),
        ('Authority', 'Contains Authority'),
        ('Agency', 'Contains Agency'),
        ('Bureau', 'Contains Bureau'),
        ('Office', 'Contains Office'),
        ('Service', 'Contains Service'),
        
        -- International and regional patterns
        ('International', 'Contains International'),
        ('European', 'Contains European'),
        ('Regional', 'Contains Regional'),
        ('Local', 'Contains Local'),
        
        -- Legacy regex patterns (more specific)
        ('^NIH.*Institute', 'NIH Institute pattern'),
        ('^National.*Institute', 'National Institute pattern'),
        ('^University.*', 'University pattern'),
        ('^.*University$', 'University pattern'),
        ('^Hospital.*', 'Hospital pattern'),
        ('^.*Hospital$', 'Hospital pattern'),
        ('^Medical.*Center', 'Medical Center pattern'),
        ('^.*Medical Center$', 'Medical Center pattern'),
        ('^Foundation.*', 'Foundation pattern'),
        ('^.*Foundation$', 'Foundation pattern'),
        ('^Research.*Institute', 'Research Institute pattern'),
        ('^.*Center$', 'Center pattern'),
        ('^Center.*', 'Center pattern'),
        ('^.*Medical Center$', 'Medical Center pattern'),
        ('^.*Hospital$', 'Hospital pattern'),
        ('^.*University$', 'University pattern'),
        ('^.*Foundation$', 'Foundation pattern'),
        ('^.*Institute$', 'Institute pattern'),
        ('^.*Clinic$', 'Clinic pattern'),
        ('^.*Laboratory$', 'Laboratory pattern'),
        ('^.*Lab$', 'Lab pattern'),
        ('^.*Department$', 'Department pattern'),
        ('^.*Division$', 'Division pattern'),
        ('^.*Program$', 'Program pattern'),
        ('^.*College$', 'College pattern'),
        ('^.*Academy$', 'Academy pattern'),
        ('^.*School$', 'School pattern')
    ON CONFLICT (pattern) DO NOTHING
    """)


def downgrade() -> None:
    """Downgrade schema - Remove all research/government filtering patterns."""
    
    # Remove all the patterns we added
    op.execute("""
        DELETE FROM resolver_ignore_sponsor 
        WHERE note IN (
            'National Institutes of Health',
            'National Cancer Institute',
            'National Institute of Allergy and Infectious Diseases',
            'National Institute of Mental Health',
            'National Institute of Neurological Disorders and Stroke',
            'National Heart, Lung, and Blood Institute',
            'National Institute of Diabetes and Digestive and Kidney Diseases',
            'National Institute of Environmental Health Sciences',
            'National Institute of General Medical Sciences',
            'National Institute of Child Health and Human Development',
            'National Institute on Drug Abuse',
            'National Institute on Alcohol Abuse and Alcoholism',
            'National Institute of Dental and Craniofacial Research',
            'National Institute of Biomedical Imaging and Bioengineering',
            'National Center for Complementary and Integrative Health',
            'National Library of Medicine',
            'Fogarty International Center',
            'National Center for Advancing Translational Sciences',
            'Office of the Director',
            'Office of Research on Women''s Health',
            'Centers for Disease Control and Prevention',
            'Food and Drug Administration',
            'Department of Veterans Affairs',
            'Department of Defense',
            'National Science Foundation',
            'National Aeronautics and Space Administration',
            'Department of Energy',
            'United States Department of Agriculture',
            'Environmental Protection Agency',
            'Contains Center',
            'Contains Hospital',
            'Contains Institute',
            'Contains University',
            'Contains Foundation',
            'Contains Clinic',
            'Contains Medical',
            'Contains Research',
            'Contains Cancer',
            'Contains National',
            'Contains College',
            'Contains Academy',
            'Contains School',
            'Contains Laboratory',
            'Contains Lab',
            'Contains Department',
            'Contains Division',
            'Contains Program',
            'Contains Government',
            'Contains Public',
            'Contains State',
            'Contains Federal',
            'Contains Ministry',
            'Contains Authority',
            'Contains Agency',
            'Contains Bureau',
            'Contains Office',
            'Contains Service',
            'Contains International',
            'Contains European',
            'Contains Regional',
            'Contains Local',
            'NIH Institute pattern',
            'National Institute pattern',
            'University pattern',
            'Hospital pattern',
            'Medical Center pattern',
            'Foundation pattern',
            'Research Institute pattern',
            'Center pattern',
            'Institute pattern',
            'Clinic pattern',
            'Laboratory pattern',
            'Lab pattern',
            'Department pattern',
            'Division pattern',
            'Program pattern',
            'College pattern',
            'Academy pattern',
            'School pattern'
        )
    """)
