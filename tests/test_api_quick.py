"""In-memory API quick integration tests using FastAPI TestClient (CI safe)."""
import pytest
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_quick_bootstrap_endpoint():
    r_boot = client.get('/api/ui/bootstrap', params={'queue': 'Queue A', 'as_of': '2026-09-13 17:00:00'})
    assert r_boot.status_code == 200
    data = r_boot.json()
    assert 'daily' in data
    assert 'full_day_forecast' in data
    assert 'watchouts' in data
    daily = data.get('daily', [])
    if daily:
        assert daily[-1].get('is_partial') is True


def test_quick_analytics_all_queues():
    r_an = client.get('/api/analytics', params={'queue': 'All Queues', 'grain': 'week', 'as_of': '2026-09-13 17:00:00'})
    assert r_an.status_code == 200
    data = r_an.json()
    assert 'series' in data
    assert len(data['series']) > 0


def test_quick_forecast_backtest():
    r_bt = client.get('/api/forecasts/full-day/backtest', params={'queue': 'Queue A', 'as_of': '2026-09-13 17:00:00', 'eval_days': 5})
    assert r_bt.status_code == 200
    data = r_bt.json()
    assert 'mean_absolute_error_sla_pp' in data or 'absolute_sla_error_pp' in data


def test_quick_chat_assistant():
    r_c = client.post('/api/assistant/chat', json={'message': 'Why is SLA falling today on Queue A?', 'queue': 'Queue A', 'as_of': '2026-09-13 17:00:00'})
    assert r_c.status_code == 200
    data = r_c.json()
    assert 'answer' in data or 'reply' in data
    assert len(data.get('answer', '') or data.get('reply', '')) > 20
