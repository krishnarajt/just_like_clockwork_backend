from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone

from app.db.database import get_db
from app.db.models import Lap, Session as DBSession, User
from app.api.dependencies import get_current_user
from app.api.schemas import (
    ApiResponse,
    CreateLapRequest,
    CreateSessionRequest,
    LapResponse,
    SessionListResponse,
    SessionResponse,
    UpdateLapRequest,
    UpdateSessionRequest,
)
from app.services.minio_service import generate_presigned_url

router = APIRouter(prefix="/sessions", tags=["Sessions"])


def _parse_datetime_flexible(s: str) -> Optional[datetime]:
    """Parse ISO strings and legacy JS toLocaleString() values."""
    if not s:
        return None

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass

    locale_formats = [
        "%m/%d/%Y, %I:%M:%S %p",
        "%d/%m/%Y, %H:%M:%S",
        "%m/%d/%Y, %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y, %I:%M:%S %p",
    ]
    for fmt in locale_formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    import logging

    logging.getLogger(__name__).warning(
        "Could not parse datetime string: %r, using current time", s
    )
    return datetime.utcnow()


def _serialize_datetime(dt) -> Optional[str]:
    """Safely serialize a datetime to an ISO string."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _coalesce(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _datetime_sort_value(dt) -> float:
    if dt is None:
        return 0
    if isinstance(dt, str):
        parsed = _parse_datetime_flexible(dt)
        return _datetime_sort_value(parsed)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _lap_duration_seconds(lap: Lap) -> int:
    if lap.duration is not None:
        return int(lap.duration)
    return int(lap.current_hours or 0) * 3600 + int(lap.current_minutes or 0) * 60 + int(
        lap.current_seconds or 0
    )


def _lap_amount(lap: Lap) -> float:
    return round(float(lap.hourly_amount or 0) * (_lap_duration_seconds(lap) / 3600), 3)


def _ordered_laps(laps) -> list[Lap]:
    return sorted(
        laps,
        key=lambda lap: (
            lap.lap_number or 0,
            _datetime_sort_value(lap.start_time),
            lap.id or 0,
        ),
    )


def _resolve_session(db: Session, user_id: int, session_id: str) -> Optional[DBSession]:
    """Resolve a session by database id or stable client/cloud UUID."""
    session_id_str = str(session_id)
    query = db.query(DBSession).filter(DBSession.user_id == user_id)
    if session_id_str.isdigit():
        return query.filter(DBSession.id == int(session_id_str)).first()
    return query.filter(DBSession.session_uuid == session_id_str).first()


def _resolve_lap(db: Session, user_id: int, session_id: int, lap_id: str) -> Optional[Lap]:
    """Resolve a lap by database id or stable client/cloud UUID."""
    lap_id_str = str(lap_id)
    query = db.query(Lap).filter(
        Lap.user_id == user_id,
        Lap.session_id == session_id,
    )
    if lap_id_str.isdigit():
        return query.filter(Lap.id == int(lap_id_str)).first()
    return query.filter(Lap.lap_uuid == lap_id_str).first()


def _recalculate_session_rollup(
    db: Session, session: DBSession, *, preserve_empty_totals: bool = False
) -> None:
    """Keep persisted count/duration/amount aligned with the child laps."""
    laps = (
        db.query(Lap)
        .filter(Lap.session_id == session.id, Lap.user_id == session.user_id)
        .order_by(Lap.lap_number.asc(), Lap.start_time.asc(), Lap.id.asc())
        .all()
    )
    if not laps:
        session.lap_count = 0
        if preserve_empty_totals:
            session.total_seconds = session.total_seconds or 0
            session.total_duration = session.total_duration or 0
            session.total_amount = session.total_amount or 0.0
        else:
            session.total_seconds = 0
            session.total_duration = 0
            session.total_amount = 0.0
        return

    total_seconds = sum(_lap_duration_seconds(lap) for lap in laps)
    session.lap_count = len(laps)
    session.total_seconds = total_seconds
    session.total_duration = total_seconds
    session.total_amount = round(sum(_lap_amount(lap) for lap in laps), 3)

    start_candidates = [lap.start_time for lap in laps if lap.start_time is not None]
    if start_candidates:
        session.start_time = min(start_candidates, key=_datetime_sort_value)

    if session.is_completed:
        end_candidates = [lap.end_time for lap in laps if lap.end_time is not None]
        if end_candidates:
            session.end_time = max(end_candidates, key=_datetime_sort_value)


def _apply_session_fields(
    session: DBSession,
    request: CreateSessionRequest | UpdateSessionRequest,
    *,
    creating: bool = False,
) -> None:
    if creating and getattr(request, "sessionUuid", None):
        session.session_uuid = request.sessionUuid
    if request.sessionName is not None:
        session.session_name = request.sessionName
    if request.description is not None:
        session.description = request.description
    if request.startedAt is not None:
        session.start_time = _parse_datetime_flexible(request.startedAt) or datetime.utcnow()
    elif creating and session.start_time is None:
        session.start_time = datetime.utcnow()
    if request.endedAt is not None:
        session.end_time = _parse_datetime_flexible(request.endedAt) or datetime.utcnow()
        session.is_active = False
    if request.totalDuration is not None:
        session.total_duration = request.totalDuration
        session.total_seconds = request.totalDuration
    if request.totalAmount is not None:
        session.total_amount = request.totalAmount
    if request.isCompleted is not None:
        session.is_completed = request.isCompleted
        session.is_active = not request.isCompleted
    elif creating:
        session.is_completed = False
        session.is_active = request.endedAt is None


def _apply_lap_fields(
    lap: Lap,
    request: CreateLapRequest | UpdateLapRequest,
    *,
    creating: bool = False,
) -> None:
    if creating and getattr(request, "lapUuid", None):
        lap.lap_uuid = request.lapUuid

    lap_name = _coalesce(request.lapName, request.workDoneString)
    if lap_name is not None:
        lap.lap_name = lap_name
        lap.work_done_string = lap_name

    if request.startedAt is not None:
        lap.start_time = _parse_datetime_flexible(request.startedAt) or datetime.utcnow()
    elif creating and lap.start_time is None:
        lap.start_time = datetime.utcnow()

    if request.endedAt is not None:
        lap.end_time = _parse_datetime_flexible(request.endedAt) or datetime.utcnow()
        lap.is_active = False

    current_hours = _coalesce(request.current_hours, request.currentHours)
    current_minutes = _coalesce(request.current_minutes, request.currentMinutes)
    current_seconds = _coalesce(request.current_seconds, request.currentSeconds)
    if current_hours is not None:
        lap.current_hours = int(current_hours)
    if current_minutes is not None:
        lap.current_minutes = int(current_minutes)
    if current_seconds is not None:
        lap.current_seconds = int(current_seconds)

    if request.duration is not None:
        lap.duration = int(request.duration)
    elif any(value is not None for value in (current_hours, current_minutes, current_seconds)):
        lap.duration = _lap_duration_seconds(lap)

    if request.isBreakLap is not None:
        lap.is_break_lap = request.isBreakLap

    hourly_amount = _coalesce(request.hourlyAmount, request.HourlyAmount)
    if hourly_amount is not None:
        lap.hourly_amount = float(hourly_amount)


def build_lap_response(lap: Lap, include_images: bool = True) -> dict:
    images_data = []
    if include_images:
        for img in lap.images:
            presigned_url = generate_presigned_url(img.minio_object_key, expiration=3600)
            if presigned_url:
                images_data.append(
                    {
                        "imageId": img.image_uuid,
                        "imageName": img.image_name,
                        "lapId": lap.id,
                        "url": presigned_url,
                        "mimeType": img.mime_type,
                        "fileSize": img.file_size,
                        "createdAt": _serialize_datetime(img.created_at),
                    }
                )

    return {
        "id": lap.id,
        "lapUuid": lap.lap_uuid,
        "lapNumber": lap.lap_number,
        "lapName": lap.lap_name,
        "workDoneString": lap.work_done_string,
        "startedAt": _serialize_datetime(lap.start_time),
        "endedAt": _serialize_datetime(lap.end_time),
        "duration": lap.duration,
        "currentHours": lap.current_hours or 0,
        "currentMinutes": lap.current_minutes or 0,
        "currentSeconds": lap.current_seconds or 0,
        "isActive": lap.is_active,
        "isBreakLap": lap.is_break_lap,
        "hourlyAmount": lap.hourly_amount or 0.0,
        "images": images_data,
    }


def build_session_response(session: DBSession, include_laps: bool = True) -> dict:
    """Build session response with stable sync identifiers and rollups."""
    laps = _ordered_laps(session.laps)
    computed_lap_count = len(laps)
    computed_total_seconds = sum(_lap_duration_seconds(lap) for lap in laps)
    computed_total_amount = round(sum(_lap_amount(lap) for lap in laps), 3)

    lap_count = session.lap_count or computed_lap_count
    total_seconds = computed_total_seconds or session.total_seconds or 0
    total_duration = computed_total_seconds or session.total_duration or total_seconds
    total_amount = computed_total_amount or session.total_amount or 0.0

    session_data = {
        "id": session.id,
        "sessionUuid": session.session_uuid,
        "sessionName": session.session_name,
        "description": session.description,
        "startedAt": _serialize_datetime(session.start_time),
        "endedAt": _serialize_datetime(session.end_time),
        "lapCount": lap_count,
        "totalSeconds": total_seconds,
        "totalDuration": total_duration,
        "totalAmount": total_amount,
        "isActive": session.is_active,
        "isCompleted": session.is_completed,
        "createdAt": _serialize_datetime(session.created_at),
        "updatedAt": _serialize_datetime(session.updated_at),
    }

    if include_laps:
        session_data["laps"] = [build_lap_response(lap) for lap in laps]

    return session_data


@router.post("/", response_model=SessionResponse)
def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update a session using the client UUID as an idempotency key."""
    db_session = None
    if request.sessionUuid:
        db_session = (
            db.query(DBSession)
            .filter(
                DBSession.user_id == current_user.id,
                DBSession.session_uuid == request.sessionUuid,
            )
            .first()
        )

    is_new_session = db_session is None
    if is_new_session:
        db_session = DBSession(user_id=current_user.id)
        db.add(db_session)

    _apply_session_fields(db_session, request, creating=is_new_session)
    db.flush()
    _recalculate_session_rollup(db, db_session, preserve_empty_totals=True)
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
    db: Session = Depends(get_db),
):
    """List all sessions for the current user."""
    query = db.query(DBSession).filter(DBSession.user_id == current_user.id)

    if start_date:
        query = query.filter(DBSession.created_at >= start_date)
    if end_date:
        query = query.filter(DBSession.created_at <= end_date)
    if is_completed is not None:
        query = query.filter(DBSession.is_completed == is_completed)

    sessions = query.order_by(desc(DBSession.created_at)).offset(offset).limit(limit).all()
    return [build_session_response(s, include_laps=False) for s in sessions]


