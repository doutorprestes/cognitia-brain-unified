"""FastAPI web dashboard."""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..shared.config import config
from ..shared.database import UnifiedDatabase

app = FastAPI(title='CognitiaBrain Unified')
db = UnifiedDatabase(config.DB_PATH)

@app.get('/')
async def index():
    items = db.get_unnotified()[:50]
    html = '<html><head><title>CognitiaBrain</title></head><body>'
    html += '<h1>CognitiaBrain Unified</h1>'
    html += f'<p>Total itens: {db.count_items()}</p>'
    html += f'<p>Notificados: {db.count_notified()}</p>'
    html += f'<p>Feedback: {db.count_labels()}</p>'
    html += '<h2>Itens não notificados</h2><ul>'
    for item in items:
        html += f'<li><a href="{item["url"]}">{item["title"]}</a> ({item["source"]})</li>'
    html += '</ul></body></html>'
    return HTMLResponse(content=html)

@app.get('/status')
async def status():
    return {
        'total_items': db.count_items(),
        'total_notificados': db.count_notified(),
        'total_feedback': db.count_labels(),
    }
