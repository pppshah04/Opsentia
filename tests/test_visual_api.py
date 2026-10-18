from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

def test_visual_frontend_assets_exist():
    for path in ('/', '/assets/styles.css','/assets/app.js','/assets/opsentia.svg','/assets/vyra.png'):
        result=client.get(path)
        assert result.status_code == 200, (path,result.status_code)

def test_visual_data_connected_to_actual_snapshot():
    response=client.get('/api/ui/bootstrap',params={'queue':'Queue A','as_of':'2026-09-13 17:00:00'})
    assert response.status_code == 200
    data=response.json()
    assert data['meta']['mode']=='SYNTHETIC_REPLAY'
    assert data['meta']['gemini_verified'] is False
    assert data['current']['offered_calls']==314
    assert abs(data['current']['sla']-0.705)<1e-8
    assert len(data['timeline'])==48
    assert data['selected_incident']['queue']=='Queue A'
    assert len(data['hourly_heatmap'])>0

def test_history_and_uncalibrated_forecast_not_fabricated():
    result=client.get('/api/ui/bootstrap',params={'queue':'Queue A','as_of':'2026-09-13 16:30:00'})
    data=result.json()
    assert data['baseline']['offered_calls'] >= 0
    assert len(data['weekly']) >= 1
    assert data['forecast']
    assert 'UNCALIBRATED' in data['forecast'][0]['model_name']
    assert all(x.get('projected_sla') is None for x in data['scenarios'])

def test_other_day_and_queue():
    response=client.get('/api/ui/bootstrap',params={'queue':'Support L2','as_of':'2026-08-23 11:30:00'})
    assert response.status_code == 200
    d=response.json()
    assert d['meta']['queue']=='Support L2'
    assert d['current']['queue']=='Support L2'
    assert len(d['queue_comparison'])==5

def test_invalid_filters_rejected():
    assert client.get('/api/ui/bootstrap',params={'queue':'Missing','as_of':'2026-09-13 17:00:00'}).status_code==400
    assert client.get('/api/ui/bootstrap',params={'queue':'Queue A','as_of':'2025-01-01 17:00:00'}).status_code==404
