import os
import sqlite3
import subprocess
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def _run_python(args, database_url):
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["PYTHONPATH"] = PROJECT_ROOT
    return subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _table_names(db_path):
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def test_alembic_upgrade_creates_fresh_database(tmp_path):
    db_path = tmp_path / "fresh.db"
    database_url = f"sqlite:///{db_path}"

    _run_python(["-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], database_url)

    tables = _table_names(db_path)
    assert {
        "alembic_version",
        "users",
        "refresh_tokens",
        "sessions",
        "laps",
        "images",
        "user_settings",
    }.issubset(tables)


def test_alembic_upgrade_adopts_existing_create_all_database(tmp_path):
    db_path = tmp_path / "existing.db"
    database_url = f"sqlite:///{db_path}"

    _run_python(
        [
            "-c",
            (
                "from app.db.database import Base, engine; "
                "import app.db.models; "
                "Base.metadata.create_all(bind=engine)"
            ),
        ],
        database_url,
    )
    before_tables = _table_names(db_path)

    _run_python(["-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], database_url)

    after_tables = _table_names(db_path)
    assert before_tables.issubset(after_tables)
    assert "alembic_version" in after_tables
