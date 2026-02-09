from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.database import Base


def generate_uuid():
    """Generate a unique UUID string"""
    return str(uuid.uuid4())


class User(Base):
    """User model - stores user info and authentication"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    laps = relationship("Lap", back_populates="user", cascade="all, delete-orphan")
    images = relationship("Image", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")


class RefreshToken(Base):
    """Stores refresh tokens for JWT authentication"""
    __tablename__ = "refresh_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(500), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="refresh_tokens")


class Session(Base):
    """Work session - represents a saved work session"""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_uuid = Column(String(36), default=generate_uuid, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Session metadata
    session_name = Column(String(200), nullable=True)  # Optional name for the session
    description = Column(Text, nullable=True)  # Optional description
    start_time = Column(DateTime(timezone=True), nullable=True)  # From first lap
    end_time = Column(DateTime(timezone=True), nullable=True)  # From last lap
    lap_count = Column(Integer, default=0)
    total_seconds = Column(Integer, default=0)
    total_duration = Column(Integer, default=0)  # Alias for total_seconds, used by some routes
    total_amount = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    is_completed = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    laps = relationship("Lap", back_populates="session", cascade="all, delete-orphan")
    images = relationship("Image", back_populates="session", cascade="all, delete-orphan")


class Lap(Base):
    """Individual lap/time block within a session"""
    __tablename__ = "laps"
    
    id = Column(Integer, primary_key=True, index=True)
    lap_uuid = Column(String(36), default=generate_uuid, unique=True, index=True)
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    
    # Lap metadata
    lap_number = Column(Integer, default=1)
    lap_name = Column(String(500), nullable=True)  # What work was done
    
    # Time tracking
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration = Column(Integer, nullable=True)  # Duration in seconds
    is_active = Column(Boolean, default=True)
    
    # Detailed time (from frontend stopwatch)
    current_hours = Column(Integer, default=0)
    current_minutes = Column(Integer, default=0)
    current_seconds = Column(Integer, default=0)
    
    # Lap details
    work_done_string = Column(Text, nullable=True)
    is_break_lap = Column(Boolean, default=False)
    hourly_amount = Column(Float, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="laps")
    session = relationship("Session", back_populates="laps")
    images = relationship("Image", back_populates="lap", cascade="all, delete-orphan")


class Image(Base):
    """Images attached to laps"""
    __tablename__ = "images"
    
    id = Column(Integer, primary_key=True, index=True)
    image_uuid = Column(String(36), default=generate_uuid, unique=True, index=True)
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    lap_id = Column(Integer, ForeignKey("laps.id", ondelete="CASCADE"), nullable=False)
    
    # File metadata
    image_name = Column(String(300), nullable=True)  # Original filename
    mime_type = Column(String(100), nullable=True)  # e.g. "image/jpeg"
    file_size = Column(Integer, nullable=True)  # Size in bytes
    file_format = Column(String(10), nullable=True)  # jpg, png, etc.
    
    # MinIO storage
    minio_object_key = Column(String(500), nullable=False)  # Path in MinIO
    minio_bucket = Column(String(100), nullable=True)  # Bucket name
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="images")
    session = relationship("Session", back_populates="images")
    lap = relationship("Lap", back_populates="images")


class UserSettings(Base):
    """User settings/preferences"""
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Display settings
    show_amount = Column(Boolean, default=True)
    show_stats_before_laps = Column(Boolean, default=False)
    breaks_impact_amount = Column(Boolean, default=False)
    breaks_impact_time = Column(Boolean, default=False)
    minimalist_mode = Column(Boolean, default=False)
    
    # Notification settings
    notification_enabled = Column(Boolean, default=True)
    notification_interval_hours = Column(Float, default=2.0)
    
    # Financial settings
    hourly_amount = Column(Float, default=450.0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="settings")
