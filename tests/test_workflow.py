import json
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Settings
from backend.store import Store

@pytest.fixture
def client(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,approval_token='test-token'))
    with TestClient(app) as client:
        yield client

def test_approval_gate_and_idempotency(client):
    eid=client.post('/api/demo-events').json()[0]['id']
    before=client.post(f'/api/events/{eid}/approve',json={'approve':True,'reviewer':'test'},headers={'Authorization':'Bearer test-token'})
    assert before.status_code==409
    analysis=client.post(f'/api/events/{eid}/analyze',json={'mode':'demo'})
    assert analysis.status_code==200
    report=analysis.json()['report']
    assert report['status']=='awaiting_approval'
    assert report['citations'][0]['id']=='DEMO-SOP-01'
    assert all(t['selected_by']=='deterministic_demo' for t in report['trace'])
    forbidden=client.post(f'/api/events/{eid}/approve',json={'approve':True,'reviewer':'test'})
    assert forbidden.status_code==403
    payload={'approve':True,'reviewer':'test'}; headers={'Authorization':'Bearer test-token'}
    first=client.post(f'/api/events/{eid}/approve',json=payload,headers=headers).json()
    second=client.post(f'/api/events/{eid}/approve',json=payload,headers=headers).json()
    assert first['command']['status']=='mock_executed'
    assert second['idempotent'] is True
    assert first['command']['id']==second['command']['id']
    audit=client.get(f'/api/events/{eid}').json()['audit']
    assert sum(a['action']=='device_result' for a in audit)==1

def test_uncertain_evidence_cannot_execute(client):
    eid=client.post('/api/demo-events').json()[2]['id']
    result=client.post(f'/api/events/{eid}/analyze',json={'mode':'demo'}).json()
    assert result['status']=='needs_review'
    assert result['report']['action'] is None
    assert client.post(f'/api/events/{eid}/approve',json={'approve':True,'reviewer':'test'},headers={'Authorization':'Bearer test-token'}).status_code==409

def test_reject_does_not_dispatch(client):
    eid=client.post('/api/demo-events').json()[0]['id']
    client.post(f'/api/events/{eid}/analyze',json={'mode':'demo'})
    response=client.post(f'/api/events/{eid}/approve',json={'approve':False,'reviewer':'test'},headers={'Authorization':'Bearer test-token'}).json()
    assert response['event']['status']=='rejected'
    assert response['command'] is None

def test_real_mode_failure_never_becomes_demo(client,monkeypatch):
    async def fail(event,mode): raise RuntimeError('model offline')
    monkeypatch.setattr(client.app.state.agent,'run',fail)
    eid=client.post('/api/demo-events').json()[0]['id']
    response=client.post(f'/api/events/{eid}/analyze',json={'mode':'local'})
    assert response.status_code==503
    event=client.get(f'/api/events/{eid}').json()
    assert event['status']=='error' and event['report'] is None

def test_unknown_tool_is_rejected(client):
    import asyncio
    with pytest.raises(ValueError,match='allowlisted'):
        asyncio.run(client.app.state.agent.tool('open_gate',{},{}))

def test_recovery_never_resends_unknown_command(tmp_path):
    store=Store(tmp_path)
    e=store.add({'source':'demo'})
    store.save_report(e['id'],{'status':'awaiting_approval','mode':'demo','risk':'high','action':{'device_id':'alarm-light-01','action':'TURN_ON','duration_seconds':30}})
    assert store.approve(e['id'],'test',True)
    restarted=Store(tmp_path); restarted.recover()
    assert restarted.command(e['id'])['status']=='delivery_unknown'
    assert restarted.get(e['id'])['status']=='delivery_unknown'
    assert not restarted.approve(e['id'],'test',True)

def test_bad_polygon_rejected(client):
    r=client.post('/api/videos',files={'file':('clip.mp4',b'invalid','video/mp4')},data={'polygon':'[[2,0],[0,1],[1,1]]'})
    assert r.status_code==422

def test_missing_visual_confirmation_blocks_action(client):
    event={'source':'video','snapshot':'frame.jpg','event_type':'INTRUSION','confidence':0.99,'duration':10}
    state={'event':event,'mode':'local','trace':[],
           'evidence':{'get_event_context':{},'get_track_evidence':{}},'citations':[{'id':'DEMO-SOP-01'}]}
    report=client.app.state.agent.decide(state)['report']
    assert report['status']=='needs_review' and report['action'] is None

def test_device_allowlist_rejects_unapproved_action(tmp_path):
    from backend.devices import dispatch
    with pytest.raises(ValueError,match='allowlist'):
        dispatch(Settings(data_dir=tmp_path),{'device_id':'door-01','action':'OPEN','duration_seconds':30})

