"""Phase 1: Advanced Proctoring Features - Schema

Revision ID: 002_phase1_advanced_features
Revises: 001_initial
Create Date: 2026-04-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_phase1_advanced_features'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Phase 1 tables for advanced proctoring"""
    
    # PHASE 1A: Multi-Camera Proctoring
    op.create_table(
        'secondary_cameras',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.String(length=255), nullable=False),
        sa.Column('camera_type', sa.String(length=50), nullable=False),  # 'mobile', 'tablet', 'webcam'
        sa.Column('registration_time', sa.DateTime(), nullable=False),
        sa.Column('last_frame_timestamp', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('sync_offset_ms', sa.Integer(), default=0),  # Time offset from primary camera
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_secondary_cameras_session_id'), 'secondary_cameras', ['session_id'], unique=False)
    op.create_index(op.f('ix_secondary_cameras_device_id'), 'secondary_cameras', ['device_id'], unique=False)
    
    op.create_table(
        'camera_sync_frames',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('primary_frame_id', sa.Integer(), nullable=True),
        sa.Column('secondary_camera_id', sa.Integer(), nullable=False),
        sa.Column('frame_base64', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('frame_index', sa.Integer(), nullable=False),
        sa.Column('cheating_indicators', sa.JSON(), nullable=True),  # Side-cam specific analysis
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.ForeignKeyConstraint(['secondary_camera_id'], ['secondary_cameras.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_camera_sync_frames_session_id'), 'camera_sync_frames', ['session_id'], unique=False)
    op.create_index(op.f('ix_camera_sync_frames_secondary_camera_id'), 'camera_sync_frames', ['secondary_camera_id'], unique=False)
    
    # PHASE 1B: Audio Intelligence
    op.create_table(
        'audio_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('audio_base64', sa.Text(), nullable=False),  # Compressed audio chunk
        sa.Column('duration_seconds', sa.Float(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('sample_index', sa.Integer(), nullable=False),
        sa.Column('audio_analysis', sa.JSON(), nullable=True),  # Whisper + voice detection results
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audio_samples_session_id'), 'audio_samples', ['session_id'], unique=False)
    op.create_index(op.f('ix_audio_samples_timestamp'), 'audio_samples', ['timestamp'], unique=False)
    
    # PHASE 1C: Behavioral Fingerprinting
    op.create_table(
        'behavioral_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=False),  # 'typing_speed', 'mouse_movement', 'scroll_pattern'
        sa.Column('baseline_value', sa.Float(), nullable=False),  # Established in first 5 minutes
        sa.Column('current_value', sa.Float(), nullable=False),
        sa.Column('deviation_percent', sa.Float(), nullable=False),  # How far from baseline (0-100%)
        sa.Column('is_anomaly', sa.Boolean(), default=False),
        sa.Column('confidence_score', sa.Float(), nullable=False),  # 0-1
        sa.Column('collected_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_behavioral_metrics_session_id'), 'behavioral_metrics', ['session_id'], unique=False)
    op.create_index(op.f('ix_behavioral_metrics_metric_type'), 'behavioral_metrics', ['metric_type'], unique=False)
    
    op.create_table(
        'typing_patterns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('wpm', sa.Float(), nullable=False),  # Words per minute
        sa.Column('accuracy_percent', sa.Float(), nullable=False),  # Keystroke accuracy
        sa.Column('avg_keystroke_interval_ms', sa.Float(), nullable=False),
        sa.Column('hold_time_distribution', sa.JSON(), nullable=False),  # Time held per key distribution
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_typing_patterns_session_id'), 'typing_patterns', ['session_id'], unique=False)
    
    op.create_table(
        'mouse_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('velocity_px_per_sec', sa.Float(), nullable=False),
        sa.Column('acceleration_px_per_sec2', sa.Float(), nullable=False),
        sa.Column('jitter_score', sa.Float(), nullable=False),  # 0-1, higher = more jittery (natural)
        sa.Column('teleport_events', sa.Integer(), default=0),  # Abrupt jumps (unnatural RDP)
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mouse_movements_session_id'), 'mouse_movements', ['session_id'], unique=False)
    
    # PHASE 1D: Eye Tracking & Attention Score
    op.create_table(
        'eye_gaze_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('gaze_x', sa.Float(), nullable=False),  # Normalized 0-1
        sa.Column('gaze_y', sa.Float(), nullable=False),  # Normalized 0-1
        sa.Column('pupil_diameter_mm', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),  # 0-1, tracking quality
        sa.Column('is_on_screen', sa.Boolean(), nullable=False),  # Looking at exam area?
        sa.Column('region_of_interest', sa.String(length=50), nullable=True),  # 'question_area', 'answer_area', 'off_screen'
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_eye_gaze_samples_session_id'), 'eye_gaze_samples', ['session_id'], unique=False)
    op.create_index(op.f('ix_eye_gaze_samples_timestamp'), 'eye_gaze_samples', ['timestamp'], unique=False)
    
    op.create_table(
        'attention_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('window_start_time', sa.DateTime(), nullable=False),  # e.g., 1-minute windows
        sa.Column('window_end_time', sa.DateTime(), nullable=False),
        sa.Column('attention_percent', sa.Float(), nullable=False),  # % time looking at screen
        sa.Column('focus_score', sa.Float(), nullable=False),  # 0-100, composite attention metric
        sa.Column('gaze_stability', sa.Float(), nullable=False),  # 0-1, higher = more stable
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_attention_scores_session_id'), 'attention_scores', ['session_id'], unique=False)
    
    # PHASE 1E: Zero Trust Architecture
    op.create_table(
        'device_verification_checks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('check_type', sa.String(length=100), nullable=False),  # 'device_fingerprint', 'vpn_detection', 'network_change'
        sa.Column('check_timestamp', sa.DateTime(), nullable=False),
        sa.Column('result', sa.String(length=20), nullable=False),  # 'pass', 'fail', 'warning'
        sa.Column('details', sa.JSON(), nullable=True),  # Details of what was checked
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_verification_checks_session_id'), 'device_verification_checks', ['session_id'], unique=False)
    op.create_index(op.f('ix_device_verification_checks_check_type'), 'device_verification_checks', ['check_type'], unique=False)
    
    op.create_table(
        'identity_reverification_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('scheduled_time', sa.DateTime(), nullable=False),
        sa.Column('actual_time', sa.DateTime(), nullable=True),
        sa.Column('live_image_base64', sa.Text(), nullable=True),
        sa.Column('similarity_score', sa.Float(), nullable=True),
        sa.Column('passed', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_identity_reverification_events_session_id'), 'identity_reverification_events', ['session_id'], unique=False)
    
    # Add columns to exam_sessions for Phase 1 metrics
    op.add_column('exam_sessions', sa.Column('device_integrity_score', sa.Float(), nullable=True, server_default='100.0'))
    op.add_column('exam_sessions', sa.Column('attention_score', sa.Float(), nullable=True, server_default='100.0'))
    op.add_column('exam_sessions', sa.Column('behavioral_consistency_score', sa.Float(), nullable=True, server_default='100.0'))
    op.add_column('exam_sessions', sa.Column('multi_camera_enabled', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('exam_sessions', sa.Column('audio_enabled', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('exam_sessions', sa.Column('eye_tracking_enabled', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Drop Phase 1 tables"""
    
    # Drop exam_sessions columns
    op.drop_column('exam_sessions', 'eye_tracking_enabled')
    op.drop_column('exam_sessions', 'audio_enabled')
    op.drop_column('exam_sessions', 'multi_camera_enabled')
    op.drop_column('exam_sessions', 'behavioral_consistency_score')
    op.drop_column('exam_sessions', 'attention_score')
    op.drop_column('exam_sessions', 'device_integrity_score')
    
    # Drop zero trust tables
    op.drop_index(op.f('ix_identity_reverification_events_session_id'), table_name='identity_reverification_events')
    op.drop_table('identity_reverification_events')
    
    op.drop_index(op.f('ix_device_verification_checks_check_type'), table_name='device_verification_checks')
    op.drop_index(op.f('ix_device_verification_checks_session_id'), table_name='device_verification_checks')
    op.drop_table('device_verification_checks')
    
    # Drop eye tracking tables
    op.drop_index(op.f('ix_attention_scores_session_id'), table_name='attention_scores')
    op.drop_table('attention_scores')
    
    op.drop_index(op.f('ix_eye_gaze_samples_timestamp'), table_name='eye_gaze_samples')
    op.drop_index(op.f('ix_eye_gaze_samples_session_id'), table_name='eye_gaze_samples')
    op.drop_table('eye_gaze_samples')
    
    # Drop behavioral tables
    op.drop_index(op.f('ix_mouse_movements_session_id'), table_name='mouse_movements')
    op.drop_table('mouse_movements')
    
    op.drop_index(op.f('ix_typing_patterns_session_id'), table_name='typing_patterns')
    op.drop_table('typing_patterns')
    
    op.drop_index(op.f('ix_behavioral_metrics_metric_type'), table_name='behavioral_metrics')
    op.drop_index(op.f('ix_behavioral_metrics_session_id'), table_name='behavioral_metrics')
    op.drop_table('behavioral_metrics')
    
    # Drop audio tables
    op.drop_index(op.f('ix_audio_samples_timestamp'), table_name='audio_samples')
    op.drop_index(op.f('ix_audio_samples_session_id'), table_name='audio_samples')
    op.drop_table('audio_samples')
    
    # Drop multi-camera tables
    op.drop_index(op.f('ix_camera_sync_frames_secondary_camera_id'), table_name='camera_sync_frames')
    op.drop_index(op.f('ix_camera_sync_frames_session_id'), table_name='camera_sync_frames')
    op.drop_table('camera_sync_frames')
    
    op.drop_index(op.f('ix_secondary_cameras_device_id'), table_name='secondary_cameras')
    op.drop_index(op.f('ix_secondary_cameras_session_id'), table_name='secondary_cameras')
    op.drop_table('secondary_cameras')