@router.get("/latest", response_model=SessionResponse)
def get_latest_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the latest session for the current user."""
    session = (
        db.query(DBSession)
        .filter(DBSession.user_id == current_user.id)
        .order_by(desc(DBSession.created_at))
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No sessions found",
        )

    return build_session_response(session)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a session by database ID or session UUID."""
    session = _resolve_session(db, current_user.id, session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return build_session_response(session)


@router.put("/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a session by database ID or session UUID."""
    session = _resolve_session(db, current_user.id, session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    _apply_session_fields(session, request)
    _recalculate_session_rollup(db, session, preserve_empty_totals=True)
    if request.totalDuration is not None:
        session.total_duration = request.totalDuration
        session.total_seconds = request.totalDuration
    if request.totalAmount is not None:
        session.total_amount = request.totalAmount
    db.commit()
    db.refresh(session)

    return build_session_response(session)


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a session by database ID or session UUID."""
    session = _resolve_session(db, current_user.id, session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    from app.services.minio_service import delete_session_images

    delete_session_images(current_user.id, session.id)
    db.delete(session)
    db.commit()

    return ApiResponse(success=True, message="Session deleted successfully")


# ============ Lap Routes ============


@router.get("/{session_id}/laps", response_model=List[LapResponse])
def list_laps(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List laps for a session."""
    session = _resolve_session(db, current_user.id, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return [build_lap_response(lap) for lap in _ordered_laps(session.laps)]


@router.post("/{session_id}/laps", response_model=LapResponse)
def create_lap(
    session_id: str,
    request: CreateLapRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update a lap using the client UUID as an idempotency key."""
    session = _resolve_session(db, current_user.id, session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    db_lap = None
    if request.lapUuid:
        db_lap = (
            db.query(Lap)
            .filter(
                Lap.user_id == current_user.id,
                Lap.session_id == session.id,
                Lap.lap_uuid == request.lapUuid,
            )
            .first()
        )

    if db_lap is None:
        next_lap_number = (
            db.query(func.max(Lap.lap_number)).filter(Lap.session_id == session.id).scalar()
            or 0
        ) + 1
        db_lap = Lap(
            user_id=current_user.id,
            session_id=session.id,
            lap_number=next_lap_number,
            is_active=request.endedAt is None,
        )
        db.add(db_lap)

    _apply_lap_fields(db_lap, request, creating=True)
    db.flush()
    _recalculate_session_rollup(db, session)
    db.commit()
    db.refresh(db_lap)

    return build_lap_response(db_lap)


@router.put("/{session_id}/laps/{lap_id}", response_model=LapResponse)
def update_lap(
    session_id: str,
    lap_id: str,
    request: UpdateLapRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a lap by database ID or lap UUID."""
    session = _resolve_session(db, current_user.id, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    lap = _resolve_lap(db, current_user.id, session.id, lap_id)
    if not lap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lap not found",
        )

    _apply_lap_fields(lap, request)
    _recalculate_session_rollup(db, session)
    db.commit()
    db.refresh(lap)

    return build_lap_response(lap)


@router.delete("/{session_id}/laps/{lap_id}")
def delete_lap(
    session_id: str,
    lap_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a lap."""
    session = _resolve_session(db, current_user.id, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    lap = _resolve_lap(db, current_user.id, session.id, lap_id)
    if not lap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lap not found",
        )

    from app.services.minio_service import delete_lap_images

    delete_lap_images(current_user.id, session.id, lap.id)
    db.delete(lap)
    db.flush()
    _recalculate_session_rollup(db, session)
    db.commit()

    return ApiResponse(success=True, message="Lap deleted successfully")
