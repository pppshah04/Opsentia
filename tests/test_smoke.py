from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)
def test_health_truthful():
 r=client.get('/api/health');assert r.status_code==200;d=r.json();assert d['product']=='Opsentia' and not d['gemini_verified']
def test_coverage():
 r=client.get('/api/data-coverage');assert r.status_code==200;d=r.json();assert d['rows']==43680 and len(d['queues'])==5
def test_snapshot_is_synthetic():
 r=client.get('/api/snapshot',params={'queue':'Queue A','as_of':'2026-09-13 16:30:00'})
 assert r.status_code==200;rj=r.json();assert rj['mode']=='SYNTHETIC_REPLAY';assert rj['observed']['queue']=='Queue A'

def test_fixture_presence():
 from pathlib import Path
 root=Path(__file__).resolve().parent.parent
 assert len(list((root/'data').glob('*.csv')))==26
