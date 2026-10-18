"""In-memory Chat Request integration tests using FastAPI TestClient (CI safe)."""
import pytest
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_chat_request_with_context():
    r = client.post('/api/assistant/chat', json={
        'message': 'Analyze Queue A as of 2026-09-13 17:00:00. Call get_current_metrics and get_full_day_forecast.',
        'queue': 'Queue A',
        'as_of': '2026-09-13 17:00:00'
    })
    assert r.status_code == 200
    data = r.json()
    assert 'ai_mode' in data
    assert 'tool_calls' in data
    assert 'evidence' in data
    assert 'answer' in data or 'reply' in data
    assert len(data.get('answer', '') or data.get('reply', '')) > 0
