"""Testes unitários para API."""
import pytest
from fastapi.testclient import TestClient
from src.web.pwa import pwa_app

client = TestClient(pwa_app)


def test_health():
    """Testa endpoint /api/health."""
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_stats():
    """Testa endpoint /api/stats."""
    response = client.get('/api/stats')
    assert response.status_code == 200
    data = response.json()
    assert 'total_items' in data
    assert 'total_grants' in data
    assert 'total_artigos' in data


def test_items():
    """Testa endpoint /api/items."""
    response = client.get('/api/items?limit=5')
    assert response.status_code == 200
    data = response.json()
    assert 'items' in data
    assert 'total' in data
    assert 'offset' in data


def test_search():
    """Testa endpoint /api/search."""
    response = client.get('/api/search?q=test')
    assert response.status_code == 200
    data = response.json()
    assert 'items' in data
    assert 'query' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
