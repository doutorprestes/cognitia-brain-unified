"""Database unificado."""
import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from typing import Optional

from .config import DB_PATH

logger = logging.getLogger(__name__)


class UnifiedDatabase:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_PATH
        self._conn = None
        self._create_tables()

    def _get_conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute('PRAGMA journal_mode=WAL')
            self._conn.execute('PRAGMA foreign_keys=ON')
        return self._conn

    @contextmanager
    def _connection(self):
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _create_tables(self):
        with self._connection() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS items (
                    hash TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
                    source TEXT NOT NULL, type TEXT NOT NULL CHECK(type IN ('grant', 'artigo')),
                    snippet TEXT, confidence REAL DEFAULT 0.0,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, notified_at TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, item_hash TEXT NOT NULL,
                    label INTEGER NOT NULL CHECK(label IN (0, 1)), confidence REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_hash) REFERENCES items(hash)
                );
                CREATE TABLE IF NOT EXISTS model_metrics (
                    version INTEGER PRIMARY KEY AUTOINCREMENT, accuracy REAL,
                    precision REAL, recall REAL, n_train_samples INTEGER,
                    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    interests TEXT DEFAULT '[]',
                    stats TEXT DEFAULT '{}',
                    config TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
                CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);
                CREATE INDEX IF NOT EXISTS idx_items_notified ON items(notified_at);
            ''')

    @staticmethod
    def hash_item(title: str, url: str) -> str:
        text = f'{title.strip().lower()}{url.strip().lower()}'
        return hashlib.sha256(text.encode()).hexdigest()

    def insert_item(self, item: dict) -> bool:
        item_hash = item.get('hash') or self.hash_item(item['title'], item['url'])
        if self.exists(item_hash):
            return False
        with self._connection() as conn:
            conn.execute(
                'INSERT INTO items (hash, title, url, source, type, snippet) VALUES (?, ?, ?, ?, ?, ?)',
                (item_hash, item['title'], item['url'], item['source'], item['type'], item.get('snippet', ''))
            )
        return True

    def exists(self, item_hash: str) -> bool:
        with self._connection() as conn:
            cursor = conn.execute('SELECT 1 FROM items WHERE hash = ?', (item_hash,))
            return cursor.fetchone() is not None

    def get_unnotified(self, item_type: Optional[str] = None) -> list:
        with self._connection() as conn:
            if item_type:
                cursor = conn.execute('SELECT * FROM items WHERE notified_at IS NULL AND type = ?', (item_type,))
            else:
                cursor = conn.execute('SELECT * FROM items WHERE notified_at IS NULL')
            return [dict(row) for row in cursor.fetchall()]

    def mark_notified(self, item_hash: str):
        with self._connection() as conn:
            conn.execute('UPDATE items SET notified_at = CURRENT_TIMESTAMP WHERE hash = ?', (item_hash,))

    def search(self, query: str, item_type: Optional[str] = None) -> list:
        with self._connection() as conn:
            search_term = f'%{query.lower()}%'
            if item_type:
                cursor = conn.execute(
                    'SELECT * FROM items WHERE type = ? AND (LOWER(title) LIKE ? OR LOWER(snippet) LIKE ? OR LOWER(source) LIKE ?) ORDER BY scraped_at DESC',
                    (item_type, search_term, search_term, search_term)
                )
            else:
                cursor = conn.execute(
                    'SELECT * FROM items WHERE LOWER(title) LIKE ? OR LOWER(snippet) LIKE ? OR LOWER(source) LIKE ? ORDER BY scraped_at DESC',
                    (search_term, search_term, search_term)
                )
            return [dict(row) for row in cursor.fetchall()]

    def save_feedback(self, item_hash: str, label: int, confidence: float):
        with self._connection() as conn:
            conn.execute('INSERT INTO feedback (item_hash, label, confidence) VALUES (?, ?, ?)', (item_hash, label, confidence))

    def get_all_labels(self) -> list:
        with self._connection() as conn:
            cursor = conn.execute('SELECT i.title, f.label FROM feedback f JOIN items i ON f.item_hash = i.hash')
            return [(row['title'], row['label']) for row in cursor.fetchall()]

    def count_labels(self) -> int:
        with self._connection() as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM feedback')
            return cursor.fetchone()[0]

    def count_items(self, item_type: Optional[str] = None) -> int:
        with self._connection() as conn:
            if item_type:
                cursor = conn.execute('SELECT COUNT(*) FROM items WHERE type = ?', (item_type,))
            else:
                cursor = conn.execute('SELECT COUNT(*) FROM items')
            return cursor.fetchone()[0]

    def count_notified(self) -> int:
        with self._connection() as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM items WHERE notified_at IS NOT NULL')
            return cursor.fetchone()[0]

    def get_user_profile(self, user_id: str) -> dict:
        with self._connection() as conn:
            cursor = conn.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'user_id': row['user_id'],
                    'interests': json.loads(row['interests']),
                    'stats': json.loads(row['stats']),
                    'config': json.loads(row['config']),
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                }
        return {'user_id': user_id, 'interests': [], 'stats': {}, 'config': {}}

    def save_user_profile(self, user_id: str, interests: list, stats: dict, config: dict = None):
        with self._connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO user_profiles (user_id, interests, stats, config, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, json.dumps(interests), json.dumps(stats), json.dumps(config or {})))

    def save_metrics(self, accuracy: float, precision: float, recall: float, n_samples: int):
        with self._connection() as conn:
            conn.execute('INSERT INTO model_metrics (accuracy, precision, recall, n_train_samples) VALUES (?, ?, ?, ?)', (accuracy, precision, recall, n_samples))
