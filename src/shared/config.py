"""Unified configuration module."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv(TELEGRAM_BOT_TOKEN, )
TELEGRAM_CHAT_ID = os.getenv(TELEGRAM_CHAT_ID, )

# Database
DB_PATH = os.getenv(DB_PATH, str(PROJECT_ROOT / data / cognitia.db))

# ChromaDB
CHROMA_DIR = os.getenv(CHROMA_DIR, str(PROJECT_ROOT / .chromadb))

# Model
MODEL_PATH = os.getenv(MODEL_PATH, str(PROJECT_ROOT / models / classifier.pkl))

# Confidence
CONFIDENCE_MODE = os.getenv(CONFIDENCE_MODE, moderado)
CONFIDENCE_THRESHOLD = float(os.getenv(CONFIDENCE_THRESHOLD, 0.6))
CONFIDENCE_MODES = {conservador: 0.8, moderado: 0.6, agressivo: 0.5}

# LLM
OPENROUTER_API_KEY = os.getenv(OPENROUTER_API_KEY, )
OPENROUTER_MODEL = os.getenv(OPENROUTER_MODEL, google/gemma-2-9b-it:free)
OLLAMA_CLOUD_API_KEY = os.getenv(OLLAMA_CLOUD_API_KEY, )
OLLAMA_CLOUD_MODEL = os.getenv(OLLAMA_CLOUD_MODEL, gpt-oss:120b)

# Web
WEB_PORT = int(os.getenv(WEB_PORT, 8081))

# Scraping
SCRAPE_WAIT_MS = int(os.getenv(SCRAPE_WAIT_MS, 5000))
RETRAIN_INTERVAL = int(os.getenv(RETRAIN_INTERVAL, 20))

# Logging
LOG_LEVEL = os.getenv(LOG_LEVEL, INFO)


def get_confidence_threshold() -> float:
    """Get effective confidence threshold."""
    return CONFIDENCE_MODES.get(CONFIDENCE_MODE, CONFIDENCE_THRESHOLD)


def validate() -> list[str]:
    """Validate required config. Returns list of errors."""
    errors = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append(TELEGRAM_BOT_TOKEN nao configurado)
    if not TELEGRAM_CHAT_ID:
        errors.append(TELEGRAM_CHAT_ID nao configurado)
    return errors
