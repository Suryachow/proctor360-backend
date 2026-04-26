"""
Database migration script to add new columns to exam_sessions table for enhanced proctoring.
Run this script to update the database schema before deploying the updated application.
"""

from sqlalchemy import text, inspect
from app.db.session import SessionLocal, engine


def migrate_database():
    """Add new columns to exam_sessions table for enhanced security"""
    db = SessionLocal()
    inspector = inspect(engine)
    
    # Get existing columns in exam_sessions table
    existing_columns = [col['name'] for col in inspector.get_columns('exam_sessions')]
    
    try:
        # Add device_fingerprint column
        if 'device_fingerprint' not in existing_columns:
            db.execute(text(
                "ALTER TABLE exam_sessions ADD COLUMN device_fingerprint VARCHAR(255) NULL"
            ))
            db.commit()
            print("✓ Added device_fingerprint column")
        else:
            print("  device_fingerprint column already exists")

        # Add registered_face_image column
        if 'registered_face_image' not in existing_columns:
            db.execute(text(
                "ALTER TABLE exam_sessions ADD COLUMN registered_face_image TEXT NULL"
            ))
            db.commit()
            print("✓ Added registered_face_image column")
        else:
            print("  registered_face_image column already exists")

        # Add face_similarity_history column
        if 'face_similarity_history' not in existing_columns:
            db.execute(text(
                "ALTER TABLE exam_sessions ADD COLUMN face_similarity_history TEXT DEFAULT '[]'"
            ))
            db.commit()
            print("✓ Added face_similarity_history column")
        else:
            print("  face_similarity_history column already exists")

        print("\n✓ Database migration completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_database()
