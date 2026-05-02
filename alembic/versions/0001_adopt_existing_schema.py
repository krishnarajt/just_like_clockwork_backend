"""adopt existing clockwork schema

Revision ID: 0001_adopt_existing_schema
Revises:
Create Date: 2026-05-02

This baseline migration is deliberately non-destructive. It can initialize a
fresh database, and it can adopt a database previously created by SQLAlchemy
create_all() without dropping or rewriting existing data.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_adopt_existing_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _now_default():
    if _dialect_name() == "sqlite":
        return sa.text("CURRENT_TIMESTAMP")
    return sa.text("now()")


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _columns(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    inspector = _inspector()
    names = {index["name"] for index in inspector.get_indexes(table_name)}
    names.update(
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    )
    return names


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if index_name not in _indexes(table_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _create_users() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now_default()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index_if_missing("ix_users_id", "users", ["id"])
    _create_index_if_missing("ix_users_username", "users", ["username"], unique=True)


def _ensure_users() -> None:
    if not _table_exists("users"):
        _create_users()
        return
    _add_column_if_missing("users", sa.Column("username", sa.String(length=100), nullable=True))
    _add_column_if_missing("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    _add_column_if_missing("users", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    _create_index_if_missing("ix_users_id", "users", ["id"])
    _create_index_if_missing("ix_users_username", "users", ["username"], unique=True)


def _create_refresh_tokens() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now_default()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index_if_missing("ix_refresh_tokens_id", "refresh_tokens", ["id"])
    _create_index_if_missing("ix_refresh_tokens_token", "refresh_tokens", ["token"], unique=True)


def _ensure_refresh_tokens() -> None:
    if not _table_exists("refresh_tokens"):
        _create_refresh_tokens()
        return
    _add_column_if_missing("refresh_tokens", sa.Column("user_id", sa.Integer(), nullable=True))
    _add_column_if_missing("refresh_tokens", sa.Column("token", sa.String(length=500), nullable=True))
    _add_column_if_missing("refresh_tokens", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("refresh_tokens", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    _create_index_if_missing("ix_refresh_tokens_id", "refresh_tokens", ["id"])
    _create_index_if_missing("ix_refresh_tokens_token", "refresh_tokens", ["token"], unique=True)


def _create_sessions() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_uuid", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_name", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lap_count", sa.Integer(), nullable=True),
        sa.Column("total_seconds", sa.Integer(), nullable=True),
        sa.Column("total_duration", sa.Integer(), nullable=True),
        sa.Column("total_amount", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now_default()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index_if_missing("ix_sessions_id", "sessions", ["id"])
    _create_index_if_missing("ix_sessions_session_uuid", "sessions", ["session_uuid"], unique=True)


def _ensure_sessions() -> None:
    if not _table_exists("sessions"):
        _create_sessions()
        return
    _add_column_if_missing("sessions", sa.Column("session_uuid", sa.String(length=36), nullable=True))
    _add_column_if_missing("sessions", sa.Column("user_id", sa.Integer(), nullable=True))
    _add_column_if_missing("sessions", sa.Column("session_name", sa.String(length=200), nullable=True))
    _add_column_if_missing("sessions", sa.Column("description", sa.Text(), nullable=True))
    _add_column_if_missing("sessions", sa.Column("start_time", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("sessions", sa.Column("end_time", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("sessions", sa.Column("lap_count", sa.Integer(), nullable=True))
    _add_column_if_missing("sessions", sa.Column("total_seconds", sa.Integer(), nullable=True))
    _add_column_if_missing("sessions", sa.Column("total_duration", sa.Integer(), nullable=True))
    _add_column_if_missing("sessions", sa.Column("total_amount", sa.Float(), nullable=True))
    _add_column_if_missing("sessions", sa.Column("is_active", sa.Boolean(), nullable=True))
    _add_column_if_missing("sessions", sa.Column("is_completed", sa.Boolean(), nullable=True))
    _add_column_if_missing("sessions", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("sessions", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    _create_index_if_missing("ix_sessions_id", "sessions", ["id"])
    _create_index_if_missing("ix_sessions_session_uuid", "sessions", ["session_uuid"], unique=True)


def _create_laps() -> None:
    op.create_table(
        "laps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lap_uuid", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=True),
        sa.Column("lap_name", sa.String(length=500), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("current_hours", sa.Integer(), nullable=True),
        sa.Column("current_minutes", sa.Integer(), nullable=True),
        sa.Column("current_seconds", sa.Integer(), nullable=True),
        sa.Column("work_done_string", sa.Text(), nullable=True),
        sa.Column("is_break_lap", sa.Boolean(), nullable=True),
        sa.Column("hourly_amount", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now_default()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index_if_missing("ix_laps_id", "laps", ["id"])
    _create_index_if_missing("ix_laps_lap_uuid", "laps", ["lap_uuid"], unique=True)


def _ensure_laps() -> None:
    if not _table_exists("laps"):
        _create_laps()
        return
    _add_column_if_missing("laps", sa.Column("lap_uuid", sa.String(length=36), nullable=True))
    _add_column_if_missing("laps", sa.Column("user_id", sa.Integer(), nullable=True))
    _add_column_if_missing("laps", sa.Column("session_id", sa.Integer(), nullable=True))
    _add_column_if_missing("laps", sa.Column("lap_number", sa.Integer(), nullable=True))
    _add_column_if_missing("laps", sa.Column("lap_name", sa.String(length=500), nullable=True))
    _add_column_if_missing("laps", sa.Column("start_time", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("laps", sa.Column("end_time", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("laps", sa.Column("duration", sa.Integer(), nullable=True))
    _add_column_if_missing("laps", sa.Column("is_active", sa.Boolean(), nullable=True))
    _add_column_if_missing("laps", sa.Column("current_hours", sa.Integer(), nullable=True))
    _add_column_if_missing("laps", sa.Column("current_minutes", sa.Integer(), nullable=True))
    _add_column_if_missing("laps", sa.Column("current_seconds", sa.Integer(), nullable=True))
    _add_column_if_missing("laps", sa.Column("work_done_string", sa.Text(), nullable=True))
    _add_column_if_missing("laps", sa.Column("is_break_lap", sa.Boolean(), nullable=True))
    _add_column_if_missing("laps", sa.Column("hourly_amount", sa.Float(), nullable=True))
    _add_column_if_missing("laps", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("laps", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    _create_index_if_missing("ix_laps_id", "laps", ["id"])
    _create_index_if_missing("ix_laps_lap_uuid", "laps", ["lap_uuid"], unique=True)


def _create_images() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("image_uuid", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("lap_id", sa.Integer(), nullable=False),
        sa.Column("image_name", sa.String(length=300), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("file_format", sa.String(length=10), nullable=True),
        sa.Column("minio_object_key", sa.String(length=500), nullable=False),
        sa.Column("minio_bucket", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now_default()),
        sa.ForeignKeyConstraint(["lap_id"], ["laps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index_if_missing("ix_images_id", "images", ["id"])
    _create_index_if_missing("ix_images_image_uuid", "images", ["image_uuid"], unique=True)


def _ensure_images() -> None:
    if not _table_exists("images"):
        _create_images()
        return
    _add_column_if_missing("images", sa.Column("image_uuid", sa.String(length=36), nullable=True))
    _add_column_if_missing("images", sa.Column("user_id", sa.Integer(), nullable=True))
    _add_column_if_missing("images", sa.Column("session_id", sa.Integer(), nullable=True))
    _add_column_if_missing("images", sa.Column("lap_id", sa.Integer(), nullable=True))
    _add_column_if_missing("images", sa.Column("image_name", sa.String(length=300), nullable=True))
    _add_column_if_missing("images", sa.Column("mime_type", sa.String(length=100), nullable=True))
    _add_column_if_missing("images", sa.Column("file_size", sa.Integer(), nullable=True))
    _add_column_if_missing("images", sa.Column("file_format", sa.String(length=10), nullable=True))
    _add_column_if_missing("images", sa.Column("minio_object_key", sa.String(length=500), nullable=True))
    _add_column_if_missing("images", sa.Column("minio_bucket", sa.String(length=100), nullable=True))
    _add_column_if_missing("images", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    _create_index_if_missing("ix_images_id", "images", ["id"])
    _create_index_if_missing("ix_images_image_uuid", "images", ["image_uuid"], unique=True)


def _create_user_settings() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("show_amount", sa.Boolean(), nullable=True),
        sa.Column("show_stats_before_laps", sa.Boolean(), nullable=True),
        sa.Column("breaks_impact_amount", sa.Boolean(), nullable=True),
        sa.Column("breaks_impact_time", sa.Boolean(), nullable=True),
        sa.Column("minimalist_mode", sa.Boolean(), nullable=True),
        sa.Column("notification_enabled", sa.Boolean(), nullable=True),
        sa.Column("notification_interval_hours", sa.Float(), nullable=True),
        sa.Column("hourly_amount", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now_default()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    _create_index_if_missing("ix_user_settings_id", "user_settings", ["id"])


def _ensure_user_settings() -> None:
    if not _table_exists("user_settings"):
        _create_user_settings()
        return
    _add_column_if_missing("user_settings", sa.Column("user_id", sa.Integer(), nullable=True))
    _add_column_if_missing("user_settings", sa.Column("show_amount", sa.Boolean(), nullable=True))
    _add_column_if_missing("user_settings", sa.Column("show_stats_before_laps", sa.Boolean(), nullable=True))
    _add_column_if_missing("user_settings", sa.Column("breaks_impact_amount", sa.Boolean(), nullable=True))
    _add_column_if_missing("user_settings", sa.Column("breaks_impact_time", sa.Boolean(), nullable=True))
    _add_column_if_missing("user_settings", sa.Column("minimalist_mode", sa.Boolean(), nullable=True))
    _add_column_if_missing("user_settings", sa.Column("notification_enabled", sa.Boolean(), nullable=True))
    _add_column_if_missing("user_settings", sa.Column("notification_interval_hours", sa.Float(), nullable=True))
    _add_column_if_missing("user_settings", sa.Column("hourly_amount", sa.Float(), nullable=True))
    _add_column_if_missing("user_settings", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("user_settings", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    _create_index_if_missing("ix_user_settings_id", "user_settings", ["id"])


def upgrade() -> None:
    _ensure_users()
    _ensure_refresh_tokens()
    _ensure_sessions()
    _ensure_laps()
    _ensure_images()
    _ensure_user_settings()


def downgrade() -> None:
    # This baseline intentionally has no destructive downgrade. The app's
    # production data should never be dropped by a migration rollback.
    pass
