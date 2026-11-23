import asyncio
import json
import ssl
import socket
import threading

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from foxoe.admin import AdminGateway, COOKIE, password_digest
from foxoe.admin_setup import configure, load_settings
from foxoe.server import create_app
from foxoe.__main__ import SharedLoopServer

PASSWORD = 'synthetic-test-password-only'
ORIGIN = 'https://pi.test:8767'


@pytest.fixture
def admin(tmp_path):
    salt = 'ab' * 16
    settings = {'salt': salt, 'passwordHash': password_digest(PASSWORD, salt)}
    local = create_app(tmp_path, hardware=False)
    gateway = AdminGateway(local, settings)
    with TestClient(gateway, base_url=ORIGIN) as client:
        yield client, gateway, local


def login(client, password=PASSWORD):
    return client.post('/api/admin/login', json={'password': password}, headers={'origin': ORIGIN})


def test_admin_authentication_cookie_csrf_and_revocation(admin):
    client, gateway, local = admin
    assert client.get('/').status_code == 200
    assert client.get('/api/access').json()['authenticated'] is False
    assert client.get('/api/config').status_code == 401
    assert login(client, 'wrong').status_code == 401
    response = login(client)
    assert response.status_code == 200
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie and 'Path=/' in cookie
    old_cookie = client.cookies.get(COOKIE)
    original = client.get('/api/config').json()
    value = json.loads(json.dumps(original))
    value['apps'][0].update(iconColor='#ff0000', textColor='#00ff00', backgroundColor='#0000ff')
    for headers in ({}, {'origin': 'https://evil.test'}, {'origin': ORIGIN, 'sec-fetch-site': 'same-site'}):
        assert client.put('/api/config', json=value, headers=headers).status_code == 403
    assert client.get('/api/config').json() == original
    saved = client.put('/api/config', json=value, headers={'origin': ORIGIN})
    assert saved.status_code == 200
    assert local.state.controller.config.apps[0].iconColor == '#ff0000'
    assert client.put('/api/config', json=value, headers={'origin': ORIGIN}).status_code == 409
    assert client.post('/api/admin/logout', headers={'origin': ORIGIN}).status_code == 200
    client.cookies.set(COOKIE, old_cookie)
    assert client.get('/api/config').status_code == 401
    assert not gateway.sessions


def test_admin_cannot_expose_local_credentials_or_bridge(admin):
    client, _, _ = admin
    login(client)
    for method, path in [('POST', '/api/pair'), ('POST', '/api/registration-token'), ('GET', '/api/health'),
                         ('GET', '/api/deck/power'), ('PUT', '/api/deck/power'),
                         ('GET', '/bridge'), ('POST', '/v1/apps'), ('GET', '/admin/config.json'), ('GET', '/api/images/../../admin/config.json')]:
        assert client.request(method, path, headers={'origin': ORIGIN}).status_code == 404
    assert client.get('/api/config', headers={'origin': 'http://127.0.0.1:8765'}).status_code == 403
    assert client.get('http://pi.test:8767/api/access').status_code == 403


def test_remote_preview_requires_session_origin_and_valid_draft(admin, monkeypatch):
    client, _, local = admin
    calls = []
    async def preview(source):
        calls.append(source)
        return {'value': {'count': 0}, 'updatedAt': 123, 'error': None}
    monkeypatch.setattr(local.state.sources, 'preview', preview)
    draft = {'id': 'draft', 'name': 'Draft', 'url': 'https://example.test/json', 'interval': 15, 'authEnv': ''}
    assert client.post('/api/data/preview', json=draft, headers={'origin': ORIGIN}).status_code == 401
    login(client)
    for headers in ({}, {'origin': 'https://evil.test'}, {'origin': ORIGIN, 'sec-fetch-site': 'cross-site'}):
        assert client.post('/api/data/preview', json=draft, headers=headers).status_code == 403
    for invalid in ({**draft, 'url': 'file:///etc/passwd'}, {**draft, 'authEnv': 'PATH'}, {**draft, 'extra': True}):
        response = client.post('/api/data/preview', json=invalid, headers={'origin': ORIGIN})
        assert response.status_code == 422
        assert response.json() == {'error': 'invalid_configuration'}
    assert not calls
    before = client.get('/api/config').json()
    response = client.post('/api/data/preview', json=draft, headers={'origin': ORIGIN})
    assert response.status_code == 200
    assert response.json()['value'] == {'count': 0}
    assert calls[0].url == draft['url']
    assert client.get('/api/config').json() == before


def test_key_preview_matches_device_and_protects_remote_access(admin):
    import io
    from PIL import Image
    from foxoe.device import key_image
    client, _, _ = admin
    value = {'label': 'Label Station', 'icon': 'printer', 'textSize': 32,
             'textColor': '#12abcd', 'backgroundColor': '#123456', 'disabled': True}
    params = {'key': json.dumps(value)}
    assert client.get('/api/deck/preview', params=params).status_code == 401
    login(client)
    assert client.get('/api/deck/preview', params=params, headers={'origin': 'https://evil.test'}).status_code == 403
    for invalid in ({**value, 'textSize': True}, {**value, 'textSize': 999}, {**value, 'label': 'a' * 61},
                    {**value, 'image': '../../secret'}, {**value, 'icon': '../../secret'},
                    {**value, 'backgroundColor': 'red'}, {**value, 'extra': True}):
        response = client.get('/api/deck/preview', params={'key': json.dumps(invalid)})
        assert response.status_code == 422
        assert response.json() == {'error': 'invalid_configuration'}
    assert client.get('/api/deck/preview', params={'key': '{'}).status_code == 422
    assert client.get('/api/deck/preview', params={'key': 'x' * 2049}).status_code == 422
    before = client.get('/api/config').json()
    response = client.get('/api/deck/preview', params=params)
    assert response.status_code == 200 and response.headers['content-type'] == 'image/png'
    with Image.open(io.BytesIO(response.content)) as actual:
        expected = key_image('Label Station', True, False, icon='printer', text_size=32,
                             text_color='#12abcd', background_color='#123456')
        assert actual.tobytes() == expected.tobytes()
    assert client.get('/api/config').json() == before


