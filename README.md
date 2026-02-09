# Just Like Clockwork Backend

Backend API for Just Like Clockwork time tracking application.

## Features

- **Authentication**: JWT-based authentication with access and refresh tokens
- **Sessions Management**: Create, read, update, delete work sessions with laps
- **Image Storage**: Upload and store images in MinIO with presigned URLs
- **User Settings**: Manage user preferences and settings
- **RESTful API**: Clean and well-documented API endpoints
- **PostgreSQL**: Robust database with proper relationships
- **Kubernetes Ready**: Full K8s deployment configuration

## Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Object Storage**: MinIO (S3-compatible)
- **Authentication**: JWT with PBKDF2 password hashing
- **Container**: Docker
- **Orchestration**: Kubernetes
- **Secrets Management**: External Secrets Operator with Vault

## API Endpoints

### Authentication
- `POST /api/auth/signup` - Create new user account
- `POST /api/auth/login` - Login with credentials
- `POST /api/auth/refresh` - Refresh access token
- `POST /api/auth/logout` - Logout and revoke refresh token

### Sessions
- `POST /api/sessions` - Create a new session
- `GET /api/sessions` - Get all sessions (paginated)
- `GET /api/sessions/latest` - Get most recent session
- `GET /api/sessions/{session_uuid}` - Get specific session with laps and images
- `PUT /api/sessions/{session_uuid}` - Update session
- `DELETE /api/sessions/{session_uuid}` - Delete session
- `GET /api/sessions/by-date` - Get sessions by date range

### Images
- `POST /api/images/upload` - Upload image for a lap
- `GET /api/images/{image_uuid}` - Get presigned URL for image
- `DELETE /api/images/{image_uuid}` - Delete image

### Settings
- `GET /api/settings` - Get user settings
- `PUT /api/settings` - Update user settings

## Local Development

1. **Install dependencies**: `pip install -r requirements.txt`
2. **Configure environment**: Copy `.env.example` to `.env` and update values
3. **Run application**: `python main.py`

API documentation available at: `http://localhost:8000/docs`

## Kubernetes Deployment

### Required Secrets in Vault

Path: `apps/just-like-clockwork-backend/just-like-clockwork-backend/env`

Required secrets:
- DATABASE_URL
- SECRET_KEY
- MINIO_ENDPOINT
- MINIO_ACCESS_KEY
- MINIO_SECRET_KEY
- CORS_ORIGINS

### Deploy

```bash
kubectl create namespace just-like-clockwork-backend
kubectl apply -k k8s/overlays/prod
```

Service exposed on NodePort 32004.

## Image Storage

Images stored in MinIO: `/{user_id}/{session_id}/{lap_uuid}_{image_uuid}.{format}`

## Health Checks

- `GET /health` - Liveness probe
- `GET /ready` - Readiness probe
- `GET /` - API status
