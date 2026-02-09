from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Optional
from datetime import datetime

from app.db.database import get_db
from app.db.models import User, Session as DBSession, Lap, Image
from app.api.dependencies import get_current_user
from app.api.schemas import (
    SessionResponse, SessionListResponse, CreateSessionRequest,
    UpdateSessionRequest, LapResponse, CreateLapRequest, UpdateLapRequest,
    ImageResponse, ApiResponse
)
from app.services.minio_service import generate_presigned_url

router = APIRouter(prefix="/sessions", tags=["Sessions"])


def _parse_datetime_flexible(s: str) -> Optional[datetime]:
    """Parse a datetime string that could be ISO format or JS toLocaleString() output.
    Returns a datetime object or None if unparseable."""
    if not s:
        return None
    
    # Try ISO format first (most common from well-behaved clients)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass
    
    # Try common locale formats from JS toLocaleString()
    # e.g. "2/8/2025, 3:30:00 PM" or "08/02/2025, 15:30:00"
    locale_formats = [
        "%m/%d/%Y, %I:%M:%S %p",   # US: 2/8/2025, 3:30:00 PM
        "%d/%m/%Y, %H:%M:%S",      # en-GB: 08/02/2025, 15:30:00
        "%m/%d/%Y, %H:%M:%S",      # US 24h: 2/8/2025, 15:30:00
        "%Y-%m-%d %H:%M:%S",       # SQL-ish: 2025-02-08 15:30:00
        "%d/%m/%Y, %I:%M:%S %p",   # en-GB 12h
    ]
    for fmt in locale_formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    
    # Last resort: return current time and log warning
    import logging
    logging.getLogger(__name__).warning(f"Could not parse datetime string: {s!r}, using current time")
    return datetime.utcnow()


def _serialize_datetime(dt) -> Optional[str]:
    """Safely serialize a datetime to ISO string"""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def build_session_response(session: DBSession, include_laps: bool = True) -> dict:
    """Build session response with presigned URLs for images"""
    session_data = {
        "id": session.id,
        "sessionUuid": session.session_uuid,
        "sessionName": session.session_name,
        "description": session.description,
        "startedAt": _serialize_datetime(session.start_time),
        "endedAt": _serialize_datetime(session.end_time),
        "totalDuration": session.total_duration,
        "isActive": session.is_active,
        "isCompleted": session.is_completed,
        "createdAt": _serialize_datetime(session.created_at),
        "updatedAt": _serialize_datetime(session.updated_at),
    }
    
    if include_laps:
        laps_data = []
        for lap in session.laps:
            # Generate presigned URLs for images
            images_data = []
            for img in lap.images:
                presigned_url = generate_presigned_url(img.minio_object_key, expiration=3600)
                if presigned_url:
                    images_data.append({
                        "imageId": img.image_uuid,
                        "imageName": img.image_name,
                        "lapId": lap.id,
                        "url": presigned_url,
                        "mimeType": img.mime_type,
                        "fileSize": img.file_size,
                        "createdAt": _serialize_datetime(img.created_at)
                    })
            
            laps_data.append({
                "id": lap.id,
                "lapUuid": lap.lap_uuid,
                "lapNumber": lap.lap_number,
                "lapName": lap.lap_name,
                "startedAt": _serialize_datetime(lap.start_time),
                "endedAt": _serialize_datetime(lap.end_time),
                "duration": lap.duration,
                "isActive": lap.is_active,
                "images": images_data
            })
        
        session_data["laps"] = laps_data
    
    return session_data


@router.post("/", response_model=SessionResponse)
def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new session"""
    started_at = _parse_datetime_flexible(request.startedAt) if request.startedAt else datetime.utcnow()
    
    db_session = DBSession(
        user_id=current_user.id,
        session_name=request.sessionName,
        description=request.description,
        start_time=started_at,
        is_active=True
    )
    
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    
    return build_session_response(db_session)


@router.get("/", response_model=List[SessionListResponse])
def list_sessions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    is_completed: Optional[bool] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all sessions for the current user"""
    query = db.query(DBSession).filter(DBSession.user_id == current_user.id)
    
    # Apply filters
    if start_date:
        query = query.filter(DBSession.created_at >= start_date)
    if end_date:
        query = query.filter(DBSession.created_at <= end_date)
    if is_completed is not None:
        query = query.filter(DBSession.is_completed == is_completed)
    
    # Order by created_at descending
    query = query.order_by(desc(DBSession.created_at))
    
    # Apply pagination
    sessions = query.offset(offset).limit(limit).all()
    
    # Return list without laps
    return [build_session_response(s, include_laps=False) for s in sessions]


