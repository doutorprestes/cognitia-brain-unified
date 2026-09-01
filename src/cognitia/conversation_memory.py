"""Conversation memory for multi-turn RAG in Cognitia Brain."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Manage conversation context for multi-turn RAG."""

    def __init__(
        self,
        max_messages: int = 10,
        max_context_age: timedelta = timedelta(hours=1),
        storage_path: Path = Path(".chromadb/conversation_memory.json")
    ):
        self.max_messages = max_messages
        self.max_context_age = max_context_age
        self.storage_path = storage_path
        self.conversations: Dict[str, List[Dict]] = defaultdict(list)
        self._load()

    def _load(self) -> None:
        """Load conversations from storage."""
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                for user_id, messages in data.items():
                    self.conversations[user_id] = messages
            except Exception as e:
                logger.error(f"Error loading conversation memory: {e}")

    def _save(self) -> None:
        """Save conversations to storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = dict(self.conversations)
            self.storage_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Error saving conversation memory: {e}")

    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """Add a message to conversation history."""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        self.conversations[user_id].append(message)

        # Trim old messages
        self._trim_messages(user_id)

        # Save to storage
        self._save()

    def get_context(
        self,
        user_id: str,
        max_messages: Optional[int] = None
    ) -> List[Dict]:
        """Get conversation context for RAG."""
        messages = self.conversations.get(user_id, [])

        # Filter by age
        cutoff = datetime.now() - self.max_context_age
        recent_messages = []
        for msg in messages:
            try:
                msg_time = datetime.fromisoformat(msg["timestamp"])
                if msg_time > cutoff:
                    recent_messages.append(msg)
            except (KeyError, ValueError):
                continue

        # Limit by count
        limit = max_messages or self.max_messages
        return recent_messages[-limit:]

    def get_context_string(
        self,
        user_id: str,
        max_messages: Optional[int] = None
    ) -> str:
        """Get conversation context as formatted string."""
        messages = self.get_context(user_id, max_messages)

        if not messages:
            return ""

        context_parts = []
        for msg in messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            context_parts.append(f"{role}: {msg['content']}")

        return "\n".join(context_parts)

    def clear_context(self, user_id: str) -> None:
        """Clear conversation context for user."""
        if user_id in self.conversations:
            del self.conversations[user_id]
            self._save()

    def _trim_messages(self, user_id: str) -> None:
        """Trim messages to stay within limits."""
        messages = self.conversations[user_id]

        # Remove old messages
        cutoff = datetime.now() - self.max_context_age
        filtered = []
        for msg in messages:
            try:
                msg_time = datetime.fromisoformat(msg["timestamp"])
                if msg_time > cutoff:
                    filtered.append(msg)
            except (KeyError, ValueError):
                continue

        # Keep only recent messages
        self.conversations[user_id] = filtered[-self.max_messages:]

    def get_stats(self) -> Dict:
        """Get conversation statistics."""
        stats = {}
        for user_id, messages in self.conversations.items():
            stats[user_id] = {
                "message_count": len(messages),
                "last_message": messages[-1]["timestamp"] if messages else None
            }
        return stats


# Global conversation memory instance
conversation_memory = ConversationMemory()
