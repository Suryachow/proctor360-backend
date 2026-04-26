from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import Student

security = HTTPBearer()


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials
    payload = decode_access_token(token)

    role = payload.get("role")
    if role != "student":
        raise HTTPException(status_code=403, detail="Student role required")

    subject = str(payload.get("sub") or "").strip().lower()
    student = db.query(Student).filter(Student.email == subject).first()
    if not student:
        raise HTTPException(status_code=401, detail="Student not found")
    return student


def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")

    expected_admin_email = settings.admin_email.strip().lower()
    token_subject = str(payload.get("sub") or "").strip().lower()
    if token_subject != expected_admin_email:
        raise HTTPException(status_code=403, detail="Admin identity mismatch")

    return {"email": expected_admin_email, "role": "admin"}
