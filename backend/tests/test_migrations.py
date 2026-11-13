import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.database.session import engine

EXPECTED_TABLES = {"users", "documents", "document_chunks", "conversations", "messages", "citations",
                   "user_feedback", "document_categories", "processing_jobs", "audit_logs"}


def _cfg():
    return Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))


def test_all_ten_tables_exist():
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_migration_roundtrip():
    command.downgrade(_cfg(), "base")
    assert not (EXPECTED_TABLES & set(inspect(engine).get_table_names()))
    command.upgrade(_cfg(), "head")
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
