"""Run CognitiaBrain PWA."""
import uvicorn
from src.web.pwa import pwa_app

if __name__ == __main__:
    uvicorn.run(pwa_app, host=0.0.0.0, port=8080, log_level=info)
