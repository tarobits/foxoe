import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from foxoe.server import ORIGIN, create_app


@pytest.fixture
def api(tmp_path):
    app = create_app(tmp_path, hardware=False)
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, app


def test_cross_origin_and_rebinding_denied(api):
    client, app = api
    assert client.get("/api/state", headers={"host": "attacker.example"}).status_code == 400
    assert client.post("/api/pair", headers={"origin": "https://attacker.example"}).status_code == 403
    assert client.post("/api/pair").status_code == 403
    assert client.get("/api/state", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.post("/api/pair", headers={"origin": ORIGIN}).json()["token"] == app.state.store.token


def test_health_identifies_the_running_release_and_keeps_local_boundary(api):
    import os
    from foxoe.server import ROOT
    client, _ = api
    assert client.get('/api/health').json() == {'pid': os.getpid(), 'release': str(ROOT)}
    assert client.get('/api/health', headers={'origin': 'https://example.test'}).status_code == 403
    assert client.get('/api/health', headers={'host': 'example.test'}).status_code == 400


def test_invalid_save_conflict_and_recovery(api):
    client, _ = api
    original = client.get("/api/config").json()
    headers = {"origin": ORIGIN}
    assert client.put("/api/config", json={**original, "brightness": -1}, headers=headers).status_code == 422
    assert client.get("/api/config").json() == original
    saved = client.put("/api/config", json={**original, "title": "Station"}, headers=headers).json()
    assert saved["revision"] == 1
    assert client.put("/api/config", json=original, headers=headers).status_code == 409
    assert client.put("/api/config", json={**saved, "title": "Recovered"}, headers=headers).status_code == 200


def test_bridge_authentication_and_disconnect_cleanup(api):
    client, app = api
    headers = {"origin": "chrome-extension://test-extension"}
    with client.websocket_connect("ws://127.0.0.1:8765/bridge", headers=headers) as socket:
        socket.send_json({"token": "wrong"})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()
    with client.websocket_connect("ws://127.0.0.1:8765/bridge", headers=headers) as socket:
        socket.send_json({"token": app.state.store.token})
        assert socket.receive_json()["type"] == "configuration"
        socket.send_json({"type": "context", "document": "doc", "url": ORIGIN + "/"})
        assert socket.receive_json()["type"] == "ack"
        assert client.get("/api/state").json()["connected"]
    assert not client.get("/api/state").json()["connected"]
    with client.websocket_connect("ws://127.0.0.1:8765/bridge", headers=headers) as socket:
        socket.send_json({"token": app.state.store.token})
        assert socket.receive_json()["type"] == "configuration"


def test_malformed_bridge_message_then_valid_ping(api):
    client, app = api
    with client.websocket_connect("ws://127.0.0.1:8765/bridge", headers={"origin": "chrome-extension://test"}) as socket:
        socket.send_json({"token": app.state.store.token})
        socket.receive_json()
        socket.send_text("not-json")
        assert socket.receive_json()["type"] == "error"
        socket.send_json({"type": "ping"})
        assert socket.receive_json()["type"] == "pong"
        assert socket.receive_json()["type"] == "ack"


def test_regular_page_cannot_open_bridge(api):
    client, _ = api
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("ws://127.0.0.1:8765/bridge", headers={"origin": ORIGIN}):
            pass
