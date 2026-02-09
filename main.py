import logging
import logging.handlers
import sys
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db
from app.api.auth_routes import router as auth_router
from app.api.session_routes import router as session_router
from app.api.image_routes import router as image_router
from app.api.settings_routes import router as settings_router


# Configure logging
def setup_logging():
    """Configure application-wide logging"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            # Console handler
            logging.StreamHandler(sys.stdout),
            # File handler - rotates daily at midnight, keeps 30 days
            logging.handlers.TimedRotatingFileHandler(
                "logs/app.log",
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8",
            ),
        ],
    )

    # Set specific log levels for noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured at {log_level} level")
    return logger


logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("=" * 60)
    logger.info("Starting Just Like Clockwork Backend...")
    logger.info("=" * 60)

    # Initialize database
    try:
        init_db()
        logger.info("✓ Database initialized successfully")
    except Exception as e:
        logger.critical(f"✗ Failed to initialize database: {e}", exc_info=True)
        raise

    # Check MinIO configuration
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "")
    if minio_endpoint:
        logger.info(f"✓ MinIO configured at {minio_endpoint}")
    else:
        logger.warning("⚠ MINIO_ENDPOINT not set - using default localhost:9000")

    logger.info("=" * 60)
    logger.info("Just Like Clockwork Backend is ready!")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("=" * 60)
    logger.info("Shutting down Just Like Clockwork Backend...")
    logger.info("=" * 60)


# Create FastAPI app
app = FastAPI(
    title="Just Like Clockwork Backend",
    description="Backend API for Just Like Clockwork time tracking app",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info(f"CORS enabled for origins: {cors_origins}")

# Include routers
app.include_router(auth_router, prefix="/api")
app.include_router(session_router, prefix="/api")
app.include_router(image_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
logger.info("API routers registered")


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "name": "Just Like Clockwork Backend",
        "description": "Time tracking backend API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
def health_check():
    """Health check endpoint for k8s"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/ready")
def readiness_check():
    """Readiness check endpoint for k8s"""
    return {"status": "ready", "timestamp": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() == "true"

    logger.info(f"Starting server on port {port}, reload={reload}")

    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload, log_level="info")
