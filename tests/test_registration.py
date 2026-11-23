import base64
import io
import secrets
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from foxoe.registration import normalize_image, prepare_manifest, Manifest
from foxoe.server import create_app


def png(size=(120, 80)):
    file = io.BytesIO()
    Image.new('RGB', size, '#4f46e5').save(file, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(file.getvalue()).decode()


def manifest(app_id='printer'):
    return {'id': app_id, 'name': 'Printer', 'url': 'https://printer.example/app', 'icon': 'printer',
            'image': 'logo', 'images': {'logo': png()},
            'screens': [{'id': 'main', 'buttons': [{'id': 'print', 'label': 'Print', 'image': 'logo'}]}]}


@pytest.fixture
def registration(tmp_path):
    local = create_app(tmp_path, hardware=False)
    with TestClient(local.state.registration) as client:
        yield client, local


def test_setup_credential_registers_but_cannot_overwrite_existing_apps(registration):
    client, local = registration
    assert client.post('/v1/apps', json=manifest()).status_code == 401
    headers = {'Authorization': 'Bearer ' + local.state.store.registration_token}
    result = client.post('/v1/apps', json=manifest(), headers=headers)
    assert result.status_code == 201
    app_key = result.json()['appCredential']
    assert app_key != local.state.store.registration_token
    assert client.post('/v1/apps', json=manifest(), headers=headers).status_code == 409
    assert client.put('/v1/apps/printer', json=manifest(), headers=headers).status_code == 401
    updated = client.put('/v1/apps/printer', json={**manifest(), 'name': 'Updated'}, headers={'Authorization': 'Bearer ' + app_key})
    assert updated.status_code == 200
    assert 'appCredential' not in updated.json()
    app = next(item for item in local.state.controller.config.apps if item.id == 'printer')
    assert app.name == 'Updated'
    assert Image.open(io.BytesIO(local.state.store.image(app.images['logo']))).size == (72, 72)


def test_app_keys_are_scoped_and_removal_revokes_them(registration):
    client, local = registration
    headers = {'Authorization': 'Bearer ' + local.state.store.registration_token}
    key = client.post('/v1/apps', json=manifest(), headers=headers).json()['appCredential']
    assert client.put('/v1/apps/other', json=manifest('other'), headers={'Authorization': 'Bearer ' + key}).status_code == 401
    config = local.state.store.load()
    config.apps = [app for app in config.apps if app.id != 'printer']
    saved = local.state.store.save(config)
    local.state.controller.configure(saved)
    assert client.put('/v1/apps/printer', json=manifest(), headers={'Authorization': 'Bearer ' + key}).status_code == 401
    assert not local.state.store.authorize_app('printer', key)


@pytest.mark.parametrize('change', [
    {'url': 'javascript:alert(1)'},
    {'images': {'logo': 'data:image/svg+xml;base64,PHN2Zy8+'}},
    {'screens': [{'id': 'full', 'buttons': [None] * 15}]},
    {'images': {}, 'image': 'missing'},
    {'images': {'../escape': png()}},
    {'textSize': True},
    {'textSize': 33},
    {'icon': '../../etc/passwd'},
    {'icon': 'not-a-heroicon'},
    {'screens': [{'id': 'main', 'buttons': [{'id': 'x', 'label': 'X', 'textSize': 7}]}]},
])
def test_invalid_registration_is_atomic_and_next_request_succeeds(registration, change):
    client, local = registration
    headers = {'Authorization': 'Bearer ' + local.state.store.registration_token}
    previous = local.state.store.load().model_dump()
    assert client.post('/v1/apps', json={**manifest(), **change}, headers=headers).status_code == 422
    assert local.state.store.load().model_dump() == previous
    assert client.post('/v1/apps', json=manifest(), headers=headers).status_code == 201


def test_network_surface_excludes_kiosk_administration(registration):
    client, local = registration
    headers = {'Authorization': 'Bearer ' + local.state.store.registration_token}
    for path in ['/', '/api/health', '/api/config', '/api/pair', '/api/registration-token', '/bridge']:
        assert client.get(path, headers=headers).status_code == 404
    response = client.post('/v1/apps', content=b'x' * 2097153, headers=headers)
    assert response.status_code == 413
    assert client.post('/v1/apps', json=manifest(), headers=headers).status_code == 201


def test_image_limits_and_format_validation():
    digest, data = normalize_image(png())
    assert len(digest) == 64
    assert Image.open(io.BytesIO(data)).size == (72, 72)
    for image in [png((1025, 1025)), 'data:image/png;base64,bm90IGFuIGltYWdl', 'https://example.test/image.png']:
        with pytest.raises(ValueError):
            normalize_image(image)


def test_concurrent_duplicate_registration_does_not_replace_first(registration):
    _, local = registration
    app, assets = prepare_manifest(Manifest.model_validate(manifest()))
    def attempt(_):
        try:
            local.state.store.register(app, assets, secrets.token_urlsafe(32))
            return 'created'
        except ValueError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))
    assert sorted(results) == ['conflict', 'created']
    assert len([item for item in local.state.store.load().apps if item.id == 'printer']) == 1


