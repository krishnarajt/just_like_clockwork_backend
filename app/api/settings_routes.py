from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User, UserSettings
from app.api.dependencies import get_current_user
from app.api.schemas import UserSettingsResponse, UpdateSettingsRequest, ApiResponse

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/", response_model=UserSettingsResponse)
def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user settings"""
    settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not settings:
        # Create default settings if they don't exist
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return UserSettingsResponse(
        showAmount=settings.show_amount,
        showStatsBeforeLaps=settings.show_stats_before_laps,
        breaksImpactAmount=settings.breaks_impact_amount,
        breaksImpactTime=settings.breaks_impact_time,
        minimalistMode=settings.minimalist_mode,
        notificationEnabled=settings.notification_enabled,
        notificationIntervalHours=settings.notification_interval_hours,
        hourlyAmount=settings.hourly_amount,
    )


@router.put("/", response_model=UserSettingsResponse)
def update_settings(
    request: UpdateSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user settings"""
    settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not settings:
        # Create settings if they don't exist
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
    
    # Update fields if provided
    if request.showAmount is not None:
        settings.show_amount = request.showAmount
    if request.showStatsBeforeLaps is not None:
        settings.show_stats_before_laps = request.showStatsBeforeLaps
    if request.breaksImpactAmount is not None:
        settings.breaks_impact_amount = request.breaksImpactAmount
    if request.breaksImpactTime is not None:
        settings.breaks_impact_time = request.breaksImpactTime
    if request.minimalistMode is not None:
        settings.minimalist_mode = request.minimalistMode
    if request.notificationEnabled is not None:
        settings.notification_enabled = request.notificationEnabled
    if request.notificationIntervalHours is not None:
        settings.notification_interval_hours = request.notificationIntervalHours
    if request.hourlyAmount is not None:
        settings.hourly_amount = request.hourlyAmount
    
    db.commit()
    db.refresh(settings)
    
    return UserSettingsResponse(
        showAmount=settings.show_amount,
        showStatsBeforeLaps=settings.show_stats_before_laps,
        breaksImpactAmount=settings.breaks_impact_amount,
        breaksImpactTime=settings.breaks_impact_time,
        minimalistMode=settings.minimalist_mode,
        notificationEnabled=settings.notification_enabled,
        notificationIntervalHours=settings.notification_interval_hours,
        hourlyAmount=settings.hourly_amount,
    )


@router.delete("/")
def reset_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reset settings to defaults"""
    settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if settings:
        # Reset to defaults
        settings.show_amount = True
        settings.show_stats_before_laps = False
        settings.breaks_impact_amount = False
        settings.breaks_impact_time = False
        settings.minimalist_mode = False
        settings.notification_enabled = True
        settings.notification_interval_hours = 2.0
        settings.hourly_amount = 450.0
        
        db.commit()
    
    return ApiResponse(success=True, message="Settings reset to defaults")
