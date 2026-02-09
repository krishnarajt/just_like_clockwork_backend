from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List
import uuid
import os
import logging

from app.db.database import get_db
from app.db.models import User, Session as DBSession, Lap, Image as DBImage
from app.api.dependencies import get_current_user
from app.api.schemas import ImageResponse, ApiResponse
from app.services.minio_service import upload_image, delete_image, generate_presigned_url, MINIO_BUCKET

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["Images"])

# Allowed image extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

# Max file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024


def get_file_extension(filename: str) -> str:
    """Get file extension from filename"""
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''


def is_allowed_file(filename: str) -> bool:
    """Check if file has allowed extension"""
    return get_file_extension(filename) in ALLOWED_EXTENSIONS


def _serialize_datetime(dt):
    """Safely serialize a datetime to ISO string"""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


@router.post("/sessions/{session_id}/laps/{lap_id}/upload", response_model=ImageResponse)
async def upload_lap_image(
    session_id: int,
    lap_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload an image for a lap"""
    
    # Verify lap exists and belongs to user
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
    
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided"
        )
    
    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Check file size
    contents = await file.read()
    file_size = len(contents)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Max size: {MAX_FILE_SIZE / (1024*1024):.1f}MB"
        )
    
    # Reset file position
    await file.seek(0)
    
    # Generate image UUID
    image_uuid = str(uuid.uuid4())
    file_extension = get_file_extension(file.filename)
    
    # Upload to MinIO
    try:
        minio_key = upload_image(
            file.file,
            current_user.id,
            session_id,
            lap_id,
            image_uuid,
            file_extension,
            file.content_type or 'application/octet-stream'
        )
        
        # Create image record in database
        db_image = DBImage(
            image_uuid=image_uuid,
            user_id=current_user.id,
            session_id=session_id,
            lap_id=lap_id,
            image_name=file.filename,
            minio_object_key=minio_key,
            minio_bucket=MINIO_BUCKET,
            file_size=file_size,
            file_format=file_extension,
            mime_type=file.content_type
        )
        
        db.add(db_image)
        db.commit()
        db.refresh(db_image)
        
        # Generate presigned URL
        presigned_url = generate_presigned_url(minio_key, expiration=3600)
        
        return ImageResponse(
            imageId=db_image.image_uuid,
            imageName=db_image.image_name,
            lapId=db_image.lap_id,
            url=presigned_url,
            mimeType=db_image.mime_type,
            fileSize=db_image.file_size,
            createdAt=_serialize_datetime(db_image.created_at)
        )
        
    except Exception as e:
        logger.error(f"Failed to upload image: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload image: {str(e)}"
        )


@router.get("/sessions/{session_id}/laps/{lap_id}", response_model=List[ImageResponse])
def get_lap_images(
    session_id: int,
    lap_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all images for a lap"""
    
    # Verify lap exists and belongs to user
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
    
    # Get images
    images = db.query(DBImage).filter(
        and_(
            DBImage.lap_id == lap_id,
            DBImage.session_id == session_id,
            DBImage.user_id == current_user.id
        )
    ).all()
    
    # Generate presigned URLs
    result = []
    for img in images:
        presigned_url = generate_presigned_url(img.minio_object_key, expiration=3600)
        if presigned_url:
            result.append(ImageResponse(
                imageId=img.image_uuid,
                imageName=img.image_name,
                lapId=img.lap_id,
                url=presigned_url,
                mimeType=img.mime_type,
                fileSize=img.file_size,
                createdAt=_serialize_datetime(img.created_at)
            ))
    
    return result


@router.get("/sessions/{session_id}", response_model=List[ImageResponse])
def get_session_images(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all images for a session"""
    
    # Verify session exists and belongs to user
    session = db.query(DBSession).filter(
        and_(
            DBSession.id == session_id,
            DBSession.user_id == current_user.id
        )
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Get all images for this session
    images = db.query(DBImage).filter(
        and_(
            DBImage.session_id == session_id,
            DBImage.user_id == current_user.id
        )
    ).all()
    
    # Generate presigned URLs
    result = []
    for img in images:
        presigned_url = generate_presigned_url(img.minio_object_key, expiration=3600)
        if presigned_url:
            result.append(ImageResponse(
                imageId=img.image_uuid,
                imageName=img.image_name,
                lapId=img.lap_id,
                url=presigned_url,
                mimeType=img.mime_type,
                fileSize=img.file_size,
                createdAt=_serialize_datetime(img.created_at)
            ))
    
    return result


@router.delete("/{image_id}")
def delete_image_endpoint(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an image"""
    
    # Find image
    image = db.query(DBImage).filter(
        and_(
            DBImage.image_uuid == image_id,
            DBImage.user_id == current_user.id
        )
    ).first()
    
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    # Delete from MinIO
    try:
        delete_image(image.minio_object_key)
    except Exception as e:
        # Log error but continue with database deletion
        logger.error(f"Failed to delete image from MinIO: {e}")
    
    # Delete from database
    db.delete(image)
    db.commit()
    
    return ApiResponse(success=True, message="Image deleted successfully")
