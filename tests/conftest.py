"""Shared fixtures. Every test gets its own temporary SQLite database, so the real project DB is never touched."""
import pytest

from src.database import init_db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test_sales.db"
    init_db(path)
    return path
