"""Config unificado."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
DB_PATH = os.getenv('DB_PATH', str(PROJECT_ROOT / 'data' / 'cognitia.db'))
CHROMA_DIR = os.getenv('CHROMA_DIR', str(PROJECT_ROOT / '.chromadb'))
MODEL_PATH = os.getenv('MODEL_PATH', str(PROJECT_ROOT / 'models' / 'classifier.pkl'))
CONFIDENCE_MODE = os.getenv('CONFIDENCE_MODE', 'moderado')
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.6'))
CONFIDENCE_MODES = {'conservador': 0.8, 'moderado': 0.6, 'agressivo': 0.5}
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'google/gemma-2-9b-it:free')
OLLAMA_CLOUD_API_KEY = os.getenv('OLLAMA_CLOUD_API_KEY', '')
OLLAMA_CLOUD_MODEL = os.getenv('OLLAMA_CLOUD_MODEL', 'gpt-oss:120b')
WEB_PORT = int(os.getenv('WEB_PORT', '8081'))
SCRAPE_WAIT_MS = int(os.getenv('SCRAPE_WAIT_MS', '5000'))
RETRAIN_INTERVAL = int(os.getenv('RETRAIN_INTERVAL', '20'))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')


class Config:
    """Config object for import."""
    TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID
    DB_PATH = DB_PATH
    CHROMA_DIR = CHROMA_DIR
    MODEL_PATH = MODEL_PATH
    CONFIDENCE_MODE = CONFIDENCE_MODE
    CONFIDENCE_THRESHOLD = CONFIDENCE_THRESHOLD
    CONFIDENCE_MODES = CONFIDENCE_MODES
    OPENROUTER_API_KEY = OPENROUTER_API_KEY
    OPENROUTER_MODEL = OPENROUTER_MODEL
    OLLAMA_CLOUD_API_KEY = OLLAMA_CLOUD_API_KEY
    OLLAMA_CLOUD_MODEL = OLLAMA_CLOUD_MODEL
    WEB_PORT = WEB_PORT
    SCRAPE_WAIT_MS = SCRAPE_WAIT_MS
    RETRAIN_INTERVAL = RETRAIN_INTERVAL
    LOG_LEVEL = LOG_LEVEL

    @staticmethod
    def get_confidence_threshold() -> float:
        return CONFIDENCE_MODES.get(CONFIDENCE_MODE, CONFIDENCE_THRESHOLD)

    @staticmethod
    def validate() -> list:
        errors = []
        if not TELEGRAM_BOT_TOKEN: errors.append('TELEGRAM_BOT_TOKEN nao configurado')
        if not TELEGRAM_CHAT_ID: errors.append('TELEGRAM_CHAT_ID nao configurado')
        return errors


config = Config()
