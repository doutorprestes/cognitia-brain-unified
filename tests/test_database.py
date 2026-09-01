"""Tests for UnifiedDatabase."""

import os
import pytest
import tempfile
from src.shared.database import UnifiedDatabase


@pytest.fixture
def db():
    """Create temp database for tests."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db = UnifiedDatabase(db_path)
    yield db
    os.unlink(db_path)


def test_create_database(db):
    """Test database creation."""
    assert db is not None


def test_insert_item(db):
    """Test item insertion."""
    item = {'title': 'Test Grant', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    assert db.insert_item(item) is True


def test_insert_duplicate(db):
    """Test duplicate insertion returns False."""
    item = {'title': 'Test Grant', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    assert db.insert_item(item) is False


def test_exists(db):
    """Test exists check."""
    item = {'title': 'Test Grant', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    item_hash = db.hash_item(item['title'], item['url'])
    assert db.exists(item_hash) is True


def test_get_unnotified(db):
    """Test get unnotified items."""
    item = {'title': 'Test Grant', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    unnotified = db.get_unnotified()
    assert len(unnotified) == 1


def test_mark_notified(db):
    """Test mark as notified."""
    item = {'title': 'Test Grant', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    item_hash = db.hash_item(item['title'], item['url'])
    db.mark_notified(item_hash)
    unnotified = db.get_unnotified()
    assert len(unnotified) == 0


def test_save_feedback(db):
    """Test save feedback."""
    item = {'title': 'Test Grant', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    item_hash = db.hash_item(item['title'], item['url'])
    db.save_feedback(item_hash, 1, 0.85)
    labels = db.get_all_labels()
    assert len(labels) == 1


def test_count_labels(db):
    """Test count labels."""
    item = {'title': 'Test Grant', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    item_hash = db.hash_item(item['title'], item['url'])
    db.save_feedback(item_hash, 1, 0.85)
    assert db.count_labels() == 1


def test_count_items(db):
    """Test count items."""
    item = {'title': 'Test Grant', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    assert db.count_items() == 1


def test_count_notified(db):
    """Test count notified."""
    item = {'title': 'Test Grant', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    assert db.count_notified() == 0
    item_hash = db.hash_item(item['title'], item['url'])
    db.mark_notified(item_hash)
    assert db.count_notified() == 1
