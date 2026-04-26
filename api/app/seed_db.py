import sys
import os
sys.path.append(os.path.join(os.getcwd(), "app"))

from app.db.session import SessionLocal
from app.models.entities import Student
from app.core.security import hash_password

def seed():
    db = SessionLocal()
    email = "student@test.com"
    password = "Student123!"
    
    existing = db.query(Student).filter(Student.email == email).first()
    if existing:
        print(f"Student {email} already exists. Updating password...")
        existing.password_hash = hash_password(password)
        existing.device_hash = "DEMO_DEVICE" # We'll handle this in the code
    else:
        print(f"Creating test student: {email}")
        student = Student(
            email=email,
            password_hash=hash_password(password),
            device_hash="DEMO_DEVICE",
            registered_face_image="placeholder_face_data"
        )
        db.add(student)
    
    db.commit()
    db.close()
    print("Seed complete.")

if __name__ == "__main__":
    seed()
