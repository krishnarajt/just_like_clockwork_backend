import os
import io
import logging
from typing import Optional
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

logger = logging.getLogger(__name__)

# MinIO bucket name - exported for use in routes
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "clockwork-images")


class MinIOService:
    """Service for managing image storage in MinIO"""
    
    def __init__(self):
        # MinIO Configuration from environment variables
        self.endpoint_url = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.bucket_name = MINIO_BUCKET
        self.region = os.getenv("MINIO_REGION", "us-east-1")
        self._client = None
        self._initialized = False
    
    @property
    def client(self):
        """Lazy-init the S3 client so the app doesn't crash if MinIO is down at startup"""
        if self._client is None:
            self._client = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                config=Config(signature_version='s3v4')
            )
        if not self._initialized:
            self._ensure_bucket_exists()
            self._initialized = True
        return self._client
    
    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist. Non-fatal if MinIO is unreachable."""
        try:
            self._client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ('404', 'NoSuchBucket'):
                try:
                    self._client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created MinIO bucket: {self.bucket_name}")
                except ClientError as create_err:
                    logger.error(f"Error creating bucket: {create_err}")
            else:
                logger.warning(f"Could not verify MinIO bucket: {e}")
        except Exception as e:
            # Connection errors, DNS failures, etc. — don't crash the app
            logger.warning(f"MinIO not reachable during bucket check: {e}")
    
    def upload_image_bytes(
        self, 
        file_data: bytes, 
        object_key: str, 
        content_type: str = "image/jpeg"
    ) -> bool:
        """
        Upload an image to MinIO from raw bytes
        
        Args:
            file_data: Image file data as bytes
            object_key: Path/key in MinIO
            content_type: MIME type of the image
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=io.BytesIO(file_data),
                ContentType=content_type
            )
            return True
        except ClientError as e:
            logger.error(f"Error uploading image: {e}")
            return False
    
    def upload_image_fileobj(
        self,
        file_obj,
        object_key: str,
        content_type: str = "image/jpeg"
    ) -> bool:
        """
        Upload an image to MinIO from a file-like object
        
        Args:
            file_obj: File-like object (e.g. from UploadFile.file)
            object_key: Path/key in MinIO
            content_type: MIME type of the image
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_key,
                ExtraArgs={'ContentType': content_type}
            )
            return True
        except ClientError as e:
            logger.error(f"Error uploading image: {e}")
            return False
    
    def get_presigned_url(
        self, 
        object_key: str, 
        expiration: int = 3600
    ) -> Optional[str]:
        """
        Generate a presigned URL for an image
        
        Args:
            object_key: Path/key in MinIO
            expiration: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            Presigned URL as string, or None if error
        """
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': object_key
                },
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None
    
    def delete_object(self, object_key: str) -> bool:
        """
        Delete an image from MinIO
        
        Args:
            object_key: Path/key in MinIO
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            return True
        except ClientError as e:
            logger.error(f"Error deleting image: {e}")
            return False
    
    def delete_objects_batch(self, object_keys: list) -> bool:
        """
        Delete multiple images from MinIO
        
        Args:
            object_keys: List of paths/keys in MinIO
            
        Returns:
            True if successful, False otherwise
        """
        if not object_keys:
            return True
        try:
            objects = [{'Key': key} for key in object_keys]
            self.client.delete_objects(
                Bucket=self.bucket_name,
                Delete={'Objects': objects}
            )
            return True
        except ClientError as e:
            logger.error(f"Error batch deleting images: {e}")
            return False
    
    def list_objects(self, prefix: str) -> list:
        """
        List all objects with a given prefix
        
        Args:
            prefix: Prefix to filter (e.g., "user_id/session_id/")
            
        Returns:
            List of object keys
        """
        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                return []
            
            return [obj['Key'] for obj in response['Contents']]
        except ClientError as e:
            logger.error(f"Error listing objects: {e}")
            return []


# Singleton instance
_minio_service = None


def get_minio_service() -> MinIOService:
    """Get or create MinIO service instance"""
    global _minio_service
    if _minio_service is None:
        _minio_service = MinIOService()
    return _minio_service


# ============ Standalone helper functions (used by routes) ============

def generate_presigned_url(object_key: str, expiration: int = 3600) -> Optional[str]:
    """Generate a presigned URL for an object in MinIO"""
    try:
        service = get_minio_service()
        return service.get_presigned_url(object_key, expiration)
    except Exception as e:
        logger.error(f"Error in generate_presigned_url: {e}")
        return None


def upload_image(
    file_obj,
    user_id: int,
    session_id: int,
    lap_id: int,
    image_uuid: str,
    file_extension: str,
    content_type: str = "image/jpeg"
) -> str:
    """
    Upload an image for a specific lap.
    Constructs the MinIO object key and uploads the file.
    
    Returns:
        The object key (path) in MinIO
    """
    object_key = f"{user_id}/{session_id}/{lap_id}_{image_uuid}.{file_extension}"
    service = get_minio_service()
    success = service.upload_image_fileobj(file_obj, object_key, content_type)
    if not success:
        raise Exception(f"Failed to upload image to MinIO: {object_key}")
    return object_key


def delete_image(object_key: str) -> bool:
    """Delete a single image from MinIO by its object key"""
    try:
        service = get_minio_service()
        return service.delete_object(object_key)
    except Exception as e:
        logger.error(f"Error in delete_image: {e}")
        return False


def delete_session_images(user_id: int, session_id: int) -> bool:
    """Delete all images for a session from MinIO"""
    try:
        service = get_minio_service()
        prefix = f"{user_id}/{session_id}/"
        keys = service.list_objects(prefix)
        if keys:
            return service.delete_objects_batch(keys)
        return True
    except Exception as e:
        logger.error(f"Error in delete_session_images: {e}")
        return False


def delete_lap_images(user_id: int, session_id: int, lap_id: int) -> bool:
    """Delete all images for a specific lap from MinIO"""
    try:
        service = get_minio_service()
        # Lap images have keys like: user_id/session_id/lap_id_*.ext
        prefix = f"{user_id}/{session_id}/{lap_id}_"
        keys = service.list_objects(prefix)
        if keys:
            return service.delete_objects_batch(keys)
        return True
    except Exception as e:
        logger.error(f"Error in delete_lap_images: {e}")
        return False
