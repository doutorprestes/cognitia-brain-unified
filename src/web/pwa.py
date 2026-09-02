"""CognitiaBrain PWA - Progressive Web App."""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.shared.config import config
from src.shared.database import UnifiedDatabase

BASE_DIR = Path(__file__).resolve().parent.parent.parent

pwa_app = FastAPI(title='CognitiaBrain PWA', version='1.0.0')

pwa_app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')

templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))


@pwa_app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', {'request': request})


@pwa_app.get('/api/stats')
async def stats():
    db = UnifiedDatabase()
    return {
        'total_items': db.count_items(),
        'total_grants': db.count_items('grant'),
        'total_artigos': db.count_items('artigo'),
        'total_notified': db.count_notified(),
        'total_labels': db.count_labels(),
    }


@pwa_app.get('/api/items')
async def items(type: str = 'all', limit: int = 50):
    db = UnifiedDatabase()
    item_type = None if type == 'all' else type
    unnotified = db.get_unnotified(item_type)
    result = []
    for item in unnotified[:limit]:
        result.append({
            'hash': item['hash'],
            'title': item['title'],
            'url': item['url'],
            'source': item['source'],
            'type': item['type'],
            'snippet': item.get('snippet', ''),
            'scraped_at': str(item.get('scraped_at', '')),
        })
    return {'items': result, 'total': len(unnotified)}


@pwa_app.post('/api/feedback')
async def feedback(request: Request):
    data = await request.json()
    item_hash = data.get('hash')
    label = data.get('label')
    if item_hash is None or label is None:
        return JSONResponse({'error': 'hash and label required'}, status_code=400)
    db = UnifiedDatabase()
    db.save_feedback(item_hash, int(label), 1.0)
    return {'ok': True}


@pwa_app.get('/api/health')
async def health():
    return {'status': 'ok', 'version': '1.0.0'}
