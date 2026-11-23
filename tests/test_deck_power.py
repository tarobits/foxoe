import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from foxoe import deck_cli
from foxoe.__main__ import main
from foxoe.controller import Controller
from foxoe.models import Configuration
from foxoe.server import create_app
from foxoe.store import Store

ORIGIN='http://127.0.0.1:8765'


def test_power_persists_rejects_bad_requests_and_recovers_after_write_failure(tmp_path):
    app=create_app(tmp_path,hardware=False)
    with TestClient(app,base_url=ORIGIN) as client:
        assert client.get('/api/deck/power').json()['enabled'] is True
        before=client.get('/api/config').json()
        for body in ({'enabled':'false'},{'enabled':0},{'enabled':None},{},{'enabled':False,'extra':True}):
            assert client.put('/api/deck/power',json=body,headers={'origin':ORIGIN}).status_code==422
        for headers in ({},{'origin':'https://evil.test'},{'origin':ORIGIN,'sec-fetch-site':'cross-site'}):
            assert client.put('/api/deck/power',json={'enabled':False},headers=headers).status_code==403
        assert app.state.controller.device_enabled is True
        assert client.put('/api/deck/power',json={'enabled':False},headers={'origin':ORIGIN}).json()['brightness']==0
        assert client.get('/api/config').json()==before
        assert Store(tmp_path).deck_enabled() is False
        assert create_app(tmp_path,hardware=False).state.controller.device_enabled is False
        with app.state.store.connect() as db:
            db.execute("CREATE TRIGGER block_power BEFORE UPDATE ON device_state BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        assert client.put('/api/deck/power',json={'enabled':True},headers={'origin':ORIGIN}).status_code==503
        assert app.state.controller.device_enabled is False
        assert Store(tmp_path).deck_enabled() is False
        with app.state.store.connect() as db:
            db.execute('DROP TRIGGER block_power')
        assert client.put('/api/deck/power',json={'enabled':True},headers={'origin':ORIGIN}).json()['brightness']==before['brightness']
        assert Store(tmp_path).deck_enabled() is True


def test_power_disables_presses_preserves_layout_and_rejects_old_generations():
    controller=Controller(Configuration(),ORIGIN)
    queue=controller.connect('browser'); controller.context('browser','doc',ORIGIN)
    original=controller.buttons(); generation=controller.generation
    controller.set_device_enabled(False)
    controller.press(0,True,generation)
    controller.press(14,True,controller.generation)
    assert queue.empty() and not controller.held
    assert controller.buttons()==original
    controller.configure(controller.config.model_copy(update={'brightness':23}))
    assert controller.device_enabled is False
    controller.context('browser','next',ORIGIN)
    controller.set_device_enabled(True)
    while not queue.empty(): queue.get_nowait()
    controller.press(0,True,generation)
    assert queue.empty()
    controller.press(0,False,controller.generation)
    controller.press(0,True,controller.generation)
    assert queue.get_nowait()['type']=='launch'


def test_concurrent_power_writes_and_invalid_write_do_not_lock_store(tmp_path):
    store=Store(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(store.set_deck_enabled,[True,False]*8))
    with pytest.raises(ValueError): store.set_deck_enabled('false')
    store.set_deck_enabled(False)
    assert store.deck_enabled() is False
    config=store.load(); store.save(config)
    assert store.deck_enabled() is False


def test_cli_routes_through_service_with_safe_transport(monkeypatch,capsys):
    original_client=httpx.Client
    requests=[]
    def handler(request):
        requests.append(request)
        assert request.url==deck_cli.URL
        if request.method=='PUT':
            assert request.headers['origin']==ORIGIN
            enabled=json.loads(request.content)['enabled']
        else: enabled=True
        return httpx.Response(200,json={'enabled':enabled,'device':'connected','brightness':65 if enabled else 0})
    def factory(**kwargs):
        assert kwargs=={'timeout':5,'trust_env':False,'follow_redirects':False}
        return original_client(transport=httpx.MockTransport(handler),**kwargs)
    monkeypatch.setattr(deck_cli.httpx,'Client',factory)
    for action in ('off','on','status'): main(['deck',action])
    assert [r.method for r in requests]==['PUT','PUT','GET']
    assert 'Stream Deck off' in capsys.readouterr().out
    with pytest.raises(SystemExit) as error: main(['deck','invalid'])
    assert error.value.code==2 and len(requests)==3


@pytest.mark.parametrize('failure',['offline','http','redirect','invalid','wrong_shape'])
def test_cli_failure_is_nonzero_sanitized_and_can_retry(monkeypatch,capsys,failure):
    original_client=httpx.Client
    calls=0
    def handler(request):
        nonlocal calls
        calls+=1
        if calls>1: return httpx.Response(200,json={'enabled':True,'device':'connected'})
        if failure=='offline': raise httpx.ConnectError('sensitive diagnostic',request=request)
        if failure=='http': return httpx.Response(503,text='sensitive diagnostic')
        if failure=='redirect': return httpx.Response(302,headers={'location':'https://evil.test/'})
        if failure=='wrong_shape': return httpx.Response(200,json={'enabled':'yes','device':'connected'})
        return httpx.Response(200,text='sensitive diagnostic')
    monkeypatch.setattr(deck_cli.httpx,'Client',lambda **kwargs: original_client(transport=httpx.MockTransport(handler),**kwargs))
    with pytest.raises(SystemExit) as error: deck_cli.main(['off'])
    assert error.value.code==1
    assert 'sensitive diagnostic' not in capsys.readouterr().err
    deck_cli.main(['on'])
    assert calls==2
