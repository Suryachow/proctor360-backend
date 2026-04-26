import base64
import hashlib
import hmac
import struct
import time
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.core.config import settings


import bcrypt

def hash_password(password: str) -> str:
    # Bcrypt has a 72-byte limit, and passlib is broken with bcrypt>=4.0
    pwd_bytes = password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    pwd_bytes = password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    return bcrypt.checkpw(pwd_bytes, hashed_password.encode('utf-8'))


def create_access_token(subject: str, role: str = "student") -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _totp_code(secret: str, counter: int, digits: int = 6) -> str:
    secret_bytes = base64.b32decode(secret, casefold=True)
    counter_bytes = struct.pack(">Q", counter)
    digest = hmac.new(secret_bytes, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    otp = binary % (10 ** digits)
    return str(otp).zfill(digits)


def verify_totp(code: str, secret: str | None = None, window: int | None = None) -> bool:
    if not code or not code.isdigit() or len(code) != 6:
        return False

    if settings.admin_mfa_static_code and hmac.compare_digest(code, settings.admin_mfa_static_code):
        return True

    totp_secret = secret or settings.admin_mfa_secret
    allowed_window = settings.admin_mfa_window if window is None else window
    time_step = 30
    current_counter = int(time.time() // time_step)

    for drift in range(-allowed_window, allowed_window + 1):
        candidate = _totp_code(totp_secret, current_counter + drift)
        if hmac.compare_digest(candidate, code):
            return True
    return False
