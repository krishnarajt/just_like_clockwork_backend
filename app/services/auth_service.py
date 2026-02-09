from datetime import datetime, timedelta, timezone
from typing import Optional
import os
import jwt
import hashlib
import secrets
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.models import User, RefreshToken

logger = logging.getLogger(__name__)

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Password hashing configuration
SALT_LENGTH = 32  # 32 bytes = 256 bits
HASH_ITERATIONS = 100000  # OWASP recommended minimum


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a stored hash"""
    try:
        # Format: iterations$salt$hash
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False

        iterations = int(parts[0])
        salt = bytes.fromhex(parts[1])
        stored_hash = parts[2]

        # Hash the provided password with the same salt and iterations
        computed_hash = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode("utf-8"), salt, iterations
        ).hex()

        # Constant-time comparison to prevent timing attacks
        return secrets.compare_digest(computed_hash, stored_hash)
    except (ValueError, IndexError):
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using PBKDF2-SHA256"""
    # Generate a random salt
    salt = secrets.token_bytes(SALT_LENGTH)

    # Hash the password
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, HASH_ITERATIONS
    ).hex()

    # Return format: iterations$salt$hash
    return f"{HASH_ITERATIONS}${salt.hex()}${password_hash}"


def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Create a new access token"""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(db: Session, user_id: int) -> str:
    """Create a new refresh token and store in database.
    Also cleans up any expired tokens for this user to prevent DB bloat."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {"sub": str(user_id), "exp": expires_at, "type": "refresh"}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    # Clean up expired tokens for this user (prevents unbounded growth)
    try:
        db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.expires_at <= now,
        ).delete(synchronize_session=False)
    except Exception as e:
        logger.warning(f"Failed to clean expired tokens for user {user_id}: {e}")

    # Store new token in database
    db_token = RefreshToken(user_id=user_id, token=token, expires_at=expires_at)
    db.add(db_token)
    db.commit()

    return token


def verify_access_token(token: str) -> Optional[int]:
    """Verify an access token and return user_id"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        user_id = int(payload.get("sub"))
        return user_id
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def verify_refresh_token(db: Session, token: str) -> Optional[int]:
    """Verify a refresh token and return user_id"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        user_id = int(payload.get("sub"))

        # Check if token exists in database
        db_token = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token == token,
                RefreshToken.user_id == user_id,
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )

        if not db_token:
            return None

        return user_id
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def revoke_refresh_token(db: Session, token: str) -> bool:
    """Revoke a refresh token"""
    db_token = db.query(RefreshToken).filter(RefreshToken.token == token).first()
    if db_token:
        db.delete(db_token)
        db.commit()
        return True
    return False


def revoke_all_user_tokens(db: Session, user_id: int) -> None:
    """Revoke all refresh tokens for a user"""
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()
    db.commit()


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate a user with username and password"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_user(db: Session, username: str, password: str) -> User:
    """Create a new user"""
    hashed_password = get_password_hash(password)
    db_user = User(username=username, password_hash=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Get a user by their ID"""
    return db.query(User).filter(User.id == user_id).first()
