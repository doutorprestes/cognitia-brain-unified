"""Unified database module — SQLite with deduplication."""

import hashlib
import logging
import sqlite3
from contextlib import contextmanager
from typing import Optional

from .config import DB_PATH

logger = logging.getLogger(__name__)


class UnifiedDatabase:
    """SQLite database for grants and articles with deduplication."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_PATH
        self._create_tables()

    @contextmanager
    def _connection(self):
        """Context manager for SQLite connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_tables(self):
        """Create tables if they don't exist."""
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS items (
                    hash TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('grant', 'artigo')),
                    snippet TEXT,
                    confidence REAL DEFAULT 0.0,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notified_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_hash TEXT NOT NULL,
                    label INTEGER NOT NULL CHECK(label IN (0, 1)),
                    confidence REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_hash) REFERENCES items(hash)
                );

                CREATE TABLE IF NOT EXISTS model_metrics (
                    version INTEGER PRIMARY KEY AUTOINCREMENT,
                    accuracy REAL,
                    precision REAL,
                    recall REAL,
                    n_train_samples INTEGER,
                    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
                CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);
                CREATE INDEX IF NOT EXISTS idx_items_notified ON items(notified_at);
                CREATE INDEX IF NOT EXISTS idx_feedback_hash ON feedback(item_hash);
            """)
        logger.info('Database initialized: %s', self.db_path)

    @staticmethod
    def hash_item(title: str, url: str) -> str:
        """Generate SHA-256 hash from normalized title+url."""
        text = f"{title.strip().lower()}{url.strip().lower()}"
        return hashlib.sha256(text.encode()).hexdigest()

    def insert_item(self, item: dict) -> bool:
        """Insert item. Returns True if inserted, False if duplicate."""
        item_hash = item.get('hash') or self.hash_item(item['title'], item['url'])
        if self.exists(item_hash):
            logger.debug('Duplicate: %s', item['title'][:50])
            return False
        with self._connection() as conn:
            conn.execute(
                'INSERT INTO items (hash, title, url, source, type, snippet) VALUES (?, ?, ?, ?, ?, ?)',
                (item_hash, item['title'], item['url'], item['source'], item['type'], item.get('snippet', ''))
            )
        logger.info('Inserted: %s', item['title'][:50])
        return True

    def exists(self, item_hash: str) -> bool:
        """Check if item exists."""
        with self._connection() as conn:
            cursor = conn.execute('SELECT 1 FROM items WHERE hash = ?', (item_hash,))
            return cursor.fetchone() is not None

    def get_unnotified(self, item_type: Optional[str] = None) -> list:
        """Get items not yet notified."""
        with self._connection() as conn:
            if item_type:
                cursor = conn.execute(
                    'SELECT * FROM items WHERE notified_at IS NULL AND type = ? ORDER BY scraped_at',
                    (item_type,)
                )
            else:
                cursor = conn.execute('SELECT * FROM items WHERE notified_at IS NULL ORDER BY scraped_at')
            return [dict(row) for row in cursor.fetchall()]

    def mark_notified(self, item_hash: str):
        """Mark item as notified."""
        with self._connection() as conn:
            conn.execute('UPDATE items SET notified_at = CURRENT_TIMESTAMP WHERE hash = ?', (item_hash,))

    def save_feedback(self, item_hash: str, label: int, confidence: float):
        """Save user feedback."""
        with self._connection() as conn:
            conn.execute(
                'INSERT INTO feedback (item_hash, label, confidence) VALUES (?, ?, ?)',
                (item_hash, label, confidence)
            )
        logger.info('Feedback saved: hash=%s, label=%d', item_hash[:8], label)

    def get_all_labels(self) -> list:
        """Get all labels for training."""
        with self._connection() as conn:
            cursor = conn.execute(
                'SELECT i.title, f.label FROM feedback f JOIN items i ON f.item_hash = i.hash ORDER BY f.created_at'
            )
            return [(row['title'], row['label']) for row in cursor.fetchall()]

    def count_labels(self) -> int:
        """Count total feedback labels."""
        with self._connection() as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM feedback')
            return cursor.fetchone()[0]

    def count_items(self, item_type: Optional[str] = None) -> int:
        """Count total items."""
        with self._connection() as conn:
            if item_type:
                cursor = conn.execute('SELECT COUNT(*) FROM items WHERE type = ?', (item_type,))
            else:
                cursor = conn.execute('SELECT COUNT(*) FROM items')
            return cursor.fetchone()[0]

    def count_notified(self) -> int:
        """Count notified items."""
        with self._connection() as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM items WHERE notified_at IS NOT NULL')
            return cursor.fetchone()[0]

    def save_metrics(self, accuracy: float, precision: float, recall: float, n_samples: int):
        """Save model metrics."""
        with self._connection() as conn:
            conn.execute(
                'INSERT INTO model_metrics (accuracy, precision, recall, n_train_samples) VALUES (?, ?, ?, ?)',
                (accuracy, precision, recall, n_samples)
            )
        logger.info('Metrics saved: acc=%.3f, prec=%.3f, rec=%.3f', accuracy, precision, recall)
