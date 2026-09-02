"""CognitiaBrain Telegram Mini App."""
import hashlib
import hmac
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from src.shared.config import config
from src.shared.database import UnifiedDatabase
from src.shared.relevancia import engine as relevancia_engine

BASE_DIR = Path(__file__).resolve().parent.parent.parent

pwa_app = FastAPI(title="CognitiaBrain Mini App", version="1.0.0")

pwa_app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """Validate Telegram WebApp initData."""
    if not init_data:
        raise HTTPException(status_code=401, detail="No initData")
    
    params = {}
    for item in init_data.split("&"):
        if "=" in item:
            key, value = item.split("=", 1)
            params[key] = value
    
    check_hash = params.pop("hash", None)
    if not check_hash:
        raise HTTPException(status_code=401, detail="No hash")
    
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode(),
        digestmod=hashlib.sha256
    ).digest()
    
    expected_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()
    
    if expected_hash != check_hash:
        raise HTTPException(status_code=401, detail="Invalid hash")
    
    result = {}
    if "user" in params:
        result["user"] = json.loads(params["user"])
    return result


@pwa_app.get("/", response_class=HTMLResponse)
async def index():
    with open(BASE_DIR / "static" / "miniapp" / "index.html") as f:
        return HTMLResponse(content=f.read())


@pwa_app.get("/api/stats")
async def stats():
    db = UnifiedDatabase()
    return {
        "total_items": db.count_items(),
        "total_grants": db.count_items("grant"),
        "total_artigos": db.count_items("artigo"),
        "total_notified": db.count_notified(),
        "total_labels": db.count_labels(),
    }


@pwa_app.get("/api/items")
async def items(type: str = "all", limit: int = 20, offset: int = 0):
    db = UnifiedDatabase()
    item_type = None if type == "all" else type
    unnotified = db.get_unnotified(item_type)
    
    # Aplicar filtro de relevância
    itens_filtrados = relevancia_engine.filtrar(unnotified, threshold=0.1)
    
    # Paginação
    total = len(itens_filtrados)
    itens_paginados = itens_filtrados[offset:offset + limit]
    
    result = []
    for item in itens_paginados:
        result.append({
            "hash": item["hash"],
            "title": item["title"],
            "url": item["url"],
            "source": item["source"],
            "type": item["type"],
            "snippet": item.get("snippet", ""),
            "scraped_at": str(item.get("scraped_at", "")),
        })
    return {"items": result, "total": total, "offset": offset, "limit": limit}


@pwa_app.get("/api/search")
async def search(q: str = "", type: str = "all", period: str = "all", limit: int = 20, offset: int = 0):
    """Busca artigos por título, snippet, source."""
    db = UnifiedDatabase()
    item_type = None if type == "all" else type
    
    # Buscar no banco
    results = db.search(q, item_type)
    
    # Paginação
    total = len(results)
    results_paginated = results[offset:offset + limit]
    
    items = []
    for item in results_paginated:
        items.append({
            "hash": item["hash"],
            "title": item["title"],
            "url": item["url"],
            "source": item["source"],
            "type": item["type"],
            "snippet": item.get("snippet", ""),
            "scraped_at": str(item.get("scraped_at", "")),
        })
    
    return {"items": items, "total": total, "offset": offset, "limit": limit, "query": q}


@pwa_app.post("/api/feedback")
async def feedback(request: Request):
    data = await request.json()
    item_hash = data.get("hash")
    label = data.get("label")
    if item_hash is None or label is None:
        return JSONResponse({"error": "hash and label required"}, status_code=400)
    db = UnifiedDatabase()
    db.save_feedback(item_hash, int(label), 1.0)
    return {"ok": True}


@pwa_app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