@router.get("/latest", response_model=SessionResponse)
def get_latest_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the latest session for the current user"""
    session = db.query(DBSession).filter(
        DBSession.user_id == current_user.id
    ).order_by(desc(DBSession.created_at)).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No sessions found"
        )
    
    return build_session_response(session)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a session by ID"""
    session = db.query(DBSession).filter(
        and_(DBSession.id == session_id, DBSession.user_id == current_user.id)
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return build_session_response(session)


@router.put("/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: int,
    request: UpdateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a session"""
    session = db.query(DBSession).filter(
        and_(DBSession.id == session_id, DBSession.user_id == current_user.id)
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Update fields
    if request.sessionName is not None:
        session.session_name = request.sessionName
    if request.description is not None:
        session.description = request.description
    if request.endedAt is not None:
        session.end_time = _parse_datetime_flexible(request.endedAt) or datetime.utcnow()
        session.is_active = False
    if request.totalDuration is not None:
        session.total_duration = request.totalDuration
    if request.isCompleted is not None:
        session.is_completed = request.isCompleted
    
    db.commit()
    db.refresh(session)
    
    return build_session_response(session)


@router.delete("/{session_id}")
def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a session"""
    session = db.query(DBSession).filter(
        and_(DBSession.id == session_id, DBSession.user_id == current_user.id)
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Delete images from MinIO
    from app.services.minio_service import delete_session_images
    delete_session_images(current_user.id, session.id)
    
    # Delete session (cascade will delete laps and images records)
    db.delete(session)
    db.commit()
    
    return ApiResponse(success=True, message="Session deleted successfully")


# ============ Lap Routes ============

@router.post("/{session_id}/laps", response_model=LapResponse)
def create_lap(
    session_id: int,
    request: CreateLapRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new lap in a session"""
    # Verify session exists and belongs to user
    session = db.query(DBSession).filter(
        and_(DBSession.id == session_id, DBSession.user_id == current_user.id)
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Get lap number (count existing laps + 1)
    lap_count = db.query(Lap).filter(Lap.session_id == session_id).count()
    lap_number = lap_count + 1
    
    started_at = _parse_datetime_flexible(request.startedAt) if request.startedAt else datetime.utcnow()
    
    db_lap = Lap(
        user_id=current_user.id,
        session_id=session_id,
        lap_number=lap_number,
        lap_name=request.lapName,
        start_time=started_at,
        is_active=True
    )
    
    db.add(db_lap)
    db.commit()
    db.refresh(db_lap)
    
    return {
        "id": db_lap.id,
        "lapUuid": db_lap.lap_uuid,
        "lapNumber": db_lap.lap_number,
        "lapName": db_lap.lap_name,
        "startedAt": _serialize_datetime(db_lap.start_time),
        "endedAt": _serialize_datetime(db_lap.end_time),
        "duration": db_lap.duration,
        "isActive": db_lap.is_active,
        "images": []
    }


@router.put("/{session_id}/laps/{lap_id}", response_model=LapResponse)
def update_lap(
    session_id: int,
    lap_id: int,
    request: UpdateLapRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a lap"""
    lap = db.query(Lap).filter(
        and_(
            Lap.id == lap_id,
            Lap.session_id == session_id,
            Lap.user_id == current_user.id
        )
    ).first()
    
    if not lap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lap not found"
        )
    
    # Update fields
    if request.lapName is not None:
        lap.lap_name = request.lapName
    if request.endedAt is not None:
        lap.end_time = _parse_datetime_flexible(request.endedAt) or datetime.utcnow()
        lap.is_active = False
    if request.duration is not None:
        lap.duration = request.duration
    
    db.commit()
    db.refresh(lap)
    
    # Generate presigned URLs for images
    images_data = []
    for img in lap.images:
        presigned_url = generate_presigned_url(img.minio_object_key, expiration=3600)
        if presigned_url:
            images_data.append({
                "imageId": img.image_uuid,
                "imageName": img.image_name,
                "lapId": lap.id,
                "url": presigned_url,
                "mimeType": img.mime_type,
                "fileSize": img.file_size,
                "createdAt": _serialize_datetime(img.created_at)
            })
    
    return {
        "id": lap.id,
        "lapUuid": lap.lap_uuid,
        "lapNumber": lap.lap_number,
        "lapName": lap.lap_name,
        "startedAt": _serialize_datetime(lap.start_time),
        "endedAt": _serialize_datetime(lap.end_time),
        "duration": lap.duration,
        "isActive": lap.is_active,
        "images": images_data
    }


@router.delete("/{session_id}/laps/{lap_id}")
def delete_lap(
    session_id: int,
    lap_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a lap"""
    lap = db.query(Lap).filter(
        and_(
            Lap.id == lap_id,
            Lap.session_id == session_id,
            Lap.user_id == current_user.id
        )
    ).first()
    
    if not lap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lap not found"
        )
    
    # Delete images from MinIO
    from app.services.minio_service import delete_lap_images
    delete_lap_images(current_user.id, session_id, lap_id)
    
    # Delete lap (cascade will delete images records)
    db.delete(lap)
    db.commit()
    
    return ApiResponse(success=True, message="Lap deleted successfully")
