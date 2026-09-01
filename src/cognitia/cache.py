"""Cache system for Cognitia Brain."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class LRUCache:
    """Simple LRU cache with TTL support."""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict = OrderedDict()
        self.timestamps: Dict[str, float] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get item from cache."""
        if key not in self.cache:
            return None

        # Check TTL
        if time.time() - self.timestamps.get(key, 0) > self.ttl:
            self._remove(key)
            return None

        # Move to end (most recently used)
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: str, value: Any) -> None:
        """Set item in cache."""
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                self._remove_oldest()

        self.cache[key] = value
        self.timestamps[key] = time.time()

    def _remove(self, key: str) -> None:
        """Remove item from cache."""
        if key in self.cache:
            del self.cache[key]
            del self.timestamps[key]

    def _remove_oldest(self) -> None:
        """Remove oldest item from cache."""
        if self.cache:
            oldest_key = next(iter(self.cache))
            self._remove(oldest_key)

    def clear(self) -> None:
        """Clear all items from cache."""
        self.cache.clear()
        self.timestamps.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)

    def stats(self) -> Dict:
        """Get cache statistics."""
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "ttl": self.ttl
        }


class EmbeddingCache:
    """Cache for embeddings."""

    def __init__(self, cache_dir: Path = Path(".chromadb/embedding_cache")):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory_cache = LRUCache(max_size=5000, ttl=86400)  # 24h TTL
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load cache from disk."""
        cache_file = self.cache_dir / "cache.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                for key, value in data.items():
                    self.memory_cache.set(key, value)
            except Exception as e:
                logger.error(f"Error loading embedding cache: {e}")

    def _save_to_disk(self) -> None:
        """Save cache to disk."""
        cache_file = self.cache_dir / "cache.json"
        try:
            data = dict(self.memory_cache.cache)
            cache_file.write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Error saving embedding cache: {e}")

    def _compute_key(self, text: str) -> str:
        """Compute cache key for text."""
        return hashlib.md5(text.encode()).hexdigest()

    def get(self, text: str) -> Optional[Any]:
        """Get embedding from cache."""
        key = self._compute_key(text)
        return self.memory_cache.get(key)

    def set(self, text: str, embedding: Any) -> None:
        """Set embedding in cache."""
        key = self._compute_key(text)
        self.memory_cache.set(key, embedding)

        # Periodically save to disk
        if self.memory_cache.size() % 100 == 0:
            self._save_to_disk()

    def clear(self) -> None:
        """Clear cache."""
        self.memory_cache.clear()
        cache_file = self.cache_dir / "cache.json"
        if cache_file.exists():
            cache_file.unlink()

    def stats(self) -> Dict:
        """Get cache statistics."""
        return {
            "memory_cache": self.memory_cache.stats(),
            "disk_cache_dir": str(self.cache_dir)
        }


class SearchCache:
    """Cache for search results."""

    def __init__(self, ttl: int = 3600):
        self.cache = LRUCache(max_size=500, ttl=ttl)

    def get(self, query: str, n_results: int, where: Optional[Dict] = None) -> Optional[Any]:
        """Get search results from cache."""
        key = self._compute_key(query, n_results, where)
        return self.cache.get(key)

    def set(self, query: str, n_results: int, where: Optional[Dict], results: Any) -> None:
        """Set search results in cache."""
        key = self._compute_key(query, n_results, where)
        self.cache.set(key, results)

    def _compute_key(self, query: str, n_results: int, where: Optional[Dict]) -> str:
        """Compute cache key for search query."""
        where_str = json.dumps(where, sort_keys=True) if where else ""
        key_str = f"{query}:{n_results}:{where_str}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def clear(self) -> None:
        """Clear cache."""
        self.cache.clear()

    def stats(self) -> Dict:
        """Get cache statistics."""
        return self.cache.stats()


# Global cache instances
embedding_cache = EmbeddingCache()
search_cache = SearchCache()
