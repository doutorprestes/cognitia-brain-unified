"""Rate limiting for Cognitia Brain bot."""

from __future__ import annotations

import time
from collections import defaultdict
from functools import wraps
from typing import Callable, Dict, Tuple

from telegram import Update
from telegram.ext import ContextTypes


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, user_id: str) -> bool:
        """Check if user is within rate limits."""
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old requests
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if req_time > window_start
        ]

        # Check limit
        if len(self.requests[user_id]) >= self.max_requests:
            return False

        # Record request
        self.requests[user_id].append(now)
        return True

    def get_remaining(self, user_id: str) -> int:
        """Get remaining requests for user."""
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old requests
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if req_time > window_start
        ]

        return max(0, self.max_requests - len(self.requests[user_id]))

    def get_reset_time(self, user_id: str) -> float:
        """Get seconds until rate limit resets."""
        if not self.requests[user_id]:
            return 0

        oldest_request = min(self.requests[user_id])
        reset_time = oldest_request + self.window_seconds - time.time()
        return max(0, reset_time)


# Global rate limiter instance
rate_limiter = RateLimiter(max_requests=10, window_seconds=60)


def rate_limited(func: Callable) -> Callable:
    """Decorator to rate limit bot commands."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = str(update.effective_user.id) if update.effective_user else ""

        if not rate_limiter.is_allowed(user_id):
            remaining_time = rate_limiter.get_reset_time(user_id)
            await update.message.reply_text(
                f"⚠️ Rate limit excedido. Tente novamente em {remaining_time:.0f} segundos."
            )
            return

        return await func(update, context, *args, **kwargs)
    return wrapped
