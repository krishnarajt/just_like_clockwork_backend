from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.schemas import CreateLapRequest, CreateSessionRequest, UpdateLapRequest
from app.api.session_routes import create_lap, create_session, list_laps, list_sessions, update_lap
from app.db.database import Base
from app.db.models import Lap, Session as DBSession, User


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'clockwork_test.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    user = User(username="sync-user", password_hash="not-used")
    db.add(user)
    db.commit()
    db.refresh(user)

    try:
        yield db, user
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_session_and_lap_sync_are_idempotent(db_session):
    db, user = db_session

    created = create_session(
        CreateSessionRequest(
            sessionUuid="local-session-1",
            sessionName="Local session",
            startedAt="2026-05-02T10:00:00Z",
            isCompleted=False,
        ),
        current_user=user,
        db=db,
    )
    same_session = create_session(
        CreateSessionRequest(
            sessionUuid="local-session-1",
            sessionName="Renamed session",
            startedAt="2026-05-02T10:00:00Z",
        ),
        current_user=user,
        db=db,
    )

    assert same_session["id"] == created["id"]
    assert db.query(DBSession).filter_by(user_id=user.id).count() == 1
    assert same_session["sessionName"] == "Renamed session"

    first_lap = create_lap(
        str(created["id"]),
        CreateLapRequest(
            lapUuid="local-lap-1",
            lapName="Initial work",
            startedAt="2026-05-02T10:00:00Z",
            endedAt="2026-05-02T10:30:00Z",
            duration=1800,
            current_hours=0,
            current_minutes=30,
            current_seconds=0,
            isBreakLap=False,
            hourlyAmount=120,
        ),
        current_user=user,
        db=db,
    )
    updated_lap = create_lap(
        str(created["id"]),
        CreateLapRequest(
            lapUuid="local-lap-1",
            lapName="Updated work",
            startedAt="2026-05-02T10:00:00Z",
            endedAt="2026-05-02T10:45:00Z",
            duration=2700,
            current_hours=0,
            current_minutes=45,
            current_seconds=0,
            isBreakLap=True,
            hourlyAmount=200,
        ),
        current_user=user,
        db=db,
    )

    assert updated_lap["id"] == first_lap["id"]
    assert updated_lap["lapUuid"] == "local-lap-1"
    assert updated_lap["lapName"] == "Updated work"
    assert updated_lap["duration"] == 2700
    assert updated_lap["currentMinutes"] == 45
    assert updated_lap["isBreakLap"] is True
    assert updated_lap["hourlyAmount"] == 200
    assert db.query(Lap).filter_by(session_id=created["id"]).count() == 1

    sessions = list_sessions(
        limit=50,
        offset=0,
        start_date=None,
        end_date=None,
        is_completed=None,
        current_user=user,
        db=db,
    )
    assert len(sessions) == 1
    assert sessions[0]["sessionUuid"] == "local-session-1"
    assert sessions[0]["lapCount"] == 1
    assert sessions[0]["totalDuration"] == 2700
    assert sessions[0]["totalSeconds"] == 2700
    assert sessions[0]["totalAmount"] == 150


def test_lap_update_persists_live_sync_fields_and_rollups(db_session):
    db, user = db_session
    session = create_session(
        CreateSessionRequest(sessionUuid="session-live", startedAt="2026-05-02T11:00:00Z"),
        current_user=user,
        db=db,
    )
    lap = create_lap(
        str(session["id"]),
        CreateLapRequest(
            lapUuid="lap-live",
            lapName="Live lap",
            startedAt="2026-05-02T11:00:00Z",
        ),
        current_user=user,
        db=db,
    )

    updated = update_lap(
        str(session["id"]),
        str(lap["id"]),
        UpdateLapRequest(
            workDoneString="Finished live lap",
            endedAt=datetime(2026, 5, 2, 11, 10, tzinfo=timezone.utc).isoformat(),
            currentMinutes=10,
            duration=600,
            isBreakLap=True,
            hourlyAmount=90,
        ),
        current_user=user,
        db=db,
    )

    assert updated["workDoneString"] == "Finished live lap"
    assert updated["currentMinutes"] == 10
    assert updated["duration"] == 600
    assert updated["isBreakLap"] is True

    laps = list_laps("session-live", current_user=user, db=db)
    assert len(laps) == 1
    assert laps[0]["lapUuid"] == "lap-live"
    assert laps[0]["hourlyAmount"] == 90

    sessions = list_sessions(
        limit=50,
        offset=0,
        start_date=None,
        end_date=None,
        is_completed=None,
        current_user=user,
        db=db,
    )
    assert sessions[0]["lapCount"] == 1
    assert sessions[0]["totalDuration"] == 600
    assert sessions[0]["totalAmount"] == 15


def test_idempotent_session_create_does_not_reset_completion_state(db_session):
    db, user = db_session
    created = create_session(
        CreateSessionRequest(
            sessionUuid="completed-session",
            sessionName="Done",
            startedAt="2026-05-02T12:00:00Z",
            endedAt="2026-05-02T12:30:00Z",
            totalDuration=1800,
            isCompleted=True,
        ),
        current_user=user,
        db=db,
    )

    updated = create_session(
        CreateSessionRequest(
            sessionUuid="completed-session",
            sessionName="Still done",
            startedAt="2026-05-02T12:00:00Z",
        ),
        current_user=user,
        db=db,
    )

    assert updated["id"] == created["id"]
    assert updated["isCompleted"] is True
    assert updated["isActive"] is False
    assert updated["totalDuration"] == 1800