def test_malformed_login_rate_limit_expiry_and_recovery(admin, monkeypatch):
    client, gateway, _ = admin
    for content in ('[]', 'null', '{', '{"password":true}'):
        assert client.post('/api/admin/login', content=content, headers={'origin': ORIGIN}).status_code == 401
    assert client.post('/api/admin/login', content='x' * 4097, headers={'origin': ORIGIN}).status_code == 413
    assert login(client).status_code == 200
    gateway.sessions = {key: 0 for key in gateway.sessions}
    assert client.get('/api/config').status_code == 401
    for _ in range(4):
        assert login(client, 'wrong').status_code == 401
    assert login(client).status_code == 429
    gateway.attempts.clear()
    assert login(client).status_code == 200
    assert gateway.active_logins == 0


def test_failed_password_hash_releases_concurrency_slot(admin, monkeypatch):
    client, gateway, _ = admin
    original = password_digest
    monkeypatch.setattr('foxoe.admin.password_digest', lambda *_: (_ for _ in ()).throw(RuntimeError('test failure')))
    with pytest.raises(RuntimeError):
        login(client)
    assert gateway.active_logins == 0
    monkeypatch.setattr('foxoe.admin.password_digest', original)
    assert login(client).status_code == 200


def test_setup_validates_before_writes_and_preserves_certificate(tmp_path):
    for password, hostname, port in [('short', 'pi.local', 8767), (PASSWORD, 'bad;command', 8767), (PASSWORD, 'pi.local', 8765)]:
        with pytest.raises(ValueError):
            configure(tmp_path, password, hostname, port)
        assert not (tmp_path / 'admin').exists()
    assert load_settings(tmp_path) is None
    first = configure(tmp_path, PASSWORD, 'pi.local')
    certificate = (tmp_path / 'admin/certificate.pem').read_bytes()
    assert (tmp_path / 'admin/private-key.pem').stat().st_mode & 0o077 == 0
    assert (tmp_path / 'admin/config.json').stat().st_mode & 0o077 == 0
    assert PASSWORD not in (tmp_path / 'admin/config.json').read_text()
    second = configure(tmp_path, PASSWORD + '-changed', 'pi.local')
    assert first['salt'] != second['salt']
    assert first['passwordHash'] != second['passwordHash']
    assert certificate == (tmp_path / 'admin/certificate.pem').read_bytes()
    assert load_settings(tmp_path) == second


def test_cancelled_login_keeps_hash_work_bounded_and_recovers(admin, monkeypatch):
    _, gateway, _ = admin
    release = threading.Event()
    def delayed(password, salt):
        assert release.wait(5), 'Hash worker was not released'
        return password_digest(password, salt)
    monkeypatch.setattr('foxoe.admin.password_digest', delayed)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url=ORIGIN) as client:
            async def attempt():
                return await client.post('/api/admin/login', json={'password': PASSWORD}, headers={'origin': ORIGIN})
            tasks = [asyncio.create_task(attempt()) for _ in range(2)]
            try:
                async with asyncio.timeout(2):
                    while gateway.active_logins != 2:
                        await asyncio.sleep(.01)
                tasks[0].cancel()
                await asyncio.sleep(.02)
                assert gateway.active_logins == 2
                assert (await attempt()).status_code == 429
            finally:
                release.set()
                await asyncio.gather(*tasks, return_exceptions=True)
                # Cancelled requests intentionally leave their hash worker
                # running. Wait for that worker's cleanup, not just HTTP tasks.
                async with asyncio.timeout(2):
                    while gateway.active_logins:
                        await asyncio.sleep(.01)
            assert gateway.active_logins == 0
            assert (await attempt()).status_code == 200
    asyncio.run(scenario())


def test_real_admin_tls_listener_login_and_shutdown(tmp_path):
    settings = configure(tmp_path, PASSWORD, '127.0.0.1')
    async def scenario():
        app = create_app(tmp_path, hardware=False)
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        base = f'https://127.0.0.1:{sock.getsockname()[1]}'
        server = SharedLoopServer(uvicorn.Config(AdminGateway(app, settings), ssl_certfile=str(tmp_path / 'admin/certificate.pem'),
            ssl_keyfile=str(tmp_path / 'admin/private-key.pem'), log_level='error', proxy_headers=False))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    await asyncio.sleep(.02)
            trust = ssl.create_default_context(cafile=str(tmp_path / 'admin/certificate.pem'))
            async with httpx.AsyncClient(verify=trust, trust_env=False, base_url=base) as client:
                assert (await client.get('/api/config')).status_code == 401
                assert (await client.post('/api/admin/login', json={'password': PASSWORD}, headers={'origin': base})).status_code == 200
                assert (await client.get('/api/config')).status_code == 200
            async with httpx.AsyncClient(trust_env=False) as client:
                with pytest.raises(httpx.ConnectError):
                    await client.get(base + '/')
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 10)
            sock.close()
    asyncio.run(scenario())
