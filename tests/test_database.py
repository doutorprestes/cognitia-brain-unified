"""Tests for UnifiedDatabase."""
import os
import pytest
import tempfile
from src.shared.database import UnifiedDatabase

@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db = UnifiedDatabase(db_path)
    yield db
    os.unlink(db_path)

def test_insert_item(db):
    item = {'title': 'Test', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    assert db.insert_item(item) is True

def test_insert_duplicate(db):
    item = {'title': 'Test', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    assert db.insert_item(item) is False

def test_exists(db):
    item = {'title': 'Test', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    assert db.exists(db.hash_item(item['title'], item['url'])) is True

def test_get_unnotified(db):
    item = {'title': 'Test', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    assert len(db.get_unnotified()) == 1

def test_mark_notified(db):
    item = {'title': 'Test', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    item_hash = db.hash_item(item['title'], item['url'])
    db.mark_notified(item_hash)
    assert len(db.get_unnotified()) == 0

def test_save_feedback(db):
    item = {'title': 'Test', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    item_hash = db.hash_item(item['title'], item['url'])
    db.save_feedback(item_hash, 1, 0.85)
    assert db.count_labels() == 1

def test_count_items(db):
    item = {'title': 'Test', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    assert db.count_items() == 1

def test_count_notified(db):
    item = {'title': 'Test', 'url': 'https://test.com', 'source': 'TEST', 'type': 'grant'}
    db.insert_item(item)
    assert db.count_notified() == 0
    item_hash = db.hash_item(item['title'], item['url'])
    db.mark_notified(item_hash)
    assert db.count_notified() == 1