def test_registered_screens_images_and_stale_context(registration):
    client, local = registration
    client.post('/v1/apps', json=manifest(), headers={'Authorization': 'Bearer ' + local.state.store.registration_token})
    controller = local.state.controller
    controller.connect('browser')
    controller.context('browser', 'document', 'https://printer.example/app')
    controller.layout('browser', 'document', 'screen', 'main')
    assert len(controller.buttons()[0]['image']) == 64
    assert controller.buttons()[14]['id'] == 'home'
    controller.layout('browser', 'document', 'update', {'id': 'print', 'changes': {'disabled': True}})
    assert controller.buttons()[0]['disabled']
    with pytest.raises(ValueError):
        controller.layout('browser', 'document', 'update', {'id': 'print', 'changes': {'image': 'unknown'}})
    assert controller.buttons()[0]['disabled']
    controller.layout('browser', 'document', 'update', {'id': 'print', 'changes': {'disabled': False}})
    assert not controller.buttons()[0]['disabled']
    with pytest.raises(ValueError):
        controller.layout('browser', 'document', 'screen', 'unknown')
    with pytest.raises(ValueError):
        controller.layout('browser', 'document', 'show', {'id': 'bad', 'buttons': [{'id': 'x', 'label': 'X', 'image': 'foreign'}]})
    controller.context('browser', 'other', 'https://unregistered.example/')
    with pytest.raises(ValueError):
        controller.layout('browser', 'document', 'screen', 'main')


def test_revocation_between_authorization_and_commit_cannot_overwrite_new_owner(registration):
    _, local = registration
    store = local.state.store
    app, assets = prepare_manifest(Manifest.model_validate(manifest()))
    old_key = secrets.token_urlsafe(32)
    new_key = secrets.token_urlsafe(32)
    store.register(app, assets, old_key)
    assert store.authorize_app(app.id, old_key)
    config = store.load()
    config.apps = [item for item in config.apps if item.id != app.id]
    store.save(config)
    store.register(app, assets, new_key)
    before = store.load().revision
    with pytest.raises(ValueError, match='credential_changed'):
        store.register(app, assets, old_key, updating=True)
    assert store.load().revision == before
    assert store.authorize_app(app.id, new_key)


def test_registration_preserves_null_icons_sizes_and_updates_after_restart(registration):
    from foxoe.store import Store
    client, local = registration
    value = {**manifest(), 'icon': None, 'image': None, 'textSize': 28, 'backgroundColor': '#123456', 'textColor': '#fedcba', 'iconColor': '#abcdef',
             'screens': [{'id': 'main', 'buttons': [{'id': 'a', 'label': '42', 'icon': None, 'textSize': 32}]}]}
    response = client.post('/v1/apps', json=value, headers={'Authorization': 'Bearer ' + local.state.store.registration_token})
    assert response.status_code == 201
    stored = next(app for app in local.state.store.load().apps if app.id == 'printer')
    assert stored.icon is None and stored.textSize == 28
    assert (stored.iconColor, stored.textColor, stored.backgroundColor) == ('#abcdef', '#fedcba', '#123456')
    assert stored.screens[0].buttons[0].icon is None
    assert stored.screens[0].buttons[0].textSize == 32
    key = response.json()['appCredential']
    headers = {'Authorization': 'Bearer ' + key}
    assert client.put('/v1/apps/printer', json={**value, 'textSize': None}, headers=headers).status_code == 422
    assert next(app for app in local.state.store.load().apps if app.id == 'printer') == stored
    assert client.put('/v1/apps/printer', json={**value, 'icon': 'user', 'textSize': 8}, headers=headers).status_code == 200
    # Re-open the persisted store to ensure the new fields survive serialization.
    reloaded = Store(local.state.store.path.parent).load()
    updated = next(app for app in reloaded.apps if app.id == 'printer')
    assert updated.icon == 'user' and updated.textSize == 8
