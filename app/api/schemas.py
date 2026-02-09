from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============ Auth Schemas ============

class LoginRequest(BaseModel):
    username: str
    password: str


class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6)


class AuthResponse(BaseModel):
    accessToken: str
    refreshToken: str
    message: Optional[str] = None


class RefreshRequest(BaseModel):
    refreshToken: str


class RefreshResponse(BaseModel):
    accessToken: str


# ============ Session & Lap Schemas ============

# --- Request schemas (what routes expect from the client) ---

class CreateSessionRequest(BaseModel):
    """Schema for creating a new session"""
    sessionName: Optional[str] = None
    description: Optional[str] = None
    startedAt: Optional[str] = None  # ISO datetime string or locale string


class UpdateSessionRequest(BaseModel):
    """Schema for updating a session"""
    sessionName: Optional[str] = None
    description: Optional[str] = None
    endedAt: Optional[str] = None  # ISO datetime string
    totalDuration: Optional[int] = None  # Total seconds
    isCompleted: Optional[bool] = None


class CreateLapRequest(BaseModel):
    """Schema for creating a lap in a session"""
    lapName: Optional[str] = None
    startedAt: Optional[str] = None  # ISO datetime string


class UpdateLapRequest(BaseModel):
    """Schema for updating a lap"""
    lapName: Optional[str] = None
    endedAt: Optional[str] = None
    duration: Optional[int] = None  # Total seconds


# --- Bulk session create (frontend sends all laps at once when stopping) ---

class LapCreate(BaseModel):
    """Schema for creating a lap (bulk session save)"""
    id: str  # Frontend-generated UUID
    startTime: str  # ISO datetime string
    endTime: str  # ISO datetime string
    current_hours: int = 0
    current_minutes: int = 0
    current_seconds: int = 0
    workDoneString: Optional[str] = None
    isBreakLap: bool = False
    HourlyAmount: float = 450.0


class SessionCreate(BaseModel):
    """Schema for creating a session with all laps at once"""
    laps: List[LapCreate]
    sessionName: Optional[str] = None


# --- Response schemas ---

class ImageResponseItem(BaseModel):
    """Image data returned within a lap response"""
    imageId: str
    imageName: Optional[str] = None
    lapId: int
    url: Optional[str] = None
    mimeType: Optional[str] = None
    fileSize: Optional[int] = None
    createdAt: Optional[str] = None

    class Config:
        from_attributes = True


class LapResponse(BaseModel):
    """Schema for lap in response"""
    id: int
    lapUuid: str
    lapNumber: int
    lapName: Optional[str] = None
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None
    duration: Optional[int] = None
    isActive: bool = False
    images: List[ImageResponseItem] = []

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    """Schema for full session response (with laps)"""
    id: int
    sessionUuid: str
    sessionName: Optional[str] = None
    description: Optional[str] = None
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None
    totalDuration: Optional[int] = None
    isActive: bool = False
    isCompleted: bool = False
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    laps: List[LapResponse] = []

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """Schema for session in list (without laps)"""
    id: int
    sessionUuid: str
    sessionName: Optional[str] = None
    description: Optional[str] = None
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None
    totalDuration: Optional[int] = None
    isActive: bool = False
    isCompleted: bool = False
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

    class Config:
        from_attributes = True


# Backwards-compatible aliases
SessionUpdate = UpdateSessionRequest
SessionListItem = SessionListResponse
LapUpdate = UpdateLapRequest


# ============ Image Schemas ============

class ImageResponse(BaseModel):
    """Schema for image response"""
    imageId: str
    imageName: Optional[str] = None
    lapId: int
    url: Optional[str] = None
    mimeType: Optional[str] = None
    fileSize: Optional[int] = None
    createdAt: Optional[str] = None

    class Config:
        from_attributes = True


class ImageUploadResponse(BaseModel):
    """Schema for image upload response"""
    success: bool
    imageId: str
    message: Optional[str] = None


# ============ Settings Schemas ============

class UserSettingsResponse(BaseModel):
    """Schema for user settings response"""
    showAmount: bool = True
    showStatsBeforeLaps: bool = False
    breaksImpactAmount: bool = False
    breaksImpactTime: bool = False
    minimalistMode: bool = False
    notificationEnabled: bool = True
    notificationIntervalHours: float = 2.0
    hourlyAmount: float = 450.0

    class Config:
        from_attributes = True


class UpdateSettingsRequest(BaseModel):
    """Schema for updating user settings"""
    showAmount: Optional[bool] = None
    showStatsBeforeLaps: Optional[bool] = None
    breaksImpactAmount: Optional[bool] = None
    breaksImpactTime: Optional[bool] = None
    minimalistMode: Optional[bool] = None
    notificationEnabled: Optional[bool] = None
    notificationIntervalHours: Optional[float] = None
    hourlyAmount: Optional[float] = None


# Alias so either name works
UserSettingsUpdate = UpdateSettingsRequest


# ============ Generic Response ============

class ApiResponse(BaseModel):
    success: bool
    message: Optional[str] = None
