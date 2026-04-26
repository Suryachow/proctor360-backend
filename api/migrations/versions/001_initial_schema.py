"""Initial schema with Certificate and EvidenceFrame tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-04-09 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Certificate and EvidenceFrame tables"""
    
    # Create certificates table
    op.create_table(
        'certificates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('student_email', sa.String(length=255), nullable=False),
        sa.Column('exam_code', sa.String(length=100), nullable=False),
        sa.Column('score_percent', sa.Float(), nullable=False),
        sa.Column('integrity_band', sa.String(length=50), nullable=False),
        sa.Column('verification_hash', sa.String(length=255), nullable=False),
        sa.Column('issued_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('pdf_path', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_certificates_id'), 'certificates', ['id'], unique=False)
    op.create_index(op.f('ix_certificates_session_id'), 'certificates', ['session_id'], unique=False)
    op.create_index(op.f('ix_certificates_student_email'), 'certificates', ['student_email'], unique=False)
    op.create_index(op.f('ix_certificates_verification_hash'), 'certificates', ['verification_hash'], unique=True)
    
    # Create evidence_frames table
    op.create_table(
        'evidence_frames',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('violation_id', sa.Integer(), nullable=True),
        sa.Column('frame_base64', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('frame_index', sa.Integer(), nullable=False),
        sa.Column('ai_analysis', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.ForeignKeyConstraint(['violation_id'], ['violations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evidence_frames_id'), 'evidence_frames', ['id'], unique=False)
    op.create_index(op.f('ix_evidence_frames_session_id'), 'evidence_frames', ['session_id'], unique=False)
    op.create_index(op.f('ix_evidence_frames_violation_id'), 'evidence_frames', ['violation_id'], unique=False)
    op.create_index(op.f('ix_evidence_frames_timestamp'), 'evidence_frames', ['timestamp'], unique=False)


def downgrade() -> None:
    """Drop Certificate and EvidenceFrame tables"""
    op.drop_index(op.f('ix_evidence_frames_timestamp'), table_name='evidence_frames')
    op.drop_index(op.f('ix_evidence_frames_violation_id'), table_name='evidence_frames')
    op.drop_index(op.f('ix_evidence_frames_session_id'), table_name='evidence_frames')
    op.drop_index(op.f('ix_evidence_frames_id'), table_name='evidence_frames')
    op.drop_table('evidence_frames')
    
    op.drop_index(op.f('ix_certificates_verification_hash'), table_name='certificates')
    op.drop_index(op.f('ix_certificates_student_email'), table_name='certificates')
    op.drop_index(op.f('ix_certificates_session_id'), table_name='certificates')
    op.drop_index(op.f('ix_certificates_id'), table_name='certificates')
    op.drop_table('certificates')
